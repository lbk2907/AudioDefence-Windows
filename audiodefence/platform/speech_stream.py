"""PORT ADDITION: SAPI writes its sound into the game as it makes it, instead of being rendered first.

With Settings -> Speech -> Use modern output on, the game plays SAPI itself (speech_audio.py).  The first way of doing that was
to render a line into memory and then hand the bytes over, which means nothing is heard until a whole piece
of the line has been made: measured on the user's machine, 25 ms for a settings row, 37 ms for the first
sentence of a paragraph, 121 ms for a piece of the length the splitter allows.

This is the other way round.  SAPI is given an object of ours as its sound card - `ISpVoice::SetOutput`
takes anything that is an `ISpAudio` - and writes into it as the voice is synthesised, in pieces of about a
tenth of a second.  The first of them arrives 16 ms after the key whatever the line's length, and a line no
longer has to be split into pieces at all.

NVDA does the same thing, and calls it modern audio output: a stream object of its own handed to SetOutput,
written into as the voice is made.  None of its code is here - this is written against the interfaces
Microsoft documents, and what SAPI asks of them was found by asking SAPI.

Two ways of killing Python 3.14 were found while building it, and both are avoided here:

* a ctypes call that lets the interpreter go and takes it back, made from inside one of these callbacks,
  ends the process at once (`_PyThreadState_Attach: non-NULL old thread state`).  The one call needed,
  `CoTaskMemAlloc`, is made through `ctypes.PyDLL`, which holds the interpreter throughout.
* letting the sink go while it is still the voice's output ends the process on the way out
  (`gilstate_tss_set: failed to set current tstate`).  The voice is given its own card back first, always.
"""
from __future__ import annotations

import ctypes
import logging

from .speech_audio import BYTES_PER_FRAME, CHANNELS, RATE, lead_in_frames

log = logging.getLogger('platform.speech_stream')

#: SPDFID_WaveFormatEx: what the format we report is a format of
WAVE_FORMAT = '{C31ADBAE-527F-4ff5-A230-F62BB61FF70C}'
BITS = 8 * BYTES_PER_FRAME // CHANNELS
E_FAIL = -2147467259
E_NOTIMPL = 0x80004001
S_FALSE = 1
#: PyDLL rather than windll: see the module's own notes
_ole32 = ctypes.PyDLL('ole32.dll')
_ole32.CoTaskMemAlloc.restype = ctypes.c_void_p
_ole32.CoTaskMemAlloc.argtypes = (ctypes.c_size_t,)

_class = None                                             # built once, the first time one is wanted
_broken = False


def sink(play, dropping):
    """An object SAPI can write into, or None where it cannot be made.

    `play` is given the bytes of the voice as they arrive, and `dropping` is asked, before each of them,
    whether the line they belong to has been interrupted.
    """
    global _class, _broken
    if _broken:
        return None
    if _class is None:
        try:
            _class = _build()
        except Exception as exc:
            log.info('SAPI cannot write into the game directly, so it will be rendered first: %s', exc)
            _broken = True
            return None
    try:
        return _class(play, dropping)
    except Exception as exc:
        log.info('the SAPI stream would not be made: %s', exc)
        _broken = True
        return None


