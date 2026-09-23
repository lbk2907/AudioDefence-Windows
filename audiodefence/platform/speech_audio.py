"""PORT ADDITION: the game plays what SAPI 5 says, through a sound card of its own.

SAPI hands a line to Windows, which buffers it on its way to the sound card.  Asked to stop, SAPI stops
feeding it, but what is already buffered still plays: measured here, about a tenth of a second after half a
second of speech, growing the longer the voice has been talking.  For a screen-reader player who interrupts
constantly - every row of a menu cuts off the last - that lag is most of what makes a voice feel slow.

So the game plays SAPI itself.  SAPI renders a line into memory rather than to the card (160 to 220 times
faster than real time, measured), and the result is played through an SDL audio device the speech opens for
itself - the same way the DualSense's haptics have their own (haptic_audio.py).  Stopping is then dropping
what has not been handed over yet, which leaves only SDL's own buffer of about 12 milliseconds, with a
short fade so the cut does not click.

It is a device of its own on purpose.  The game's engine is OpenAL, whose current context belongs to the
thread that set it, and the reverb bus moves it between two devices as it renders; speech arriving from its
own thread and touching any of that stops the game's sound dead.  Nothing here touches the engine: the
speech device is opened, filled and closed on its own, and the worst it can do is fall silent.

NVDA solves the same problem the same way - its own player, not the app's - and calls it "modern audio
output"; Settings -> Speech has a row of that name, since NVDA's players know it.  None of NVDA's code is
here: it streams through an ISpAudio object of its own into its WASAPI player, where this renders to memory
through SAPI's documented stream and plays it through SDL.  With the row off, or with no device to be had,
SAPI speaks to Windows as it always did (speech.py).
"""
from __future__ import annotations

import logging
import threading
import time

import numpy as np

log = logging.getLogger('platform.speech_audio')

#: what SAPI is asked to render, and what the device is opened as: 16-bit mono at 44.1 kHz, so the bytes go
#: from the one to the other as they are.  Mono because a voice is mono: rendering it in stereo doubled
#: every byte for a copy of itself, and it is the bytes that cost - see SAPI_FORMAT below.
RATE = 44100
CHANNELS = 1
BYTES_PER_FRAME = 2 * CHANNELS
#: SpeechAudioFormatType: 44 kHz, 16 bit, mono.  Measured on the user's machine, rendering a page of the
#: encyclopedia: 44.1 stereo 257 ms, 44.1 mono 149 ms, 22 kHz mono 98 ms - of which GetData, which hands the
#: bytes from COM to Python with the interpreter held, was 116, 58 and 28.  The game's own sound is mixed by
#: Python on the audio thread (the reverb bus), so anything holding the interpreter that long is a dropout
#: in the arena.  Mono at the card's own rate is the best of both: half the bytes of stereo, and nothing
#: resampled.  The rest is dealt with by rendering a line in pieces (speech._SapiThread).
SAPI_FORMAT = 34
#: frames per callback: 512 is about 12 ms, which is how much of a cut-off line is still heard
CHUNK = 512
#: seconds of ramp when a line is cut off part way, so stopping is not a click
FADE = 0.004
#: how long before a device that would not open is tried again
RETRY_SECONDS = 5.0


class SpeechAudio:
    """The speech device: silence when there is nothing to say, and nothing to do with the game's engine."""

    _shared: 'SpeechAudio | None' = None

    @classmethod
    def shared(cls) -> 'SpeechAudio':
        if cls._shared is None:
            cls._shared = SpeechAudio()
        return cls._shared

    def __init__(self):
        self.device = None
        self.chunks: list = []                            # the line still to be played, as raw 16-bit bytes
        self.at = 0                                       # how far into the first of them the card has got
        self.lock = threading.Lock()
        self.last_try = -RETRY_SECONDS

    # --- the card -------------------------------------------------------------------------------------
    def available(self) -> bool:
        """Whether a line can be played now; opens the device the first time.  Called from the speaking
        thread, so the game never waits for a card to open - it took 80 ms on this machine."""
        if self.device is not None:
            return True
        now = time.monotonic()
        if now - self.last_try < RETRY_SECONDS:
            return False
        self.last_try = now
        return self.open()

    def open(self) -> bool:
        try:
            from pygame._sdl2 import audio
            device = audio.AudioDevice(devicename=None, iscapture=False, frequency=RATE,
                                       audioformat=audio.AUDIO_S16, numchannels=CHANNELS, chunksize=CHUNK,
                                       allowed_changes=0, callback=self._fill)
            device.pause(0)
        except Exception as exc:                          # no device, or it would not open: Windows speaks
            log.info('the game cannot play speech itself, so Windows will: %s', exc)
            return False
        self.device = device
        log.info('speech is played by the game (%d Hz, %d channels)', RATE, CHANNELS)
        return True

    def close(self) -> None:
        device, self.device = self.device, None
        with self.lock:
            self.chunks, self.at = [], 0
        if device is not None:
            try:
                device.close()
            except Exception:
                pass

    # --- what the voice says --------------------------------------------------------------------------
    def play(self, pcm: bytes) -> bool:
        """Add a rendered line: 16-bit frames, `CHANNELS` channels, at `RATE`.  Called from the speaking
        thread, and does nothing but add to the list the card reads."""
        if self.device is None or not pcm:
            return False
        with self.lock:
            self.chunks.append(pcm)
        return True

    def stop(self) -> None:
        """Drop what has not been played, bar a few milliseconds faded out so the cut is not a click.  What
        SDL already holds - about twelve milliseconds - is heard whatever happens."""
        with self.lock:
            if not self.chunks:
                self.at = 0
                return
            head = self.chunks[0][self.at:]
            self.chunks, self.at = [], 0
            n = min(len(head), int(RATE * FADE) * BYTES_PER_FRAME)
            n -= n % BYTES_PER_FRAME
            if n:
                tail = np.frombuffer(head[:n], dtype=np.int16).astype(np.float32)
                ramp = np.linspace(1.0, 0.0, len(tail) // CHANNELS, dtype=np.float32).repeat(CHANNELS)
                self.chunks = [(tail * ramp).astype(np.int16).tobytes()]

    def speaking(self) -> bool:
        with self.lock:
            return bool(self.chunks)

    def _fill(self, _device, stream) -> None:
        """SDL's audio thread: hand over what is waiting, and silence when there is none."""
        wanted = len(stream)
        filled = 0
        try:
            with self.lock:
                while filled < wanted and self.chunks:
                    chunk = self.chunks[0]
                    take = min(wanted - filled, len(chunk) - self.at)
                    stream[filled:filled + take] = chunk[self.at:self.at + take]
                    filled += take
                    self.at += take
                    if self.at >= len(chunk):
                        self.chunks.pop(0)
                        self.at = 0
            if filled < wanted:
                stream[filled:] = bytes(wanted - filled)
        except Exception:                                 # never let an exception reach SDL's thread
            log.exception('speech fill failed')
            try:
                stream[:] = bytes(wanted)
            except Exception:
                pass
