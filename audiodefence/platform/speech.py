"""Screen reader output: NVDA through its controller client; otherwise another screen reader through
Prism (JAWS, ZoomText, System Access and the rest, and Narrator); otherwise SAPI 5.  On the Mac:
VoiceOver, otherwise the system voice (platform/macspeech.py), which take NVDA's and SAPI 5's places here.

This replaces VoiceOver's reading of labels and UIAccessibilityPostNotification announcements, and the port
counts as a VoiceOver player whichever of them is speaking (Speech.screen_reader_running).
"""
from __future__ import annotations

import ctypes
import logging
import queue
import threading
import time
from ctypes import wintypes
from xml.sax.saxutils import escape

from .. import paths
from . import host

log = logging.getLogger('speech')

#: PORT ADDITION: Settings -> Miscellaneous -> Speech output.  Automatic takes the first of these that can
#: speak, in this order; any other choice speaks through that one only, and the game is silent while it
#: cannot.
OUTPUTS = (('auto', 'Automatic'), ('nvda', 'NVDA'), ('jaws', 'JAWS'), ('zdsr', 'ZDSR'), ('narrator', 'Narrator'),
           ('zoomtext', 'ZoomText'), ('systemaccess', 'System Access'), ('windoweyes', 'Window-Eyes'),
           ('pctalker', 'PC-Talker'), ('boypcreader', 'Boy PC Reader'), ('sensereader', 'Sense Reader'),
           ('sapi', 'SAPI 5'))
if host.MAC:
    #: the Mac's: VoiceOver where Windows has NVDA, and the system voice under SAPI 5's key, 'sapi', since it
    #: does SAPI 5's job and takes the same settings (Settings -> Speech's voice, rate, pitch and volume)
    OUTPUTS = (('auto', 'Automatic'), ('voiceover', 'VoiceOver'), ('sapi', 'System voice'))
#: the screen reader the game speaks to directly, and what the built-in voice is called
SCREEN_READER = 'voiceover' if host.MAC else 'nvda'
VOICE_NAME = dict(OUTPUTS)['sapi']
#: the choices Prism speaks for, by Prism's own names for them
PRISM_NAMES = {'jaws': 'JAWS', 'narrator': 'UIA', 'zoomtext': 'ZoomText', 'systemaccess': 'SystemAccess',
               'windoweyes': 'WindowEyes', 'pctalker': 'PCTalker', 'zdsr': 'ZDSR', 'boypcreader': 'BoyPCReader',
               'sensereader': 'SenseReader'}


class _Nvda:
    def __init__(self):
        self.dll = None
        try:
            self.dll = ctypes.windll.LoadLibrary(str(paths.NVDA_DLL))
            self.dll.nvdaController_testIfRunning.restype = ctypes.c_ulong
            self.dll.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
            self.dll.nvdaController_speakText.restype = ctypes.c_ulong
            self.dll.nvdaController_cancelSpeech.restype = ctypes.c_ulong
            self.dll.nvdaController_brailleMessage.argtypes = [ctypes.c_wchar_p]
            self.dll.nvdaController_brailleMessage.restype = ctypes.c_ulong
        except (OSError, AttributeError):
            log.info('NVDA controller client not available')
            self.dll = None

    def running(self) -> bool:
        return bool(self.dll is not None and self.dll.nvdaController_testIfRunning() == 0)

    def speak(self, text: str, interrupt: bool) -> bool:
        if not self.running():
            return False
        if interrupt:
            self.dll.nvdaController_cancelSpeech()
        self.dll.nvdaController_speakText(text)
        self.dll.nvdaController_brailleMessage(text)
        return True

    def stop(self) -> None:
        if self.running():
            self.dll.nvdaController_cancelSpeech()


class _ProcessEntry(ctypes.Structure):                  # PROCESSENTRY32W
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD),
                ('szExeFile', ctypes.c_wchar * 260)]


def process_running(exe: str) -> bool:
    """Whether a program with this file name ('narrator.exe') is running, from Windows' process list.
    A few milliseconds; False wherever the list cannot be read."""
    try:
        k32 = ctypes.WinDLL('kernel32')
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        snap = k32.CreateToolhelp32Snapshot(2, 0)       # TH32CS_SNAPPROCESS
    except (OSError, AttributeError):
        return False
    if not snap or snap == wintypes.HANDLE(-1).value:    # INVALID_HANDLE_VALUE
        return False
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        exe = exe.lower()
        more = k32.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() == exe:
                return True
            more = k32.Process32NextW(snap, ctypes.byref(entry))
        return False
    finally:
        k32.CloseHandle(snap)