def _build():
    """The class itself, built on being asked for so that a machine without these interfaces still runs."""
    from comtypes import COMObject, GUID
    from comtypes.gen import SpeechLib

    format_id = GUID(WAVE_FORMAT)

    def wave_format():
        shape = SpeechLib.WAVEFORMATEX()
        shape.wFormatTag = 1                              # WAVE_FORMAT_PCM
        shape.nChannels = CHANNELS
        shape.nSamplesPerSec = RATE
        shape.wBitsPerSample = BITS
        shape.nBlockAlign = BYTES_PER_FRAME
        shape.nAvgBytesPerSec = RATE * BYTES_PER_FRAME
        shape.cbSize = 0
        return shape

    class SpeechSink(COMObject):
        """The sound card SAPI thinks it has.

        Everything SAPI asks of a card is answered the way a card with endless room answers: it never has
        to wait, so it renders the line as fast as it can and the game holds what it makes.  The only
        method that does anything is the write.
        """

        _com_interfaces_ = [SpeechLib.ISpAudio, SpeechLib.ISpEventSink, SpeechLib.ISpEventSource]

        def __init__(self, play, dropping):
            super().__init__()
            self.play = play
            self.dropping = dropping
            self.written = 0
            self.trimming = True                          # the silence at the front of a line goes
            self.event = ctypes.windll.kernel32.CreateEventW(None, True, False, None)

        def starting(self) -> None:
            """A new line is about to be spoken."""
            self.trimming = True

        # --- the sound itself -------------------------------------------------------------------------
        def ISequentialStream_RemoteWrite(self, this, pv, cb, written):
            size = int(cb)
            if written:
                written[0] = cb                           # taken whatever happens: a short write stops SAPI
            try:
                if self.dropping():                       # interrupted: the rest of the line is not played
                    return 0
                self.written += size
                data = ctypes.string_at(pv, size)         # PYFUNCTYPE: the interpreter is held throughout
                if self.trimming:                         # SAPI's own silence, before the voice starts
                    frames = lead_in_frames(data)
                    if frames is None:
                        return 0                          # nothing but silence so far: none of it is kept
                    data = data[frames * BYTES_PER_FRAME:]
                    self.trimming = False
                self.play(data)
            except Exception:
                log.exception('the speech stream could not take what SAPI wrote')
            return 0

        def ISequentialStream_RemoteRead(self, this, pv, cb, read):
            if read:
                read[0] = 0
            return 0

        # --- what SAPI needs a card to be -------------------------------------------------------------
        def ISpStreamFormat_GetFormat(self, this, guid_out, format_out):
            try:
                if guid_out:
                    ctypes.cast(guid_out, ctypes.POINTER(GUID))[0] = format_id
                if format_out:
                    room = _ole32.CoTaskMemAlloc(ctypes.sizeof(SpeechLib.WAVEFORMATEX))
                    if not room:
                        return E_FAIL
                    ctypes.cast(room, ctypes.POINTER(SpeechLib.WAVEFORMATEX))[0] = wave_format()
                    ctypes.cast(format_out, ctypes.POINTER(ctypes.c_void_p))[0] = room
            except Exception:
                log.exception('the speech stream could not say what shape it is')
                return E_FAIL
            return 0

        def ISpAudio_GetDefaultFormat(self, this, guid_out, format_out):
            return self.ISpStreamFormat_GetFormat(this, guid_out, format_out)

        def ISpAudio_SetFormat(self, this, guid, shape):
            return 0                                      # it is set to ours: SetOutput is told not to change

        def ISpAudio_GetStatus(self, this, status):
            try:
                out = ctypes.cast(status, ctypes.POINTER(SpeechLib.SPAUDIOSTATUS))
                out[0].cbFreeBuffSpace = 1 << 20          # room enough that SAPI never waits on us
                out[0].cbNonBlockingIO = 1 << 20
                out[0].State = 3                          # SPAS_RUN
                out[0].CurSeekPos = self.written
                out[0].CurDevicePos = self.written
            except Exception:
                log.exception('the speech stream could not give its status')
                return E_FAIL
            return 0

        def ISpAudio_SetState(self, this, state, reserved):
            return 0

        def ISpAudio_SetBufferInfo(self, this, info):
            return 0

        def ISpAudio_GetBufferInfo(self, this, info):
            return 0

        def ISpAudio_EventHandle(self, this):
            return self.event

        def ISpAudio_GetVolumeLevel(self, this, level):
            if level:
                ctypes.cast(level, ctypes.POINTER(ctypes.c_ulong))[0] = 10000
            return 0

        def ISpAudio_SetVolumeLevel(self, this, level):
            return 0                                      # the voice's own volume is what the game sets

        def ISpAudio_GetBufferNotifySize(self, this, size):
            if size:
                ctypes.cast(size, ctypes.POINTER(ctypes.c_ulong))[0] = 4096
            return 0

        def ISpAudio_SetBufferNotifySize(self, this, size):
            return 0

        # --- the stream half of it, which SAPI asks after but does not use ----------------------------
        def IStream_RemoteSeek(self, this, offset, origin, out):
            if out:
                ctypes.cast(out, ctypes.POINTER(ctypes.c_ulonglong))[0] = self.written
            return 0

        def IStream_SetSize(self, this, size):
            return 0

        def IStream_Commit(self, this, flags):
            return 0

        def IStream_Revert(self, this):
            return 0

        def IStream_LockRegion(self, this, offset, count, kind):
            return 0

        def IStream_UnlockRegion(self, this, offset, count, kind):
            return 0

        def IStream_Stat(self, this, stat, flag):
            return 0

        def IStream_Clone(self, this, out):
            return 0

        def IStream_RemoteCopyTo(self, this, other, count, read, written):
            return 0

        # --- what SAPI tells a card, none of which the game listens to --------------------------------
        def ISpEventSink_AddEvents(self, this, events, count):
            return 0

        def ISpEventSink_GetEventInterest(self, this, interest):
            if interest:
                ctypes.cast(interest, ctypes.POINTER(ctypes.c_ulonglong))[0] = 0
            return 0

        def ISpEventSource_SetInterest(self, this, interest, queued):
            return 0

        def ISpEventSource_GetEvents(self, this, count, events, fetched):
            if fetched:
                ctypes.cast(fetched, ctypes.POINTER(ctypes.c_ulong))[0] = 0
            return S_FALSE                                # nothing waiting, ever

        def ISpEventSource_GetInfo(self, this, info):
            return 0

        def ISpNotifySource_SetNotifySink(self, this, notify):
            return 0

        def ISpNotifySource_SetNotifyWindowMessage(self, this, window, message, wparam, lparam):
            return E_NOTIMPL

        def ISpNotifySource_SetNotifyCallbackFunction(self, this, call, wparam, lparam):
            return E_NOTIMPL

        def ISpNotifySource_SetNotifyCallbackInterface(self, this, call, wparam, lparam):
            return E_NOTIMPL

        def ISpNotifySource_SetNotifyWin32Event(self, this):
            return 0

        def ISpNotifySource_WaitForNotifyEvent(self, this, milliseconds):
            return 0

        def ISpNotifySource_GetNotifyEventHandle(self, this):
            return self.event

    return SpeechSink
