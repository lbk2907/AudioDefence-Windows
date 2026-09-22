"""PORT ADDITION: speech on the Mac - VoiceOver, and the system voice when VoiceOver is off.

The Windows build speaks through NVDA, the other screen readers and SAPI 5 (platform/speech.py).  On the
Mac the same two roles are VoiceOver and the system's own voice, both through pyobjc:

* **VoiceOver**, by ``tell application "VoiceOver" to output "..."`` through NSAppleScript, which speaks
  in the player's own VoiceOver voice and settings and shows the line on a braille display.  An Apple
  Event can take a tenth of a second or more, which would stall the game's frame, so lines are handed to
  a thread of their own; an interrupting line throws away whatever is still waiting.  The first line is
  sent from the main thread, to learn whether the Apple Event is allowed at all.  It is not until the
  player ticks "Allow VoiceOver to be controlled with AppleScript" in VoiceOver Utility, and macOS has
  asked once whether the game may control VoiceOver (errAEEventNotPermitted, -1743); until then the line
  is posted as an accessibility announcement on the game's window instead, which VoiceOver reads while
  the window has focus.
* **The system voice**, NSSpeechSynthesizer: what Spoken Content in System Settings speaks with, or any
  installed voice, at the player's rate, pitch and volume.  It stands where SAPI 5 stands on Windows -
  the voice for a player with no screen reader running - and presents the same methods, so Settings ->
  Speech drives either without knowing which it has.

The C# accessibility mod's ``VoiceOverOutput`` did the same three things in the same order, and Papa
Sangre's Mac port uses it (papasangre/accessibility/voiceover.py); this is that, threaded.
"""
from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger('speech')

#: NSAppleScriptErrorNumber when the game may not send Apple Events to VoiceOver
ERR_AE_EVENT_NOT_PERMITTED = -1743
#: NSAccessibilityPriorityHigh, for the window announcement
ANNOUNCEMENT_PRIORITY = 90


def _frameworks() -> bool:
    try:
        import AppKit                                     # noqa: F401
        import Foundation                                 # noqa: F401
        return True
    except ImportError:
        return False


def _escape(text: str) -> str:
    """An AppleScript string literal's inside: backslashes, then quotes."""
    return str(text).replace('\\', '\\\\').replace('"', '\\"')


def _run_script(source: str) -> tuple:
    """(ran, error number or None) for one AppleScript."""
    import Foundation
    script = Foundation.NSAppleScript.alloc().initWithSource_(source)
    if script is None:
        return False, None
    result, error = script.executeAndReturnError_(None)
    if result is not None:
        return True, None
    number = None
    try:
        number = int(error.get('NSAppleScriptErrorNumber')) if error else None
    except (TypeError, ValueError, AttributeError):
        pass
    return False, number


class VoiceOver:
    """VoiceOver, spoken to by Apple Event, or by accessibility announcement when that is not allowed."""

    def __init__(self):
        self.available = _frameworks()
        self.apple_events = None                          # None until the first line says whether they work
        self._queue: queue.Queue = queue.Queue()
        self._thread = None

    def running(self) -> bool:
        """NSWorkspace's accessibilityDisplayOptions' VoiceOver switch: is VoiceOver on?"""
        if not self.available:
            return False
        try:
            from AppKit import NSWorkspace
            return bool(NSWorkspace.sharedWorkspace().isVoiceOverEnabled())
        except Exception:
            return False

    def speak(self, text: str, interrupt: bool) -> bool:
        if not self.running():
            return False
        if self.apple_events is None:                     # the first line: find out, on this thread
            ran, error = _run_script('tell application "VoiceOver" to output "%s"' % _escape(text))
            self.apple_events = ran
            if not ran:
                log.info('speech: VoiceOver will not take Apple Events (%s), so lines are announced on the '
                         "game's window instead. Allow VoiceOver to be controlled with AppleScript, in "
                         'VoiceOver Utility, for the better route', error)
                return self._announce(text)
            log.info('speech: VoiceOver, by Apple Event')
            return True
        if not self.apple_events:
            return self._announce(text)
        if interrupt:
            self._drain()
        self._start()
        self._queue.put(text)
        return True

    def stop(self) -> None:
        self._drain()
        if self.apple_events:
            self._start()
            self._queue.put('')                           # an empty output stops what VoiceOver is saying

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._worker, name='voiceover', daemon=True)
            self._thread.start()

    def _worker(self) -> None:
        try:
            from Foundation import NSAutoreleasePool
        except ImportError:
            return
        while True:
            text = self._queue.get()
            pool = NSAutoreleasePool.alloc().init()
            try:
                ran, error = _run_script('tell application "VoiceOver" to output "%s"' % _escape(text))
                if not ran and text:
                    log.info('speech: VoiceOver did not take a line (%s)', error)
            except Exception:
                log.exception('speech: VoiceOver')
            finally:
                del pool

    @staticmethod
    def _announce(text: str) -> bool:
        """NSAccessibilityPostNotificationWithUserInfo on the game's window: what VoiceOver reads when the
        Apple Event is refused.  AppKit, so the main thread only."""
        try:
            import AppKit
            from Foundation import NSDictionary
            app = AppKit.NSApplication.sharedApplication()
            window = app.keyWindow() or app.mainWindow() or (app.windows() or [None])[0]
            if window is None:
                return False
            info = NSDictionary.dictionaryWithDictionary_({
                AppKit.NSAccessibilityAnnouncementKey: str(text),
                AppKit.NSAccessibilityPriorityKey: ANNOUNCEMENT_PRIORITY})
            AppKit.NSAccessibilityPostNotificationWithUserInfo(
                window, AppKit.NSAccessibilityAnnouncementRequestedNotification, info)
            return True
        except Exception as exc:
            log.info('speech: VoiceOver announcement failed: %s', exc)
            return False


