"""PORT ADDITION: the game's own sound card plays what SAPI 5 says.

SAPI hands a line to Windows, which buffers it on its way to the sound card.  Asked to stop, SAPI stops
feeding it, but what is already buffered still plays: measured here, about a tenth of a second after half a
second of speech, growing the longer the voice has been talking.  For a screen-reader player who interrupts
constantly - every row of a menu cuts off the last - that lag is most of what makes a voice feel slow.

So the game can play SAPI itself instead.  SAPI renders a line into memory rather than to the card (160 to
220 times faster than real time, measured), and the result is played through a source of the engine's own,
filled by a callback the way the reverb bus is.  Stopping is then dropping what has not been played yet,
which is instant, with four milliseconds of fade so the cut does not click.

NVDA solves the same problem the same way, and calls it "modern audio output"; Settings -> Speech has a row
of that name.  Nothing here is NVDA's: it renders through an ISpAudio object of its own into its own WASAPI
player, while this uses SAPI's documented memory stream and the sound the game already has.  With the row
off, or with no engine to play through, SAPI speaks to Windows as it always did (speech.py).
"""
from __future__ import annotations

import ctypes
import logging
import threading

import numpy as np

from ..s3d import openal as oal
from ..s3d.device import SAMPLE_RATE

log = logging.getLogger('platform.speech_audio')

#: SAPI renders at the rate and shape the engine's device runs at, so nothing is resampled and the voice
#: reaches the card as it was made.  Stereo, so the source can take AL_DIRECT_CHANNELS_SOFT and go out
#: without the HRTF: a voice belongs in the head, not in the arena.
CHANNELS = 2
#: SpeechAudioFormatType: 44 kHz, 16 bit, stereo
SAPI_FORMAT = 35
#: seconds of ramp when a line is cut off part way, so stopping is not a click
FADE = 0.004
EMPTY = np.zeros(0, dtype=np.float32)


class SpeechAudio:
    """One source on the engine's device, always playing: silence when there is nothing to say."""

    _shared: 'SpeechAudio | None' = None

    @classmethod
    def shared(cls) -> 'SpeechAudio':
        if cls._shared is None:
            cls._shared = SpeechAudio()
        return cls._shared

    def __init__(self):
        self.pending = EMPTY                              # what is still to be played, interleaved float32
        self.at = 0                                       # how much of it the mixer has taken
        self.lock = threading.Lock()
        self.source = 0
        self.buffer = 0
        self._callback = None                             # kept: OpenAL holds the pointer, not the object
        self._engine = None
        self._tried = False
        self._failed = False

    # --- the source -----------------------------------------------------------------------------------
    def available(self) -> bool:
        """Whether a line can be played now; opens the source the first time, once the engine is up."""
        if self.source:
            return True
        if self._tried:
            return False
        return self._open()

    def _open(self) -> bool:
        from ..s3d.engine import S3DEngine
        self._tried = True
        try:
            engine = S3DEngine.engine()
            al = engine.al
            if not al.alIsExtensionPresent(b'AL_SOFT_callback_buffer'):
                log.info('AL_SOFT_callback_buffer missing: SAPI 5 speaks through Windows')
                return False
            al.make_current(engine.device.context)
            self._callback = oal.BUFFER_CALLBACK(self._render)
            self.buffer = al.gen('alGenBuffers')
            al.buffer_callback(self.buffer, oal.AL_FORMAT_STEREO_FLOAT32, SAMPLE_RATE, self._callback)
            self.source = al.gen('alGenSources')
            al.alSourcei(self.source, oal.AL_BUFFER, self.buffer)
            al.alSourcei(self.source, oal.AL_SOURCE_RELATIVE, 1)
            al.alSourcef(self.source, oal.AL_ROLLOFF_FACTOR, 0.0)
            al.alSourcei(self.source, oal.AL_DIRECT_CHANNELS_SOFT, 1)
            al.alSourcePlay(self.source)                  # it runs from here on, silent until there is speech
            al.check('speech source')
            self._engine = engine
            log.info('SAPI 5 is played through the game (%d Hz, %d channels)', SAMPLE_RATE, CHANNELS)
            return True
        except Exception as exc:
            log.info('the game cannot play SAPI 5 itself, so Windows will: %s', exc)
            self.source = 0
            return False

    # --- what the voice says --------------------------------------------------------------------------
    def play(self, pcm: bytes) -> bool:
        """Add a rendered line: 16-bit samples, `CHANNELS` channels, at the device's rate."""
        if not self.available() or not pcm:
            return False
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        with self.lock:
            left = self.pending[self.at:] if self.at else self.pending
            self.pending = np.concatenate((left, samples)) if len(left) else samples
            self.at = 0
        return True

    def stop(self) -> None:
        """Drop what has not been played, bar a few milliseconds faded out so the cut is not a click."""
        with self.lock:
            left = len(self.pending) - self.at
            if left <= 0:
                self.pending, self.at = EMPTY, 0
                return
            n = min(left, int(SAMPLE_RATE * FADE) * CHANNELS)
            n -= n % CHANNELS
            tail = np.array(self.pending[self.at:self.at + n])
            if n:
                ramp = np.linspace(1.0, 0.0, n // CHANNELS, dtype=np.float32).repeat(CHANNELS)
                tail *= ramp
            self.pending, self.at = tail, 0

    def speaking(self) -> bool:
        with self.lock:
            return self.at < len(self.pending)

    def _render(self, _userptr, sampledata, numbytes) -> int:
        """ALBUFFERCALLBACKTYPESOFT, on OpenAL Soft's mixer thread: hand over what is waiting."""
        wanted = numbytes // 4                            # float32 samples, both channels
        try:
            out = np.ctypeslib.as_array((ctypes.c_float * wanted).from_address(sampledata))
            with self.lock:
                have = min(wanted, len(self.pending) - self.at)
                if have > 0:
                    out[:have] = self.pending[self.at:self.at + have]
                    self.at += have
                    if self.at >= len(self.pending):      # said: let the line go rather than hold it
                        self.pending, self.at = EMPTY, 0
                else:
                    have = 0
            if have < wanted:
                out[have:] = 0.0
        except Exception:                                 # never let an exception reach the mixer thread
            if not self._failed:
                self._failed = True
                log.exception('speech render failed')
            ctypes.memset(sampledata, 0, numbytes)
        return numbytes

    def close(self) -> None:
        if not self.source:
            return
        try:
            al = self._engine.al
            al.make_current(self._engine.device.context)
            al.alSourceStop(self.source)
            al.alDeleteSources(1, ctypes.byref(ctypes.c_uint(self.source)))
            al.alDeleteBuffers(1, ctypes.byref(ctypes.c_uint(self.buffer)))
        except Exception as exc:
            log.debug('speech source not closed cleanly: %s', exc)
        self.source, self.buffer, self._callback = 0, 0, None