class _Readers:
    """PORT ADDITION: the screen readers other than NVDA, through Prism (the prismatoid package, optional).

    NVDA keeps its own controller client above, which is asked before every line whether NVDA is running.
    The others are tried in Speech output's order (OUTPUTS), not Prism's own.  Prism also offers plain
    voices (OneCore, its own SAPI); those are left out, so with no screen reader running the voice is the
    same SAPI 5 one as before, with its own settings (_Sapi).  Narrator is reached through Prism's UI
    Automation notifications ('UIA'), which Prism ranks last and which report themselves ready whether
    Narrator is running or not - sent with nothing listening, a line would be lost - so the game asks
    Windows itself whether Narrator.exe is running, and uses them only then.  A screen reader started
    while the game runs is looked for every few seconds, and one that stops or fails is let go at once and
    SAPI 5 speaks the line instead.  Prism is loaded only once NVDA is found not to be running, so an NVDA
    player never loads it."""

    NARRATOR = 'UIA'                                      # Prism's name for what Narrator reads
    PROBE_EVERY = 5.0                                     # seconds between looks, while none is speaking
    CHECK_EVERY = 1.0                                     # seconds between asking the one in use

    def __init__(self):
        self.ctx = None
        self.ids = []
        self.reader = None
        self.only = None                                  # the one screen reader chosen, or None for any
        self.next_probe = 0.0
        self.checked = 0.0
        try:
            from prism import Context
            self.ctx = Context()
            present = {self.ctx.name_of(bid): bid
                       for bid in (self.ctx.id_of(i) for i in range(self.ctx.backends_count))}
            self.ids = [present[PRISM_NAMES[key]] for key, _name in OUTPUTS
                        if key in PRISM_NAMES and PRISM_NAMES[key] in present]
            log.info('Prism: %s', ', '.join(self.ctx.name_of(bid) for bid in self.ids))
        except Exception as exc:                          # not installed, or its library will not load
            log.info('Prism not available (%s): NVDA and SAPI 5 only', exc)
            self.ctx = None
            self.ids = []

    @classmethod
    def _running(cls, backend) -> bool:
        if backend.name == cls.NARRATOR:
            return process_running('narrator.exe')
        try:
            return bool(backend.features.is_supported_at_runtime)
        except Exception:
            return False

    def _drop(self, why) -> None:
        log.info('speech: %s let go (%s)', self.reader.name, why)
        self.reader = None
        self.next_probe = 0.0                             # look for another at once

    def current(self, only=None):
        """The screen reader to speak through, or None - any of them, or only the one Prism calls `only`."""
        if self.ctx is None:
            return None
        if only != self.only:                             # Speech output changed: look again, for it
            self.only, self.reader, self.next_probe = only, None, 0.0
        now = time.monotonic()
        if self.reader is not None and now - self.checked >= self.CHECK_EVERY:
            self.checked = now
            if not self._running(self.reader):
                self._drop('no longer running')
        if self.reader is None and now >= self.next_probe:
            self.next_probe = now + self.PROBE_EVERY
            for bid in self.ids:
                name = self.ctx.name_of(bid)
                if only is not None and name != only:
                    continue
                if name == self.NARRATOR and not process_running('narrator.exe'):
                    continue                              # not even made, with Narrator off
                try:
                    backend = self.ctx.create(bid)
                except Exception:
                    continue
                if self._running(backend):
                    self.reader, self.checked = backend, now
                    log.info('speech: %s, through Prism', backend.name)
                    break
        return self.reader

    def speak(self, text: str, interrupt: bool, only=None) -> bool:
        reader = self.current(only)
        if reader is None:
            return False
        try:
            if reader.features.supports_output:           # speech, and braille where there is a display
                reader.output(text, interrupt)
            else:
                reader.speak(text, interrupt)
            return True
        except Exception as exc:
            self._drop(exc)
            return False

    def stop(self) -> None:
        if self.reader is not None:
            try:
                self.reader.stop()
            except Exception as exc:
                self._drop(exc)