class SystemVoice:
    """NSSpeechSynthesizer with the player's voice, rate, pitch and volume: the Mac's SAPI 5.

    It answers to the same calls as speech.py's _Sapi, in the same units, so Settings -> Speech works on
    either.  Rate runs -10 to 10, each step a tenth faster or slower than the system's own rate; pitch runs
    -10 to 10 around the voice's own, each step a twentieth; volume is 0 to 100.  A voice, rate or volume
    of None is the system's (Spoken Content in System Settings).  There is no rate boost: a Mac voice goes
    as fast as its rate says, so boost_supported is always False and the row is never shown."""

    DEFAULT_NAME = 'System default'

    def __init__(self):
        self.voice = None                                 # the synthesizer; None where there is none
        self.config = {'voice': None, 'rate': None, 'boost': False, 'pitch': 0, 'volume': None}
        self._voices = None
        self._pending = []                                # lines waiting for the one being said
        self._pumping = False
        self.panel_rate = 175.0
        self.panel_pitch = None
        try:
            from AppKit import NSSpeechPitchBaseProperty, NSSpeechSynthesizer
            self._pitch_key = NSSpeechPitchBaseProperty
            self.voice = NSSpeechSynthesizer.alloc().initWithVoice_(None)
            self.panel_rate = float(self.voice.rate()) or 175.0
            self.panel_pitch = self._read_pitch()
        except Exception as exc:
            log.info('system voice not available: %s', exc)
            self.voice = None

    def _read_pitch(self):
        try:
            value, _error = self.voice.objectForProperty_error_(self._pitch_key, None)
            return float(value) if value is not None else None
        except Exception:
            return None

    def voices(self) -> list:
        """(identifier, name) for every installed voice, in the system's order."""
        if self._voices is None:
            self._voices = []
            if self.voice is not None:
                from AppKit import NSSpeechSynthesizer
                for identifier in NSSpeechSynthesizer.availableVoices():
                    attributes = NSSpeechSynthesizer.attributesForVoice_(identifier) or {}
                    self._voices.append((str(identifier), str(attributes.get('VoiceName') or identifier)))
        return self._voices

    def configure(self, voice=None, rate=None, boost=False, pitch=0, volume=None) -> None:
        self.config = {'voice': voice, 'rate': rate, 'boost': bool(boost), 'pitch': int(pitch or 0),
                       'volume': volume}
        if self.voice is None:
            return
        try:
            from AppKit import NSSpeechSynthesizer
            wanted = voice if voice in dict(self.voices()) else NSSpeechSynthesizer.defaultVoice()
            if str(self.voice.voice() or '') != str(wanted):
                self.voice.setVoice_(wanted)              # a new voice starts at its own pitch
                self.panel_pitch = self._read_pitch()
            self.voice.setRate_(self.panel_rate * (1.1 ** self.rate()) if rate is not None else self.panel_rate)
            self.voice.setVolume_(self.volume() / 100.0)
            if self.panel_pitch is not None:
                self.voice.setObject_forProperty_error_(self.panel_pitch * (1.05 ** self.config['pitch']),
                                                        self._pitch_key, None)
        except Exception as exc:
            log.info('system voice settings not applied: %s', exc)

    def rate(self) -> int:
        rate = self.config['rate']
        return 0 if rate is None else max(-10, min(10, int(rate)))

    def volume(self) -> int:
        volume = self.config['volume']
        return 100 if volume is None else max(0, min(100, int(volume)))

    def boost_supported(self, voice_id=None) -> bool:
        return False

    def speak(self, text: str, interrupt: bool) -> bool:
        if self.voice is None:
            return False
        if interrupt or not (self.voice.isSpeaking() or self._pending):
            self._pending = []
            self.voice.stopSpeaking()
            return bool(self.voice.startSpeakingString_(str(text)))
        # NSSpeechSynthesizer has no queue: a line that does not interrupt waits for the one being said
        self._pending.append(str(text))
        if not self._pumping:
            self._pumping = True
            self._pump()
        return True

    def _pump(self) -> None:
        from .runloop import RunLoop
        if not self._pending:
            self._pumping = False
            return
        if not self.voice.isSpeaking():
            self.voice.startSpeakingString_(self._pending.pop(0))
        RunLoop.main().call_later(0.05, self._pump)

    def stop(self) -> None:
        self._pending = []
        if self.voice is not None:
            self.voice.stopSpeaking()
