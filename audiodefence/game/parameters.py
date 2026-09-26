"""ADGameParameters - the settings singleton (NSUserDefaults backed)."""
from __future__ import annotations

import time

from ..platform import crand
from ..platform.defaults import UserDefaults

GYRO, SWIPE, TILT = 1, 2, 3


class GameParameters:
    _shared: 'GameParameters | None' = None
    #: UIAccessibilityIsVoiceOverRunning() equivalent: always, in the port (platform/speech.py
    #: Speech.screen_reader_running, which __main__ copies here).  Nothing reads it since a fresh profile
    #: started choosing Gesture for itself (DEFAULT_BUTTON_MODE); it is what the original asked there.
    screen_reader_running = True

    @classmethod
    def shared(cls) -> 'GameParameters':    # +[ADGameParameters sharedParameters] 0x1000a3878
        if cls._shared is None:
            cls._shared = GameParameters()
        return cls._shared

    def __init__(self):                     # -[ADGameParameters init] 0x1000a360c
        self.defaults = UserDefaults.standard()
        self.current_level = None
        self.playlist_name = None
        self.last_challenge_world = None
        self._control_scheme = -1
        self._button_mode = False
        self._sensivity = 0.0
        self._debug_map_visible = False
        self.set_control_scheme(self.last_control_scheme())
        self.endless_mode = False
        self.set_button_mode(self.last_button_mode())
        self.set_sensivity(self.last_sensivity())
        self.set_debug_map_visible(self.last_debug_map_visible())
        crand.srand(int(time.time()))

    # --- control scheme --------------------------------------------------------------------------
    @property
    def control_scheme(self) -> int:
        return self._control_scheme

    def set_control_scheme(self, value: int) -> None:      # 0x1000a40fc
        self.defaults.set_integer(value, 'controlScheme')
        self.defaults.synchronize()
        self._control_scheme = int(value)

    def last_control_scheme(self) -> int:                 # 0x1000a44e8
        v = self.defaults.object('controlScheme')
        if v is None:
            # PORT CHOICE: the original answers -1 with nothing stored, which sends the first launch to
            # ADInitialControlSchemeViewController - and that screen hides its Gyro button while a screen
            # reader runs (the gyroTextButton outlet points at the button itself), so Gyro could never be
            # picked there.  The port starts on Gyro instead; Settings -> Aiming still offers all three.
            return 1
        return self.defaults.integer('controlScheme')

    # --- button mode -----------------------------------------------------------------------------
    @property
    def button_mode(self) -> bool:
        return self._button_mode

    def set_button_mode(self, value: bool) -> None:        # 0x1000a3a50
        self._button_mode = bool(value)
        self.defaults.set_bool(self._button_mode, 'buttonMode')
        self.defaults.synchronize()

    #: DIVERGENCE: what a fresh profile plays in.  The original asks VoiceOver (0x1000a3aec), which puts
    #: every blind player in Button mode; the port starts in Gesture instead (user request).  Only a
    #: profile with nothing stored is affected: the mode is written the first time the game runs, so
    #: anyone who has played keeps what they had, whether they chose it or the original chose it for them.
    DEFAULT_BUTTON_MODE = False

    def last_button_mode(self) -> bool:                   # 0x1000a3aec
        if self.defaults.object('buttonMode') is not None:
            return self.defaults.bool('buttonMode')
        return self.DEFAULT_BUTTON_MODE

    # --- sensitivity -----------------------------------------------------------------------------
    @property
    def sensivity(self) -> float:
        return self._sensivity

    #: the sensitivity Settings -> Aiming steps through, and the value a fresh profile starts on
    SENSIVITY_STEPS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
    DEFAULT_SENSIVITY = 1.5

    def set_sensivity(self, value: float) -> None:         # 0x1000a419c
        # DIVERGENCE: the original stores the slider's value with setInteger:, so its 1.5 default comes back
        # as 1 on the next launch.  The port's Aiming category can set it, so it is stored as a float.
        self.defaults.set_float(float(value), 'sensivity')
        self.defaults.synchronize()
        self._sensivity = float(value)

    def turn_speed_factor(self) -> float:
        """PORT INPUT: the gyro and swipe turn rates are the port's own, chosen at the default sensitivity,
        so the setting scales them the way it scales the original's tilt formula."""
        return float(self._sensivity) / self.DEFAULT_SENSIVITY

    def last_sensivity(self) -> float:                    # 0x1000a423c
        if self.defaults.object('sensivity') is not None:
            return self.defaults.float('sensivity')
        self.set_sensivity(self.DEFAULT_SENSIVITY)
        return self._sensivity

    # --- debug map -------------------------------------------------------------------------------
    @property
    def debug_map_visible(self) -> bool:
        return self._debug_map_visible

    def set_debug_map_visible(self, value: bool) -> None:  # 0x1000a435c
        self.defaults.set_integer(int(bool(value)), 'debugMapVisible')
        self.defaults.synchronize()
        self._debug_map_visible = bool(value)

    def last_debug_map_visible(self) -> bool:
        if self.defaults.object('debugMapVisible') is None:
            return False
        return self.defaults.float('debugMapVisible') != 0.0

    # --- master gain -----------------------------------------------------------------------------
    def set_master_gain(self, gain: float) -> None:        # 0x1000a3ba0
        from ..s3d.engine import S3DEngine
        S3DEngine.engine().set_master_gain(gain)
        self.defaults.set_float(gain, 'masterGain')
        self.defaults.synchronize()

    def last_master_gain(self) -> float:                  # 0x1000a3ca0
        v = self.defaults.float('masterGain')
        if v == 0.0:
            self.set_master_gain(1.0)
            return 1.0
        return v

    # --- announcer -------------------------------------------------------------------------------
    def set_announcer(self, value: bool) -> None:          # 0x1000a3da4
        self.defaults.set_bool(value, 'announcer')
        self.defaults.synchronize()

    def last_announcer_value(self) -> bool:               # 0x1000a3e60
        if self.defaults.object('announcer') is None:
            return True
        return self.defaults.bool('announcer')

    # --- menu arrows -----------------------------------------------------------------------------
    #: PORT ADDITION: which pair of arrow keys moves through a screen's elements.  The original is driven
    #: by VoiceOver's swipes, which have no direction to choose, so none of this comes from it.
    MENU_AXES = (('horizontal', 'Left and Right'), ('vertical', 'Up and Down'))
    DEFAULT_MENU_AXIS = 'horizontal'

    def menu_axis(self) -> str:
        value = self.defaults.object('menuAxis')
        return value if value in dict(self.MENU_AXES) else self.DEFAULT_MENU_AXIS

    def set_menu_axis(self, value: str) -> None:
        self.defaults.set_object(value, 'menuAxis')
        self.defaults.synchronize()

    #: PORT ADDITION: whether the tutorial announcer's lines are also spoken as text, and when.  The
    #: announcer tells you to tilt, swipe or tap a corner of a phone; the spoken line names your keys.
    TUTORIAL_TEXT_MODES = (('with', 'As the announcer speaks'),
                           ('after', 'After the announcer finishes'),
                           ('off', 'Off'))
    DEFAULT_TUTORIAL_TEXT = 'with'

    def tutorial_text_mode(self) -> str:
        value = self.defaults.object('tutorialText')
        return value if value in dict(self.TUTORIAL_TEXT_MODES) else self.DEFAULT_TUTORIAL_TEXT

    def set_tutorial_text_mode(self, value: str) -> None:
        self.defaults.set_object(value, 'tutorialText')
        self.defaults.synchronize()

    #: PORT ADDITION: whether going back to a screen puts the cursor where you left it.  Off by default:
    #: the original rebuilds the screen and starts at the first element every time.
    DEFAULT_REMEMBER_FOCUS = False

    def remember_focus(self) -> bool:
        value = self.defaults.object('rememberFocus')
        return self.DEFAULT_REMEMBER_FOCUS if value is None else bool(value)

    def set_remember_focus(self, value: bool) -> None:
        self.defaults.set_bool(bool(value), 'rememberFocus')
        self.defaults.synchronize()

    #: PORT ADDITION: whether the main menu looks for a new build when it opens.  The App Store did this
    #: for the phone game; on Windows the game has to ask.  On by default, because a player who never
    #: opens Settings is exactly the one who would otherwise never hear that a fix exists.  The check is
    #: one call to GitHub on a worker thread, and it says nothing at all unless there is an update.
    DEFAULT_CHECK_UPDATES = True

    def check_updates(self) -> bool:
        value = self.defaults.object('checkUpdates')
        return self.DEFAULT_CHECK_UPDATES if value is None else bool(value)

    def set_check_updates(self, value: bool) -> None:
        self.defaults.set_bool(bool(value), 'checkUpdates')
        self.defaults.synchronize()

    #: PORT ADDITION: how loud the menu music is, in percent - the three sounds of the main_menu playlist
    #: (the theme, the game-over theme, which is the same music, and the opening sting), not the music
    #: or the ambience of a game.  The original has no volume of its own: the phone's buttons set all of
    #: it at once.
    MENU_MUSIC_VOLUMES = tuple(range(0, 101, 10))
    DEFAULT_MENU_MUSIC_VOLUME = 100

    def menu_music_volume(self) -> int:
        value = self.defaults.object('menuMusicVolume')
        return value if value in self.MENU_MUSIC_VOLUMES else self.DEFAULT_MENU_MUSIC_VOLUME

    def set_menu_music_volume(self, value: int) -> None:
        self.defaults.set_object(int(value), 'menuMusicVolume')
        self.defaults.synchronize()

    def menu_music_gain(self) -> float:
        """The percentage as a gain, squared so that each step sounds about as big as the last: straight
        percentages barely change anything near the top and drop to nothing in the last step or two."""
        return (self.menu_music_volume() / 100.0) ** 2

    #: PORT ADDITION: how strongly a game controller vibrates (platform/haptics.py), and how stiff a
    #: DualSense's triggers are in play (platform/pad.py): off, light, medium or strong.  Medium by default:
    #: a player holding a controller that can do either expects it to, and not to be shaken out of it.  An
    #: older settings file kept these as on and off, which read as medium and off.
    FEEL_LEVELS = (('off', 'Off'), ('light', 'Light'), ('medium', 'Medium'), ('strong', 'Strong'))
    DEFAULT_VIBRATION = 'medium'
    DEFAULT_TRIGGER_FEEL = 'medium'

    def _level(self, key: str, default: str) -> str:
        value = self.defaults.object(key)
        if value is True:
            return default
        if value is False:
            return 'off'
        return value if value in dict(self.FEEL_LEVELS) else default

    def vibration_level(self) -> str:
        return self._level('vibration', self.DEFAULT_VIBRATION)

    def set_vibration_level(self, level: str) -> None:
        self.defaults.set_object(level, 'vibration')
        self.defaults.synchronize()

    def vibration(self) -> bool:
        return self.vibration_level() != 'off'

    def trigger_level(self) -> str:
        return self._level('triggerEffects', self.DEFAULT_TRIGGER_FEEL)

    def set_trigger_level(self, level: str) -> None:
        self.defaults.set_object(level, 'triggerEffects')
        self.defaults.synchronize()

    #: PORT ADDITION: whether the hints, the tutorial text and the other lines that name a key name the
    #: keyboard's keys or the connected controller's buttons (platform/pad.menu_words,
    #: game/tutorial_text.py).  With no controller connected - at startup, or when the last one goes - it
    #: goes back to keys (Pads._keys_when_none).  Keys by default, as they always did.
    KEY_NAMES = (('keys', 'Keyboard keys'), ('buttons', 'Controller buttons'))
    DEFAULT_KEY_NAMES = 'keys'

    def key_names(self) -> str:
        value = self.defaults.object('keyNames')
        return value if value in dict(self.KEY_NAMES) else self.DEFAULT_KEY_NAMES

    def set_key_names(self, value: str) -> None:
        self.defaults.set_object(value, 'keyNames')
        self.defaults.synchronize()

    #: PORT ADDITION: Settings -> Miscellaneous -> Fine haptics: whether a controller that has them plays
    #: what you feel in its grips (a DualSense over USB) or through its motors like any other pad.  On by
    #: default; with no such controller connected the motors are used whatever this says.
    DEFAULT_FINE_HAPTICS = True

    def fine_haptics(self) -> bool:
        value = self.defaults.object('fineHaptics')
        return self.DEFAULT_FINE_HAPTICS if value is None else self.defaults.bool('fineHaptics')

    def set_fine_haptics(self, value: bool) -> None:
        self.defaults.set_bool(bool(value), 'fineHaptics')
        self.defaults.synchronize()

    #: PORT ADDITION: Settings -> Miscellaneous -> Language: the language the port's own text is shown and
    #: spoken in (audiodefence/localization.py, localization/<code>.json).  English by default, so a player
    #: who does not choose one sees exactly what the port always showed.
    LANGUAGES = (('en', 'English'), ('ru', 'Русский'))
    DEFAULT_LANGUAGE = 'en'

    def language(self) -> str:
        value = self.defaults.object('language')
        return value if value in dict(self.LANGUAGES) else self.DEFAULT_LANGUAGE

    def set_language(self, value: str) -> None:
        from ..localization import load                   # here: localization asks this module for it
        self.defaults.set_object(value, 'language')
        self.defaults.synchronize()
        load(value, force=True)                           # every caller takes effect, not only Settings

    #: PORT ADDITION: Settings -> Speech -> Use modern output: whether the game plays what SAPI 5 says
    #: through its own sound (platform/speech_audio.py), where a line stops the instant it is interrupted,
    #: or hands it to Windows as it always did, where what is already buffered plays on.  On by default, and
    #: the name is NVDA's, whose players know it from their own settings.
    DEFAULT_MODERN_AUDIO = True

    def modern_audio(self) -> bool:
        value = self.defaults.object('sapiModernAudio')
        return self.DEFAULT_MODERN_AUDIO if value is None else self.defaults.bool('sapiModernAudio')

    def set_modern_audio(self, value: bool) -> None:
        self.defaults.set_bool(bool(value), 'sapiModernAudio')
        self.defaults.synchronize()

    #: PORT ADDITION: Settings -> Miscellaneous -> Speech output: Automatic, or one screen reader or voice
    #: only (platform/speech.py OUTPUTS).  Automatic by default, as it always was.
    DEFAULT_SPEECH_OUTPUT = 'auto'

    def speech_output(self) -> str:
        from ..platform.speech import OUTPUTS
        value = self.defaults.object('speechOutput')
        return value if value in dict(OUTPUTS) else self.DEFAULT_SPEECH_OUTPUT

    def set_speech_output(self, value: str) -> None:
        from ..platform.speech import Speech
        self.defaults.set_object(value, 'speechOutput')
        self.defaults.synchronize()
        Speech.shared().choice = self.speech_output()

    #: PORT ADDITION: Settings -> Miscellaneous -> SAPI 5 voice, rate, rate boost, pitch and volume
    #: (platform/speech.py _Sapi).  Nothing stored is Control Panel's voice, rate and volume.
    SAPI_KEYS = {'voice': 'sapiVoice', 'rate': 'sapiRate', 'boost': 'sapiRateBoost', 'pitch': 'sapiPitch',
                 'volume': 'sapiVolume'}

    def sapi_config(self) -> dict:
        voice = self.defaults.object('sapiVoice')
        rate = self.defaults.object('sapiRate')
        pitch = self.defaults.object('sapiPitch')
        volume = self.defaults.object('sapiVolume')
        return {'voice': voice if isinstance(voice, str) and voice else None,
                'rate': max(-10, min(10, int(rate))) if isinstance(rate, (int, float)) else None,
                'boost': self.defaults.object('sapiRateBoost') is True,
                'pitch': max(-10, min(10, int(pitch))) if isinstance(pitch, (int, float)) else 0,
                'volume': max(0, min(100, int(volume))) if isinstance(volume, (int, float)) else None}

    def set_sapi(self, **changes) -> None:
        """Change some of them - None (or False, 0 for pitch) puts one back - and tell the voice."""
        from ..platform.speech import Speech
        for key, value in changes.items():
            # compared by identity: 0 == False, and a rate or volume of 0 is a setting, not Control Panel's
            unset = value is None or value is False or (key == 'pitch' and value == 0)
            self.defaults.set_object(None if unset else value, self.SAPI_KEYS[key])
        self.defaults.synchronize()
        Speech.shared().configure_sapi(**self.sapi_config())

    def names_controller(self):
        """The connected controller whose buttons the lines name, by the name it gives itself - the one
        chosen when several kinds are connected, else the one connected last - or None to name keys."""
        if self.key_names() != 'buttons':
            return None
        from ..platform.pad import Pads
        models = Pads.shared().connected_models()
        if not models:
            return None
        chosen = self.defaults.object('keyNamesController')
        return chosen if chosen in models else models[-1]

    def set_names_controller(self, model) -> None:
        self.defaults.set_object(model, 'keyNamesController')
        self.defaults.synchronize()

    def controller_names(self):
        """The names to use for that controller's buttons - 'playstation', 'xbox', 'nintendo' or
        'generic' (pad.NAMES) - or None to name keys."""
        model = self.names_controller()
        if model is None:
            return None
        from ..platform.pad import family
        return family(model)

    #: The version the player answered "no" to, so the same build is not offered at every launch.  Asking
    #: again for a *newer* build is right, so this stores which one was refused rather than a flag.
    def skipped_update(self) -> str:
        value = self.defaults.object('skippedUpdate')
        return str(value) if value else ''

    def set_skipped_update(self, tag: str) -> None:
        self.defaults.set_object(str(tag), 'skippedUpdate')
        self.defaults.synchronize()

    # --- roulette free roll ----------------------------------------------------------------------
    def set_last_good_news(self, unix_time: float) -> None:  # 0x1000a3f44
        self.defaults.set_date(unix_time, 'lastGoodNews')
        self.defaults.synchronize()

    def time_since_last_good_news(self) -> float:           # 0x1000a4010: timeIntervalSinceNow (negative)
        t = self.defaults.date('lastGoodNews')
        if t is None:
            t = -63114076800.0                                  # [NSDate distantPast] (year 1)
        return t - time.time()

    # --- audio route -----------------------------------------------------------------------------
    @staticmethod
    def is_headset_plugged_in() -> bool:                    # 0x1000a45d0
        """The original asks the audio session for its route and looks for "Head" in it.
        PORT CHOICE: Windows has no dependable way to tell headphones from speakers (USB and Bluetooth
        devices report many form factors), so the port answers YES and the "Wear headphones" alert of the
        main menu's Play button is not shown."""
        return True