#: PORT ADDITION: Settings -> Miscellaneous -> SAPI 5 voice, rate, rate boost, pitch and volume.  A voice or
#: rate or volume of None is Control Panel's (whatever a new SpVoice starts with); pitch 0 is the voice's own.
SAPI_DEFAULTS = {'voice': None, 'rate': None, 'boost': False, 'pitch': 0, 'volume': None}


class _SapiThread(threading.Thread):
    """PORT ADDITION: a thread of SAPI's own, so a line the game speaks never stops the game.

    Every SAPI call costs the thread that makes it: measured here, 10 ms to hand over a line, 26 to 30 ms
    when it cuts off the one before, and up to 50 ms to stop.  On the main thread that is a stutter in the
    arena every time a row is read out, so the calls are made here instead.

    The voice belongs to this thread (COM objects do), which is why the settings are sent as commands
    rather than set from outside.  `generation` is what makes stopping instant: it goes up whenever the
    game interrupts, and a line whose generation has passed is dropped rather than spoken - what is already
    playing is cut by the caller, in SpeechAudio, before this thread has even woken up.
    """

    def __init__(self, sapi):
        super().__init__(daemon=True, name='sapi')
        self.sapi = sapi
        self.queue: 'queue.Queue' = queue.Queue()
        self.voice = None
        self.audio = None                                 # its output as ISpeechAudio, for stopping it
        self.ready = threading.Event()

    # --- what the game asks for -----------------------------------------------------------------------
    def say(self, body: str, flags: int, engine: bool, generation: int) -> None:
        self.queue.put(('speak', generation, body, flags, engine))

    def silence(self, generation: int) -> None:
        self.queue.put(('stop', generation))

    def configure(self, voice_id, rate: int, volume: int) -> None:
        self.queue.put(('configure', voice_id, rate, volume))

    # --- the thread -----------------------------------------------------------------------------------
    def run(self) -> None:
        try:
            import comtypes
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except Exception as exc:                          # already initialised, or a build without it
            log.debug('SAPI thread: %s', exc)
        try:
            import comtypes.client
            self.voice = comtypes.client.CreateObject('SAPI.SpVoice')
            self.client = comtypes.client
        except Exception as exc:
            log.info('SAPI not available on its own thread: %s', exc)
            self.ready.set()
            return
        self.ready.set()
        while True:
            command = self.queue.get()
            try:
                if command[0] == 'quit':
                    return
                if command[0] == 'configure':
                    self._configure(*command[1:])
                elif command[0] == 'stop':
                    self._stop(command[1])
                elif command[0] == 'speak':
                    self._speak(*command[1:])
            except Exception:
                log.exception('SAPI thread: %s failed', command[0])

    def _configure(self, voice_id, rate: int, volume: int) -> None:
        if voice_id:
            token = self.sapi.token_on(self.voice, voice_id)
            if token is not None and token.Id != self.voice.Voice.Id:
                self.voice.Voice = token
        self.voice.Rate = rate
        self.voice.Volume = volume

    def _audio_stream(self):
        """The voice's own output, as the interface that can stop what is on its way to the card."""
        if self.audio is None:
            try:
                from comtypes.gen import SpeechLib
                self.audio = self.voice.AudioOutputStream.QueryInterface(SpeechLib.ISpeechAudio)
            except Exception as exc:
                log.debug('SAPI audio stream not reachable: %s', exc)
                self.audio = False
        return self.audio or None

    def _stop(self, generation: int) -> None:
        if generation < self.sapi.generation:
            return
        audio = self._audio_stream()
        if audio is not None:                             # drop what Windows already has, then purge
            audio.SetState(_Sapi.SAS_STOP)
        self.voice.Speak('', _Sapi.SVSF_ASYNC | _Sapi.SVSF_PURGE)
        if audio is not None:
            audio.SetState(_Sapi.SAS_RUN)

    def _speak(self, generation: int, body: str, flags: int, engine: bool) -> None:
        if generation < self.sapi.generation:             # interrupted before this one was reached
            return
        if engine and self._render(generation, body, flags):
            return
        if flags & _Sapi.SVSF_PURGE:                      # Windows plays it: cut what it is playing first
            audio = self._audio_stream()
            if audio is not None:
                audio.SetState(_Sapi.SAS_STOP)
                self.voice.Speak(body, flags)
                audio.SetState(_Sapi.SAS_RUN)
                return
        self.voice.Speak(body, flags)

    def _render(self, generation: int, body: str, flags: int) -> bool:
        """Render into memory and hand it to the game's own source.  False if that cannot be done, and the
        line goes to Windows instead."""
        from .speech_audio import SAPI_FORMAT, SpeechAudio
        audio = SpeechAudio.shared()
        if not audio.available():
            return False
        try:
            stream = self.client.CreateObject('SAPI.SpMemoryStream')
            shape = stream.Format
            shape.Type = SAPI_FORMAT
            stream.Format = shape
            self.voice.AudioOutputStream = stream
            self.voice.Speak(body, flags & ~(_Sapi.SVSF_ASYNC | _Sapi.SVSF_PURGE))   # here, not to the card
            pcm = bytes(stream.GetData())
        except Exception as exc:
            log.info('SAPI could not be rendered, so Windows will play it: %s', exc)
            self._to_windows()
            return False
        finally:
            self.audio = None                             # its output stream is ours now, not the card's
        if generation < self.sapi.generation:             # interrupted while it was being made
            return True
        audio.play(pcm)
        return True

    def _to_windows(self) -> None:
        """Give the voice back to Windows, for when rendering has failed and the line must still be said."""
        try:
            self.voice.AudioOutputStream = None
        except Exception as exc:
            log.debug('SAPI output not given back: %s', exc)


class _Sapi:
    """SAPI 5, with the player's voice, rate, rate boost, pitch and volume.

    Rate (-10 to 10) and volume (0 to 100) are the voice's own properties.  Pitch has none, so it is SAPI's
    XML, <pitch absmiddle> (-10 to 10), and the rate boost is <rate speed="10"> on top of the rate: some
    voices go faster that way than rate 10 allows and some do not, which is measured for each voice
    (boost_supported) rather than assumed.  The XML is sent only while one of them is in use, since some
    voices take XML oddly; otherwise the text goes as plain text (SVSFIsNotXML), never parsed."""

    SVSF_ASYNC = 1                                        # SpeechLib's SpeechVoiceSpeakFlags
    SVSF_PURGE = 2
    SVSF_IS_XML = 8
    SVSF_IS_NOT_XML = 16
    SAS_STOP, SAS_RUN = 1, 3                              # SpeechAudioState: stopping the output stream

    def __init__(self):
        self.voice = None
        self.client = None
        self.panel_rate, self.panel_volume = 0, 100
        self.config = dict(SAPI_DEFAULTS)
        self._voices = None
        self._boost = {}
        self.thread = None                                # the speaking voice lives there (PORT ADDITION)
        self.generation = 0
        try:
            import comtypes.client
            self.client = comtypes.client
            self.voice = comtypes.client.CreateObject('SAPI.SpVoice')
            self.panel_rate, self.panel_volume = int(self.voice.Rate), int(self.voice.Volume)
        except Exception:
            log.info('SAPI not available')
            self.voice = None

    def voices(self) -> list:
        """(id, name) for every installed SAPI 5 voice, in SAPI's own order."""
        if self._voices is None:
            self._voices = []
            if self.voice is not None:
                tokens = self.voice.GetVoices()
                for i in range(tokens.Count):
                    token = tokens.Item(i)
                    self._voices.append((str(token.Id), str(token.GetDescription())))
        return self._voices

    def _token(self, voice_id):
        return self.token_on(self.voice, voice_id)

    @staticmethod
    def token_on(voice, voice_id):
        """The token for this voice id, asked of a given SpVoice: COM objects belong to one thread, so the
        speaking thread looks its own up rather than being handed one."""
        tokens = voice.GetVoices()
        for i in range(tokens.Count):
            if tokens.Item(i).Id == voice_id:
                return tokens.Item(i)
        return None

    def configure(self, voice=None, rate=None, boost=False, pitch=0, volume=None) -> None:
        self.config = {'voice': voice, 'rate': rate, 'boost': bool(boost), 'pitch': int(pitch or 0),
                       'volume': volume}
        if self.voice is None:
            return
        try:
            token = self._token(voice) if voice else None
            if token is None:                             # Control Panel's, as a new SpVoice starts on
                token = self.client.CreateObject('SAPI.SpVoice').Voice
            if token.Id != self.voice.Voice.Id:
                self.voice.Voice = token
            self.voice.Rate = self.rate()
            self.voice.Volume = self.volume()
        except Exception as exc:
            log.info('SAPI settings not applied: %s', exc)
        if self.thread is not None:                       # and the voice that does the speaking
            self.thread.configure(self.config['voice'], self.rate(), self.volume())

    def rate(self) -> int:
        rate = self.config['rate']
        return self.panel_rate if rate is None else max(-10, min(10, int(rate)))

    def volume(self) -> int:
        volume = self.config['volume']
        return self.panel_volume if volume is None else max(0, min(100, int(volume)))

    def boost_supported(self, voice_id=None) -> bool:
        """Whether this voice (None: Control Panel's) speaks faster with the boost than at rate 10 alone,
        measured once a session by speaking a line into memory both ways."""
        key = voice_id or ''
        if key not in self._boost:
            self._boost[key] = self._measure_boost(voice_id)
        return self._boost[key]

    def _measure_boost(self, voice_id) -> bool:
        if self.voice is None:
            return False
        try:
            from comtypes.gen import SpeechLib
            voice = self.client.CreateObject('SAPI.SpVoice')
            token = self._token(voice_id) if voice_id else None
            if token is not None:
                voice.Voice = token
            voice.Rate = 10
            line = 'Reload your weapon and get ready.'

            def length(text, flags) -> int:
                stream = self.client.CreateObject('SAPI.SpMemoryStream')
                audio_format = self.client.CreateObject('SAPI.SpAudioFormat')
                audio_format.Type = SpeechLib.SAFT22kHz16BitMono
                stream.Format = audio_format
                voice.AudioOutputStream = stream
                voice.Speak(text, flags)
                return len(bytes(stream.GetData()))
            plain = length(line, self.SVSF_IS_NOT_XML)
            boosted = length('<rate speed="10">%s</rate>' % line, self.SVSF_IS_XML)
            log.info('SAPI rate boost for %s: %s', voice_id or 'the Control Panel voice',
                     'yes' if plain and boosted < 0.9 * plain else 'no')
            return bool(plain) and boosted < 0.9 * plain
        except Exception as exc:
            log.info('SAPI rate boost not measured: %s', exc)
            return False

    def worker(self) -> '_SapiThread':
        """PORT ADDITION: the thread the voice speaks on, started the first time it is wanted."""
        if self.thread is None:
            self.thread = _SapiThread(self)
            self.thread.start()
            self.thread.ready.wait(2.0)
            if self.config != SAPI_DEFAULTS:
                self.thread.configure(self.config['voice'], self.rate(), self.volume())
        return self.thread

    @staticmethod
    def modern_audio() -> bool:
        """Settings -> Speech -> Modern audio output: whether the game plays SAPI 5 itself."""
        from ..game.parameters import GameParameters
        return GameParameters.shared().modern_audio()

    def speak(self, text: str, interrupt: bool) -> bool:
        if self.voice is None:
            return False
        flags = self.SVSF_ASYNC | (self.SVSF_PURGE if interrupt else 0)
        pitch = self.config['pitch']
        boost = self.config['boost'] and self.boost_supported(self.config['voice'])
        if pitch or boost:
            body = escape(text)
            if boost:
                body = '<rate speed="10">%s</rate>' % body
            if pitch:
                body = '<pitch absmiddle="%d">%s</pitch>' % (max(-10, min(10, pitch)), body)
            flags |= self.SVSF_IS_XML
        else:
            body, flags = text, flags | self.SVSF_IS_NOT_XML
        engine = self.modern_audio()
        if interrupt:
            self.generation += 1
            if engine:                                    # cut here rather than wait for the thread to wake
                from .speech_audio import SpeechAudio
                SpeechAudio.shared().stop()
        self.worker().say(body, flags, engine, self.generation)
        return True

    def stop(self) -> None:
        if self.voice is None:
            return
        self.generation += 1
        from .speech_audio import SpeechAudio
        SpeechAudio.shared().stop()                       # what the game is playing: gone at once
        self.worker().silence(self.generation)


class _NoReaders:
    """The Mac has no Prism: VoiceOver is spoken to directly, as NVDA is on Windows."""
    ctx = None
    reader = None

    def current(self, only=None):
        return None

    def speak(self, text: str, interrupt: bool, only=None) -> bool:
        return False

    def stop(self) -> None:
        pass


class Speech:
    _shared: 'Speech | None' = None

    @classmethod
    def shared(cls) -> 'Speech':
        if cls._shared is None:
            cls._shared = Speech()
        return cls._shared

    def __init__(self):
        if host.MAC:
            from .macspeech import VoiceOver
            self.nvda = VoiceOver()                       # the screen reader spoken to directly
        else:
            self.nvda = _Nvda()
        self._readers = None
        self._sapi = None
        self.choice = 'auto'                              # Speech output (OUTPUTS), set from the settings
        self.sapi_config = dict(SAPI_DEFAULTS)            # SAPI 5's voice and the rest, likewise
        self._silent = False                              # the chosen one could not speak the last line

    @property
    def readers(self) -> _Readers:
        if self._readers is None:
            self._readers = _NoReaders() if host.MAC else _Readers()
        return self._readers

    @property
    def sapi(self) -> _Sapi:
        if self._sapi is None:
            if host.MAC:
                from .macspeech import SystemVoice
                self._sapi = SystemVoice()
            else:
                self._sapi = _Sapi()
            self._sapi.configure(**self.sapi_config)
        return self._sapi

    def configure_sapi(self, **config) -> None:
        """SAPI 5's voice, rate, boost, pitch and volume (SAPI_DEFAULTS), from the settings."""
        self.sapi_config = dict(SAPI_DEFAULTS, **config)
        configure = getattr(self._sapi, 'configure', None)
        if configure is not None:
            configure(**self.sapi_config)

    def screen_reader_running(self) -> bool:
        """UIAccessibilityIsVoiceOverRunning() equivalent: always, in the port.

        The original takes its VoiceOver branches - the accessible screens, the spoken game view, Button
        mode on a new profile - only while VoiceOver is on; the other branches are its sighted game, which
        the port has not ported, since it has nothing to look at.  Every screen here is spoken - by NVDA,
        by another screen reader through Prism, or by SAPI 5 - so the VoiceOver branches are always the ones
        taken.  This used to ask whether NVDA was running, which sent a player on SAPI 5 down the sighted
        path: "ADChallengeSelectorViewController is not ported yet" on opening a world's challenges, and
        a game that was not described."""
        return True

    def speak(self, text, interrupt: bool = True) -> None:
        if not text:
            return
        text = str(text)
        log.debug('speak: %s', text)
        choice = self.choice
        if choice not in PRISM_NAMES and choice not in (SCREEN_READER, 'sapi'):
            self.speak_automatic(text, interrupt)
            return
        if choice == SCREEN_READER:
            spoken = self.nvda.speak(text, interrupt)
        elif choice == 'sapi':
            spoken = self.sapi.speak(text, interrupt)
        else:
            spoken = self.readers.speak(text, interrupt, PRISM_NAMES[choice])
        if spoken == self._silent:                        # said once, as it starts or stops
            self._silent = not spoken
            log.info('speech: %s %s', dict(OUTPUTS)[choice],
                     'is not running: the game is silent until it is' if self._silent else 'speaks again')

    def speak_automatic(self, text, interrupt: bool = True) -> None:
        """The first of NVDA, another screen reader and SAPI 5 that can speak, whatever Speech output says.
        The game speaks this way on Automatic, and Settings says through it that a chosen screen reader
        is not running, which it could not say through that one."""
        if self.nvda.speak(text, interrupt):
            return
        if self.readers.speak(text, interrupt):
            return
        self.sapi.speak(text, interrupt)

    def automatic_output(self) -> str:
        """What Automatic speaks through right now, without speaking: 'nvda' ('voiceover' on the Mac),
        another screen reader's Prism name, or 'sapi'."""
        if self.nvda.running():
            return SCREEN_READER
        reader = self.readers.current()
        return reader.name if reader is not None else 'sapi'

    def can_speak(self, choice: str) -> bool:
        """Whether this Speech output choice can speak right now."""
        if choice == 'auto':
            return True
        if choice == SCREEN_READER:
            return self.nvda.running()
        if choice == 'sapi':
            return self.sapi.voice is not None
        return self.readers.current(PRISM_NAMES.get(choice)) is not None

    def stop(self) -> None:
        choice = self.choice
        if choice == SCREEN_READER:
            if self.nvda.running():
                self.nvda.stop()
        elif choice == 'sapi':
            if self._sapi is not None:
                self._sapi.stop()
        elif choice in PRISM_NAMES:
            if self._readers is not None:
                self._readers.stop()
        elif self.nvda.running():
            self.nvda.stop()
        elif self._readers is not None and self._readers.reader is not None:
            self._readers.stop()
        elif self._sapi is not None:
            self._sapi.stop()
