"""Settings and pause, with their shared options panel.

    ADSettingsViewController : ADViewController          (presented from the main menu)
    ADPauseViewController    : ADSettingsViewController   (presented over the gameplay)
    Accessible_ADControlSchemeViewController : ADControlSchemeViewController  (the table both of them show)

-[ADSettingsViewController addControlSchemePanel] 0x1000af5b8 builds the accessible control scheme while
VoiceOver runs, posts UIAccessibilityScreenChangedNotification with its table and centres its view on the
settings nib's controlSchemeView.

PORT UI: the original's accessible table is one long list under "Aiming", "Controls" and "Sound" headings
(its sighted twin, ADControlSchemeViewController, has those three as tabs).  The port shows one heading at a
time - the screen opens inside Aiming, and the arrows the menu navigation is not using change category, as
the armory's tabs do - and adds two categories' worth of things the accessible table never had: the turn
sensitivity (a sighted-only slider in the original) and the key bindings (the port's own, since the original
is touch driven).  Every change is spoken.
"""
from __future__ import annotations

import logging
import time

import pygame

from ..app import App
from ..game import data
from ..game.parameters import GameParameters
from ..platform import host as system
from ..platform.keymap import ACTIONS, BY_MODE, KeyMap, key_text, mode_text
from ..platform.speech import VOICE_NAME
from ..s3d.engine import S3DEngine
from .accessibility import (CELL, Button, View, cross_axis_key, cross_axis_text, menu_tick,
                            play_button_click)
from .challenges import _TableLoader, _play_buttons_sound
from .host import register
from .viewcontroller import ViewControllerScreen

log = logging.getLogger('ui.settings')

#: where the voice starts, before one is chosen: what Settings -> Speech's voice row says it defaults to
VOICE_DEFAULT_HINT = ('the one set in Spoken Content, in System Settings' if system.MAC else
                      'the one set in Control Panel')


def _headphones_playlist():
    return S3DEngine.engine().play_list_with_name('headphonesTest')


# PORT INPUT: the original's descriptions (GYRO_DESCRIPTION, SWIPE_DESCRIPTION, TILT_DESCRIPTION) tell the
# player to turn the device, swipe or tilt it.  All three are the turn keys here, so what actually separates
# them is how fast they turn - the three code paths run at different rates - and the rows say only which is
# which.  The degrees a second are in the README, where they can be read rather than sat through on every
# pass of the list; Turn sensitivity scales all three in proportion.
AIMING_ROWS = (('Gyro', 'Turns slowest', 1),
               ('Swipe', 'Turns in between', 2),
               ('Tilt', 'Turns fastest', 3))

# BUTTON_MODE / GESTURE_MODE describe where to tap and how to swipe; the port's keys do both, so the rows
# say what the mode changes for a keyboard player instead - with the keys bound in that mode, or the
# buttons, when a controller's names are chosen (Settings -> Miscellaneous).
CONTROL_ROWS = (('Button', True), ('Gesture', False))


def control_description(button: bool) -> str:
    mode = 'button' if button else 'gesture'
    switch, reload = _mode_words('next_weapon', mode), _mode_words('reload', mode)
    if GameParameters.shared().controller_names():
        if button:
            return ('Your controller presses the four corner buttons of the phone layout, so %s switches '
                    'weapon and %s reloads' % (switch, reload))
        return ('Your controller taps and swipes anywhere on the screen, so %s switches weapon and %s '
                'reloads' % (switch, reload))
    if button:
        return ('Your keys press the four corner buttons of the phone layout, so %s switches weapon and %s '
                'reloads' % (switch, reload))
    return 'Your keys tap and swipe anywhere on the screen, so %s switches weapon and %s reloads' % (switch,
                                                                                                     reload)


def _mode_words(action: str, mode: str) -> str:
    """An action's keys in a control scheme - or its buttons, when a controller's names are chosen."""
    if GameParameters.shared().controller_names():
        from ..platform.pad import button_words
        return button_words(action, mode) or 'no button'
    return KeyMap.shared().keys_text(action, mode)

# PORT UI: Speech holds who speaks the game - Speech output - and SAPI 5's own voice while SAPI 5 is what
# speaks.  Keyboard holds the key bindings alone, and Joystick a game controller's buttons.  Miscellaneous is
# last and holds the rest: how the cursor moves through a screen, when the tutorial's lines are shown as
# text and what they name, how a controller vibrates and how a DualSense's triggers feel, whether the game
# looks for updates, and the one button that puts every setting back.
CATEGORIES = (('aiming', 'Aiming'), ('controls', 'Controls'), ('sound', 'Sound'), ('speech', 'Speech'),
              ('keyboard', 'Keyboard'), ('joystick', 'Joystick'), ('misc', 'Miscellaneous'))
PAD_BINDING_HINT = ('Press Enter to add a button, Shift Enter to replace them all, '
                    'Delete to remove the last one.')
SELECT_HINT = 'Press Enter to select.'


class ControlSchemePanel:
    """Accessible_ADControlSchemeViewController (nib view #21, table #13 at 440x244), as categories."""

    def __init__(self, screen, parent: View, center):
        self.screen = screen
        self.category = CATEGORIES[0][0]                  # settings open inside a category, not on a list
        self.capturing = None                             # the action waiting for its new key
        self.capturing_replaces = False                   # Shift+Enter: the new key replaces the others
        self.pad_capturing = None                         # the action waiting for a controller button
        self.pad_capturing_replaces = False
        self.pad_capturing_model = None                   # and the controller whose profile it goes to
        self.sapi_shown = False                           # Speech: whether SAPI 5's rows are listed
        self.choosing = None                              # a row's choices, shown as a list of their own
        self._trigger_sample = None                       # the Trigger feel being tried on the pad
        self._speech_due = 0.0
        frame = (center[0] - 220.0, center[1] - 122.0, 440.0, 244.0)
        self.view = View('', frame, accessible=False, parent=parent, name='#21')
        self.table_view = View('', frame, accessible=False, parent=self.view, ordered=True, name='#13')
        self.reload_data()

    # --- rows ------------------------------------------------------------------------------------
    def reload_data(self) -> None:
        if self.choosing is not None:                     # a row's own choices are the list just now
            self._load_choices()
            return
        params = GameParameters.shared()
        t = _TableLoader(self.table_view)
        # The original's accessible table is one list under "Aiming", "Controls" and "Sound" headings; the
        # port shows one category at a time and changes it with the arrows the navigation is not using.
        # The category is said as it opens (and as the screen opens), like the armory's tabs, so it is not
        # kept as a row of its own.
        if self.category == 'aiming':                     # cellForAimingAtIndex: 0x1000b5734
            for title, description, scheme in AIMING_ROWS:
                cell = t.cell(title, description, hint=SELECT_HINT,
                              action=lambda s=scheme: self.select_control_scheme(s))
                cell.selected = params.control_scheme == scheme     # selectRowAtIndexPath:
            # the value is a bare multiplier - sensivity * angle in the gyro path 0x10005a108, sensivity *
            # dx in the drag path 0x10005a3e0 - with no unit of its own.  The row reads it alone; the range
            # and what it works out to in degrees a second are in the README.
            t.cell('Turn sensitivity', self.sensitivity_text(),
                   hint='Press Enter for the next value, Shift plus Enter for the previous.',
                   action=self.step_sensitivity, shift_action=self.step_sensitivity_back)
        elif self.category == 'controls':                 # cellForControlAtIndex: 0x1000b5d64
            for title, button in CONTROL_ROWS:
                cell = t.cell(title, control_description(button), hint=SELECT_HINT,
                              action=lambda b=button: self.select_button_mode(b))
                cell.selected = bool(params.button_mode) == button
        elif self.category == 'sound':                    # cellForSound: 0x1000b619c
            t.cell('Announcer', 'ON' if params.last_announcer_value() else 'OFF',
                   hint='Press Enter to toggle in-game announcements.', action=self.toggle_announcer)
            t.cell('Test headphones', hint='Press Enter to test your headphones.', action=self.test_headphones)
        elif self.category == 'misc':                     # PORT ADDITION: everything else
            if params.controller_names():                 # the Control and Tab keys have no button
                axis_hint = 'Press Enter to move through menus with the other pair of D-pad directions.'
            else:
                axis_hint = ('Press Enter to move through menus with the other pair; Control with an arrow, '
                             'or with Tab, jumps to the first or last.')
            t.cell('Menu layout', self.menu_axis_text(), hint=axis_hint, action=self.toggle_menu_axis)
            t.cell('Remember cursor position', 'ON' if params.remember_focus() else 'OFF',
                   hint='Press Enter to toggle: when on, going back to a screen returns the cursor to the '
                        'row you left it on instead of the first one.',
                   action=self.toggle_remember_focus)
            t.cell('Tutorial text', self.tutorial_text_text(),
                   hint='Press Enter for the next setting and Shift plus Enter for the previous.',
                   action=self.step_tutorial_text, shift_action=self.step_tutorial_text_back)
            from ..platform.pad import Pads
            models = Pads.shared().connected_models()
            row = t.cell('Names in hints and tutorial', dict(params.KEY_NAMES)[params.key_names()],
                         hint="Whether the hints and the tutorial text name the keyboard's keys or the "
                              "connected controller's buttons. Press Enter or Shift plus Enter to switch. It "
                              'goes back to Keyboard keys whenever no controller is connected.',
                         action=self.toggle_key_names, shift_action=self.toggle_key_names)
            row.enabled = bool(models)                    # dimmed with no controller (pad._keys_when_none)
            if len(models) > 1:                           # several kinds connected: which one to name
                row = t.cell('Controller for names', params.names_controller() or models[-1],
                             hint='Which connected controller the hints and the tutorial text name the '
                                  'buttons of. Press Enter for the next controller and Shift plus Enter for '
                                  'the previous.',
                             action=self.step_names_controller, shift_action=self.step_names_controller_back)
                row.enabled = params.key_names() == 'buttons'
            levels = dict(params.FEEL_LEVELS)
            t.cell('Joystick vibration', levels[params.vibration_level()],
                   hint='How strongly a game controller vibrates, for hits, kills, explosions, the heartbeat '
                        'and your death. Press Enter for the next setting and Shift plus Enter for the '
                        'previous.',
                   action=self.step_vibration, shift_action=self.step_vibration_back)
            t.cell('Fine haptics', 'ON' if params.fine_haptics() else 'OFF',
                   hint='Press Enter to toggle: when on, a controller that can play what you feel in its '
                        'grips does so - a DualSense plugged in by USB - instead of shaking its motors. '
                        'With no such controller the motors are used either way.',
                   action=self.toggle_fine_haptics)
            t.cell('Trigger feel', levels[params.trigger_level()],
                   hint="Only for a DualSense controller; other controllers have no trigger feel. How stiff "
                        "its triggers are while you play: R2 like a gun's trigger, L2 a pull where it "
                        'reloads. Press Enter for the next setting and Shift plus Enter for the previous.',
                   action=self.step_trigger_level, shift_action=self.step_trigger_level_back)
            t.cell('Check for updates when the game starts', 'ON' if params.check_updates() else 'OFF',
                   hint='Press Enter to toggle: when on, the main menu looks for a new build and tells '
                        'you only if there is one.',
                   action=self.toggle_check_updates)
            t.cell('Reset all settings',
                   hint='Press Enter to put every setting back to its default. Your key and controller '
                        'bindings stay as they are.',
                   action=self.reset_all_settings)
        elif self.category == 'speech':                   # PORT ADDITION: who speaks, and SAPI 5's voice
            from ..platform.speech import OUTPUTS
            t.cell('Speech output', dict(OUTPUTS)[params.speech_output()],
                   hint='Which screen reader or voice speaks the game. Automatic uses %s. Choose one and only '
                        'that one speaks: the game is silent while it is not running. Press Enter for the '
                        'list.'
                        % ('VoiceOver, or the system voice when VoiceOver is off' if system.MAC else
                           'NVDA, or another screen reader that is running, or SAPI 5 when none is'),
                   action=self.choose_speech_output, shift_action=self.choose_speech_output)
            self.sapi_shown = self.sapi_speaking()
            if self.sapi_shown:                           # only while SAPI 5 is what speaks
                self.sapi_rows(t, params)
        elif self.category == 'keyboard':                 # PORT ADDITION: the key bindings
            keymap = KeyMap.shared()
            scheme = mode_text(keymap.mode())
            for action, _label, _default in ACTIONS:
                detail = keymap.keys_text(action)
                if action in BY_MODE:                     # this one is bound per control scheme
                    detail = '%s, in %s mode' % (detail, scheme)
                row = t.cell(keymap.label(action), detail,
                             hint='Press Enter to add a key, Shift Enter to replace them all, '
                                  'Delete to remove the last one.',
                             action=lambda a=action: self.capture_key(a),
                             shift_action=lambda a=action: self.capture_key(a, replace=True))
                row.binding_action = action               # what Delete acts on, for this row
            t.cell('Restore default keys',
                   hint='Press Enter to put every key back to its default, in both control schemes.',
                   action=self.restore_keys)
        elif self.category == 'joystick':                 # PORT ADDITION: a game controller
            from ..platform.pad import PAD_DEFAULTS, PAD_LABELS, PadMap, Pads
            pads = Pads.shared()
            models = pads.connected_models()
            editing = pads.editing_model()
            if len(models) > 1:                           # several kinds: whose buttons the rows below set
                t.cell('Controller', '%s, %d of %d' % (editing, models.index(editing) + 1, len(models)),
                       hint="The buttons below are this controller's. Press Enter for the next controller "
                            'and Shift plus Enter for the previous.',
                       action=self.step_editing, shift_action=self.step_editing_back)
            else:
                t.cell('Controller', editing or 'none connected',
                       hint=None if editing else 'Connect a controller to set its buttons.')
            t.cell('Turn', 'either stick, sideways',
                   hint='The further a stick is pushed, the faster you turn. The sticks always turn and '
                        'cannot be changed; to turn with buttons instead, set Alternate turn left and '
                        'Alternate turn right below.')
            if editing is None:                           # the buttons are set for a connected controller
                self.click_on_every_row()
                return
            padmap = PadMap.for_model(editing)
            scheme = mode_text(padmap.mode())
            for action in PAD_DEFAULTS:
                detail = padmap.text(action)
                if isinstance(PAD_DEFAULTS[action], dict):   # bound per control scheme, as on the keyboard
                    detail = '%s, in %s mode' % (detail, scheme)
                hint = PAD_BINDING_HINT
                if action in ('turn_left', 'turn_right'):
                    hint = ('This turns at the same speed as the keyboard does, however hard you press; '
                            'the sticks turn as far as they are pushed. ') + hint
                row = t.cell(PAD_LABELS.get(action, KeyMap.label(action)), detail, hint=hint,
                             action=lambda a=action: self.capture_pad(a),
                             shift_action=lambda a=action: self.capture_pad(a, replace=True))
                row.pad_binding_action = action           # what Delete acts on, for this row
            t.cell('Restore default buttons',
                   hint="Press Enter to put every one of this controller's buttons back to its default, in "
                        'both control schemes.',
                   action=self.restore_pad)
        self.click_on_every_row()

    def click_on_every_row(self) -> None:
        """PORT ADDITION: these rows are buttons in the sighted original (ADControlSchemeViewController's
        tabs and option buttons are ADButtonWithFonts), and those click when pressed.  As in Button(), the
        click is added after the row's own action."""
        for row in self.table_view.children:
            for actions in (row.actions, row.shift_actions):
                if actions and play_button_click not in actions:
                    actions.append(play_button_click)

    def focus_first_row(self, prefix: str | None = None) -> None:
        """Land on the category's first option, past its heading, and say where that is - the way the
        armory lands inside a tab it has just changed to."""
        rows = [row for row in self.table_view.children if row.traits == CELL]
        self.screen.post_screen_changed(rows[0] if rows else None, prefix)

    def announce(self, text: str) -> None:
        self.screen.speak(text)

    # --- choosing from a list (PORT ADDITION) -----------------------------------------------------
    def open_choices(self, title: str, options, current, apply) -> None:
        """Show a row's choices as a list of their own, the way the aiming and the control rows are listed.

        Stepping through a setting with Enter suits the three or four choices most of them have.  Speech
        output has twelve, and the SAPI 5 voice list has as many voices as are installed - two hundred and
        fifty on the machine this was written for - which is not a list to walk through one press at a
        time, hearing each one as you pass it.  Enter opens it, the one in use is where the cursor lands,
        Enter takes one and Escape leaves it as it was (user request).
        """
        self.choosing = (title, list(options), current, apply)
        self.table_view.children.clear()                  # a list of its own: no row keeps its place
        self.reload_data()
        rows = [row for row in self.table_view.children if row.traits == CELL]
        on = next((row for row in rows if row.selected), rows[0] if rows else None)
        self.screen.post_screen_changed(on, '%s. %d to choose from.' % (title, len(rows)))

    def _load_choices(self) -> None:
        _title, options, current, _apply = self.choosing
        t = _TableLoader(self.table_view)
        for value, label in options:
            row = t.cell(label, hint='Press Enter to use this one. Escape leaves it as it was.',
                         action=lambda v=value: self.take_choice(v))
            row.selected = value == current               # where the cursor lands, and read as selected

    def take_choice(self, value) -> None:
        title, _options, _current, apply = self.choosing
        self.choosing = None
        self.table_view.children.clear()
        apply(value)                                      # which says what was chosen, in the new voice
        self.reload_data()
        self._focus_row(title)

    def close_choices(self) -> bool:
        """Escape or Back with a list open: back to the row it was opened from, the setting untouched.
        True when there was one open, so the screen knows the key was used here."""
        if self.choosing is None:
            return False
        title = self.choosing[0]
        self.choosing = None
        self.table_view.children.clear()
        self.reload_data()
        self._focus_row(title)
        return True

    def _focus_row(self, title: str) -> None:
        rows = [row for row in self.table_view.children if row.traits == CELL]
        row = next((r for r in rows if (r.label or '').startswith(title)), rows[0] if rows else None)
        self.screen.post_screen_changed(row)

    # --- categories ------------------------------------------------------------------------------
    def open_category(self, key: str) -> None:
        self.category = key
        self.capturing = None
        self.capturing_replaces = False
        self.table_view.children.clear()                  # a new list: no row keeps its place
        self.reload_data()
        self.focus_first_row(dict(CATEGORIES)[key])       # named, then the option it lands on

    @staticmethod
    def category_keys_text() -> str:
        """Both pairs of arrows, whichever way round the player has them: "Up and Down change category,
        Left and Right move through it"."""
        return cross_axis_text().replace('tab', 'category')

    def move_category(self, where: str) -> None:
        """PORT ADDITION: the arrows the menu navigation is not using move between categories - 'next',
        'previous', 'first' or 'last', as the element keys do one axis over."""
        keys = [key for key, _title in CATEGORIES]
        step = {'next': 1, 'previous': -1}.get(where)
        if step is None:
            i = 0 if where == 'first' else len(keys) - 1
        else:
            i = max(0, min(len(keys) - 1, keys.index(self.category) + step))   # the ends hold, as elsewhere
        menu_tick()                                       # PORT ADDITION: felt as well as heard
        self.open_category(keys[i])                       # at an end: says where we still are

    # --- aiming ----------------------------------------------------------------------------------
    @staticmethod
    def sensitivity_text(value=None) -> str:
        value = GameParameters.shared().sensivity if value is None else value
        return ('%.2f' % value).rstrip('0').rstrip('.')

    def select_control_scheme(self, scheme: int) -> None:   # willSelectRowAtIndexPath: 0x1000b51b0
        GameParameters.shared().set_control_scheme(scheme)
        self.reload_data()                                # the selected row moves within the section
        title = next(t for t, _d, s in AIMING_ROWS if s == scheme)
        self.announce('%s selected' % title)

    def step_sensitivity(self, step: int = 1) -> None:
        params = GameParameters.shared()
        steps = params.SENSIVITY_STEPS
        current = min(steps, key=lambda s: abs(s - params.sensivity))
        params.set_sensivity(steps[(steps.index(current) + step) % len(steps)])
        self.reload_data()
        self.announce('Turn sensitivity %s' % self.sensitivity_text())

    def step_sensitivity_back(self) -> None:
        self.step_sensitivity(-1)

    # --- controls --------------------------------------------------------------------------------
    def select_button_mode(self, button: bool) -> None:
        GameParameters.shared().set_button_mode(button)
        self.reload_data()
        mode = 'button' if button else 'gesture'          # Next weapon and Reload are bound per scheme
        self.announce('%s selected, %s switches weapon, %s reloads'
                      % ('Button' if button else 'Gesture',
                         _mode_words('next_weapon', mode), _mode_words('reload', mode)))

    # --- sound -----------------------------------------------------------------------------------
    def toggle_announcer(self) -> None:
        params = GameParameters.shared()
        params.set_announcer(not params.last_announcer_value())
        self.reload_data()
        self.announce('Announcer %s' % ('ON' if params.last_announcer_value() else 'OFF'))

    @staticmethod
    def tutorial_text_text(mode=None) -> str:
        params = GameParameters.shared()
        return dict(params.TUTORIAL_TEXT_MODES)[params.tutorial_text_mode() if mode is None else mode]

    def step_tutorial_text(self, step: int = 1) -> None:
        params = GameParameters.shared()
        modes = [m for m, _text in params.TUTORIAL_TEXT_MODES]
        mode = modes[(modes.index(params.tutorial_text_mode()) + step) % len(modes)]
        params.set_tutorial_text_mode(mode)
        self.reload_data()
        self.announce('Tutorial text %s' % self.tutorial_text_text(mode))

    def step_tutorial_text_back(self) -> None:
        self.step_tutorial_text(-1)

    @staticmethod
    def test_headphones() -> None:
        pl = _headphones_playlist()
        sound = pl.sound('HeadphonesTest') if pl is not None else None
        if sound is not None:
            sound.play()

    # --- keyboard --------------------------------------------------------------------------------
    @staticmethod
    def menu_axis_text(axis=None) -> str:
        params = GameParameters.shared()
        return dict(params.MENU_AXES)[params.menu_axis() if axis is None else axis]

    def toggle_remember_focus(self) -> None:
        params = GameParameters.shared()
        params.set_remember_focus(not params.remember_focus())
        self.reload_data()
        self.announce('Remember cursor position %s' % ('ON' if params.remember_focus() else 'OFF'))

    # --- miscellaneous (PORT ADDITION) -----------------------------------------------------------
    def toggle_check_updates(self) -> None:
        params = GameParameters.shared()
        params.set_check_updates(not params.check_updates())
        self.reload_data()
        self.announce('Check for updates when the game starts %s'
                      % ('ON' if params.check_updates() else 'OFF'))

    def reset_all_settings(self) -> None:
        """Every setting on these pages back to where a new profile starts, except the key bindings and the
        controller's - they have their own Restore default keys and Restore default buttons.

        Each value is what the setting's own getter answers when nothing is stored, so a reset profile
        and a new one cannot disagree.  The setters are all the Settings rows ever call, so going
        through them here misses nothing the rows would have done."""
        params = GameParameters.shared()
        params.set_control_scheme(1)                              # last_control_scheme with nothing stored
        params.set_sensivity(params.DEFAULT_SENSIVITY)
        params.set_button_mode(params.DEFAULT_BUTTON_MODE)        # last_button_mode, likewise
        params.set_announcer(True)                                # last_announcer_value, likewise
        params.set_tutorial_text_mode(params.DEFAULT_TUTORIAL_TEXT)
        params.set_menu_axis(params.DEFAULT_MENU_AXIS)
        params.set_remember_focus(params.DEFAULT_REMEMBER_FOCUS)
        params.set_check_updates(params.DEFAULT_CHECK_UPDATES)
        params.set_menu_music_volume(params.DEFAULT_MENU_MUSIC_VOLUME)
        params.set_vibration_level(params.DEFAULT_VIBRATION)
        params.set_trigger_level(params.DEFAULT_TRIGGER_FEEL)
        params.set_fine_haptics(params.DEFAULT_FINE_HAPTICS)
        params.set_key_names(params.DEFAULT_KEY_NAMES)
        params.set_modern_audio(params.DEFAULT_MODERN_AUDIO)
        params.set_names_controller(None)
        params.set_speech_output(params.DEFAULT_SPEECH_OUTPUT)
        params.set_sapi(voice=None, rate=None, boost=False, pitch=0, volume=None)
        App.apply_menu_music_volume()
        self.reload_data()
        self.announce('All settings reset to default. Your key and controller bindings are unchanged.')

    # --- joystick (PORT ADDITION) ----------------------------------------------------------------
    @staticmethod
    def _next_level(level: str, step: int) -> str:
        levels = [key for key, _text in GameParameters.FEEL_LEVELS]
        return levels[(levels.index(level) + step) % len(levels)]

    def step_vibration(self, step: int = 1) -> None:
        params = GameParameters.shared()
        params.set_vibration_level(self._next_level(params.vibration_level(), step))
        self.reload_data()
        self.announce('Joystick vibration %s' % dict(params.FEEL_LEVELS)[params.vibration_level()])
        from ..platform.haptics import Haptics            # so the new strength can be felt
        Haptics.shared().sample()

    def step_vibration_back(self) -> None:
        self.step_vibration(-1)

    #: PORT ADDITION: seconds a stepped Trigger feel is left on the pad, to squeeze R2 and feel it.  The
    #: triggers are a game's feel, and the game is not running while you are choosing it.
    TRIGGER_SAMPLE = 8.0

    def toggle_fine_haptics(self) -> None:
        params = GameParameters.shared()
        params.set_fine_haptics(not params.fine_haptics())
        self.reload_data()
        self.announce('Fine haptics %s' % ('ON' if params.fine_haptics() else 'OFF'))
        from ..platform.haptics import Haptics            # so the difference can be felt at once
        Haptics.shared().sample()

    def step_trigger_level(self, step: int = 1) -> None:
        params = GameParameters.shared()
        params.set_trigger_level(self._next_level(params.trigger_level(), step))
        self.reload_data()
        self.announce('Trigger feel %s' % dict(params.FEEL_LEVELS)[params.trigger_level()])
        self.sample_triggers(params.trigger_level())

    def sample_triggers(self, level: str) -> None:
        """Give a connected DualSense this feel for a few seconds, so it can be tried here; then plain
        again, as the menus always leave it."""
        from ..platform.pad import Pads
        from ..platform.runloop import RunLoop
        pads = Pads.shared()
        if not pads.dualsenses:
            return
        if level == 'off':
            pads.set_triggers('off')
            return
        pads.set_triggers('gun and reload', level)
        token = self._trigger_sample = object()

        def plain() -> None:
            if self._trigger_sample is token:             # a later step has its own few seconds
                self._trigger_sample = None
                pads.set_triggers('off')
        RunLoop.main().call_later(self.TRIGGER_SAMPLE, plain)

    def step_trigger_level_back(self) -> None:
        self.step_trigger_level(-1)

    def toggle_key_names(self) -> None:
        params = GameParameters.shared()
        params.set_key_names('keys' if params.key_names() == 'buttons' else 'buttons')
        self.reload_data()
        self.announce('Names in hints and tutorial: %s' % dict(params.KEY_NAMES)[params.key_names()])

    def choose_speech_output(self) -> None:
        """PORT ADDITION: the outputs as a list (user request).  Twelve of them, and each one said as you
        passed it while stepping - the list says them once and takes the one you land on."""
        from ..platform.speech import OUTPUTS
        self.open_choices('Speech output', list(OUTPUTS), GameParameters.shared().speech_output(),
                          self.take_speech_output)

    def take_speech_output(self, choice: str) -> None:
        """The chosen Speech output.  Said through the new one - or, when that one cannot speak, through
        the automatic choice, since it could not be heard otherwise and the player would be left in
        silence without knowing why."""
        from ..platform.speech import OUTPUTS, PRISM_NAMES, Speech
        GameParameters.shared().set_speech_output(choice)
        name = dict(OUTPUTS)[choice]
        speech = Speech.shared()
        if speech.can_speak(choice):
            self.announce('Speech output: %s' % name)
        elif choice in PRISM_NAMES and speech.readers.ctx is None:
            speech.speak_automatic('Speech output: %s. It needs Prism, which is not installed, so the game '
                                   'will be silent.' % name)
        else:
            speech.speak_automatic('Speech output: %s. %s is not running, so the game will be silent until '
                                   'it is.' % (name, name))

    # --- SAPI 5 (PORT ADDITION) ------------------------------------------------------------------
    SAPI_STEP_HINT = 'Press Enter for the next setting and Shift plus Enter for the previous.'
    SPEECH_CHECK_EVERY = 1.0                              # seconds between looks at what speaks

    @staticmethod
    def sapi_speaking() -> bool:
        """Whether SAPI 5 is what speaks: chosen, or Automatic with no screen reader running."""
        from ..platform.speech import Speech
        choice = GameParameters.shared().speech_output()
        return choice == 'sapi' or (choice == 'auto' and Speech.shared().automatic_output() == 'sapi')

    def follow_speech(self) -> None:
        """On the Speech category, SAPI 5's rows come and go as it starts or stops being what speaks - a
        screen reader started or closed while the list is open - looked at once a second."""
        if self.category != 'speech' or self.capturing is not None or self.choosing is not None:
            return
        now = time.monotonic()
        if now < self._speech_due:
            return
        self._speech_due = now + self.SPEECH_CHECK_EVERY
        if self.sapi_speaking() != self.sapi_shown:
            self.reload_data()
    CONTROL_PANEL_VOICE = 'System default' if system.MAC else 'Control Panel default'

    def sapi_rows(self, t, params) -> None:
        """SAPI 5's voice, rate, rate boost (for a voice that has one), pitch and volume - the system voice's,
        on the Mac.  Each change is said in that voice itself, at the new setting, so it can be heard
        whatever else is speaking."""
        from ..platform.speech import Speech
        sapi = Speech.shared().sapi
        if sapi.voice is None:                            # no SAPI here (comtypes missing)
            return
        config = params.sapi_config()
        names = dict(sapi.voices())
        t.cell(VOICE_NAME + ' voice', names.get(config['voice'], self.CONTROL_PANEL_VOICE),
               hint='The voice %s speaks with: %s, or any installed voice. ' % (VOICE_NAME, VOICE_DEFAULT_HINT)
                    + 'Press Enter for the list.',
               action=self.choose_sapi_voice, shift_action=self.choose_sapi_voice)
        t.cell(VOICE_NAME + ' rate', str(sapi.rate()), hint='How fast %s speaks, from -10 to 10. ' % VOICE_NAME + self.SAPI_STEP_HINT,
               action=self.step_sapi_rate, shift_action=self.step_sapi_rate_back)
        if sapi.boost_supported(config['voice'] if config['voice'] in names else None):
            t.cell(VOICE_NAME + ' rate boost', 'ON' if config['boost'] else 'OFF',
                   hint='Press Enter to toggle: when on, this voice speaks faster again than its rate.',
                   action=self.toggle_sapi_boost, shift_action=self.toggle_sapi_boost)
        t.cell(VOICE_NAME + ' pitch', str(config['pitch']), hint='How high %s speaks, from -10 to 10. ' % VOICE_NAME
                                                          + self.SAPI_STEP_HINT,
               action=self.step_sapi_pitch, shift_action=self.step_sapi_pitch_back)
        t.cell(VOICE_NAME + ' volume', '%d%%' % sapi.volume(), hint='How loud %s speaks. ' % VOICE_NAME + self.SAPI_STEP_HINT,
               action=self.step_sapi_volume, shift_action=self.step_sapi_volume_back)
        t.cell('Modern audio output', 'ON' if params.modern_audio() else 'OFF',
               hint='Press Enter to toggle: when on, the game plays %s itself, and a line stops the moment '
                    'you interrupt it. Turn it off to let Windows play it, which is slower to stop.'
                    % VOICE_NAME,
               action=self.toggle_modern_audio, shift_action=self.toggle_modern_audio)

    def toggle_modern_audio(self) -> None:
        """PORT ADDITION: whether the game plays SAPI 5 itself (speech_audio.py) or Windows does."""
        from ..platform.speech import Speech
        params = GameParameters.shared()
        params.set_modern_audio(not params.modern_audio())
        Speech.shared().modern_audio_changed()            # off hands the voice back now, not next time
        self.reload_data()
        self.announce('Modern audio output %s' % ('on' if params.modern_audio() else 'off'))
        self._sapi_say('This is how it sounds.')          # in that voice, through whichever plays it now

    @staticmethod
    def _sapi_say(text: str) -> None:
        from ..platform.speech import Speech
        Speech.shared().sapi.speak(text, True)

    def choose_sapi_voice(self) -> None:
        """PORT ADDITION: the installed voices as a list (user request).  There are as many as the machine
        has - two hundred and fifty on the one this was written for - and stepping said every one of them
        on the way past."""
        from ..platform.speech import Speech
        voices = Speech.shared().sapi.voices()
        self.open_choices('%s voice' % VOICE_NAME, [(None, self.CONTROL_PANEL_VOICE)] + list(voices),
                          GameParameters.shared().sapi_config()['voice'], self.take_sapi_voice)

    def take_sapi_voice(self, voice_id) -> None:
        from ..platform.speech import Speech
        GameParameters.shared().set_sapi(voice=voice_id)
        names = dict(Speech.shared().sapi.voices())
        self._sapi_say('%s voice: %s' % (VOICE_NAME, names.get(voice_id, self.CONTROL_PANEL_VOICE)))

    def step_sapi_rate(self, step: int = 1) -> None:
        from ..platform.speech import Speech
        params = GameParameters.shared()
        params.set_sapi(rate=max(-10, min(10, Speech.shared().sapi.rate() + step)))   # the ends hold
        self.reload_data()
        self._sapi_say('%s rate %d' % (VOICE_NAME, Speech.shared().sapi.rate()))

    def step_sapi_rate_back(self) -> None:
        self.step_sapi_rate(-1)

    def toggle_sapi_boost(self) -> None:
        params = GameParameters.shared()
        params.set_sapi(boost=not params.sapi_config()['boost'])
        self.reload_data()
        self._sapi_say('%s rate boost %s' % (VOICE_NAME, 'ON' if params.sapi_config()['boost'] else 'OFF'))

    def step_sapi_pitch(self, step: int = 1) -> None:
        params = GameParameters.shared()
        params.set_sapi(pitch=max(-10, min(10, params.sapi_config()['pitch'] + step)))
        self.reload_data()
        self._sapi_say('%s pitch %d' % (VOICE_NAME, params.sapi_config()['pitch']))

    def step_sapi_pitch_back(self) -> None:
        self.step_sapi_pitch(-1)

    def step_sapi_volume(self, step: int = 1) -> None:
        from ..platform.speech import Speech
        params = GameParameters.shared()
        params.set_sapi(volume=max(0, min(100, Speech.shared().sapi.volume() + 10 * step)))
        self.reload_data()
        self._sapi_say('%s volume %d%%' % (VOICE_NAME, Speech.shared().sapi.volume()))

    def step_sapi_volume_back(self) -> None:
        self.step_sapi_volume(-1)

    def step_names_controller(self, step: int = 1) -> None:
        from ..platform.pad import Pads
        params = GameParameters.shared()
        models = Pads.shared().connected_models()
        current = params.names_controller()
        if len(models) < 2 or current is None:
            return
        params.set_names_controller(models[(models.index(current) + step) % len(models)])
        self.reload_data()
        self.announce('Controller for names: %s' % params.names_controller())

    def step_names_controller_back(self) -> None:
        self.step_names_controller(-1)

    def step_editing(self, step: int = 1) -> None:
        """Several kinds of controller connected: the next one's buttons, to see and set."""
        from ..platform.pad import Pads
        pads = Pads.shared()
        models = pads.connected_models()
        if len(models) < 2:
            return
        pads.editing = models[(models.index(pads.editing_model()) + step) % len(models)]
        self.reload_data()
        self.announce('%s, %d of %d' % (pads.editing, models.index(pads.editing) + 1, len(models)))

    def step_editing_back(self) -> None:
        self.step_editing(-1)

    def _pad_profile(self):
        """The bindings being shown and set: the controller chosen in the Controller row."""
        from ..platform.pad import PadMap, Pads
        model = self.pad_capturing_model or Pads.shared().editing_model()
        return PadMap.for_model(model) if model else None

    def capture_pad(self, action: str, replace: bool = False) -> None:
        padmap = self._pad_profile()
        if padmap is None:
            self.announce('Connect a controller first.')
            return
        self.pad_capturing = action
        self.pad_capturing_replaces = replace
        self.pad_capturing_model = padmap.model           # the buttons go to this controller's profile
        self.announce('Press the button to %s %s, or Escape on the keyboard to keep %s'
                      % ('use instead of' if replace else 'add to', KeyMap.label(action), padmap.text(action)))

    def handle_captured_pad(self, name: str) -> None:
        """The next controller input while a button is being set."""
        action = self.pad_capturing
        if action is None:
            return
        padmap = self._pad_profile()
        if name in padmap.UNBINDABLE:
            why = ('Pushing a stick sideways turns' if name in ('stickleft', 'stickright')
                   else '%s is kept by %s' % (padmap.name_of(name), 'macOS' if system.MAC else 'Windows'))
            self.announce('%s. Press another button, or Escape to keep %s' % (why, padmap.text(action)))
            return
        replace = self.pad_capturing_replaces
        self.pad_capturing, self.pad_capturing_replaces, self.pad_capturing_model = None, False, None
        padmap.set(action, name) if replace else padmap.add(action, name)
        self.reload_data()
        self.announce('%s is now %s' % (KeyMap.label(action), padmap.text(action)))

    def cancel_pad_capture(self) -> None:
        padmap = self._pad_profile()
        action, self.pad_capturing, self.pad_capturing_replaces = self.pad_capturing, None, False
        self.pad_capturing_model = None
        if action is not None and padmap is not None:
            self.announce('%s keeps %s' % (KeyMap.label(action), padmap.text(action)))

    def remove_pad(self, action: str) -> None:
        padmap = self._pad_profile()
        if padmap is None:
            return
        name = padmap.remove_last(action)
        if name is None:
            self.announce('%s keeps %s: an action needs at least one button'
                          % (KeyMap.label(action), padmap.text(action)))
            return
        self.reload_data()
        self.announce('%s removed from %s, now %s'
                      % (padmap.name_of(name), KeyMap.label(action), padmap.text(action)))

    def restore_pad(self) -> None:
        padmap = self._pad_profile()
        if padmap is None:
            return
        padmap.restore_defaults()
        self.reload_data()
        self.announce('Default buttons restored for the %s, in both control schemes' % padmap.model)

    def toggle_menu_axis(self) -> None:
        params = GameParameters.shared()
        axes = [a for a, _text in params.MENU_AXES]
        axis = axes[(axes.index(params.menu_axis()) + 1) % len(axes)]
        params.set_menu_axis(axis)
        self.reload_data()
        self.announce('Menu layout %s' % self.menu_axis_text(axis))

    def capture_key(self, action: str, replace: bool = False) -> None:
        self.capturing = action
        self.capturing_replaces = replace
        keymap = KeyMap.shared()
        self.announce('Press the key to %s %s, or Escape to keep %s'
                      % ('use instead of' if replace else 'add to',
                         keymap.label(action), keymap.keys_text(action)))

    def handle_captured_key(self, code: int) -> bool:
        """The screen sends every key here while a binding is being set."""
        action, self.capturing = self.capturing, None
        replace, self.capturing_replaces = getattr(self, 'capturing_replaces', False), False
        if action is None:
            return False
        keymap = KeyMap.shared()
        if code == pygame.K_ESCAPE:
            self.announce('%s keeps %s' % (keymap.label(action), keymap.keys_text(action)))
            return True
        keymap.set_key(action, code) if replace else keymap.add_key(action, code)
        self.reload_data()
        self.announce('%s is now %s' % (keymap.label(action), keymap.keys_text(action)))
        return True

    def remove_key(self, action: str) -> None:
        """PORT ADDITION: Delete on a binding row takes off the key added last."""
        keymap = KeyMap.shared()
        name = keymap.remove_last_key(action)
        if name is None:
            self.announce('%s keeps %s: an action needs at least one key'
                          % (keymap.label(action), keymap.keys_text(action)))
            return
        self.reload_data()
        self.announce('%s removed from %s, now %s'
                      % (key_text(name), keymap.label(action), keymap.keys_text(action)))

    def restore_keys(self) -> None:
        KeyMap.shared().restore_defaults()
        self.reload_data()
        self.announce('Default keys restored in both control schemes')


@register('ADSettingsViewController')
class SettingsScreen(ViewControllerScreen):
    """ADSettingsViewController (tag-2781 view #54; the OK button #65 is labelled "OK")."""
    page_title = 'Settings'

    panel_title = 'Settings'                              # said when the panel takes the cursor

    def load_view(self) -> None:                          # 0x1000af3dc
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#54')
        self.control_scheme_view = View('', (30, 50, 508, 190), accessible=False, parent=v, name='#19')
        Button('OK', (254, 245, 60, 50), parent=v, actions=[self.validate_button_pressed], name='#65')
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x1000af1b8
        super().view_did_load()
        self.add_control_scheme_panel()
        sb = self.status_bar_view_controller
        sb.back_button.set_title('Main Menu')
        sb.set_armory_button_visibility(False)
        sb.set_currencies_visibility(True)
        sb.set_diamonds_visibility(True)
        pl = _headphones_playlist()
        if pl is not None:
            pl.activate()

    def add_control_scheme_panel(self) -> None:           # 0x1000af5b8
        f = self.control_scheme_view.frame
        self.control_scheme = ControlSchemePanel(self, self.view, (f[0] + f[2] / 2.0, f[1] + f[3] / 2.0))
        panel = self.control_scheme
        panel.focus_first_row('%s, %s. %s' % (self.panel_title, panel.category_keys_text(),
                                              dict(CATEGORIES)[panel.category]))

    def view_will_appear(self) -> None:                   # 0x1000af4e0
        self.status_bar_view_controller.back_button.hidden = False
        super().view_will_appear()

    # --- keys ------------------------------------------------------------------------------------
    def key_down(self, event) -> None:
        if self.control_scheme.capturing is not None:     # setting a binding: every key goes to the panel
            # PORT ADDITION: a controller button stands for a key in the menus; here it cancels, as Escape
            # does, rather than binding the key it stands for
            key = pygame.K_ESCAPE if getattr(event, 'pad', False) else event.key
            self.control_scheme.handle_captured_key(key)
            return
        panel = self.control_scheme
        if panel.pad_capturing is not None:               # PORT ADDITION: setting a controller button
            if not getattr(event, 'pad', False):
                if event.key == pygame.K_ESCAPE:
                    panel.cancel_pad_capture()
                else:
                    panel.announce('Press a button on the controller, or Escape to cancel')
            return
        if event.key == pygame.K_DELETE:                  # PORT ADDITION: take a key off the focused binding
            action = getattr(self.focus, 'binding_action', None)
            if action is not None:
                self.control_scheme.remove_key(action)
                return
            action = getattr(self.focus, 'pad_binding_action', None)
            if action is not None:
                self.control_scheme.remove_pad(action)
                return
        where = cross_axis_key(event)                     # PORT ADDITION: the other arrows change category
        if where is not None:
            if self.control_scheme.choosing is None:      # while a row's list is open, it has the arrows
                self.control_scheme.move_category(where)
            return
        super().key_down(event)

    def frame(self) -> None:
        super().frame()
        self.control_scheme.follow_speech()               # PORT ADDITION: see there

    def on_dismiss(self) -> None:
        from ..platform.pad import Pads
        self.control_scheme._trigger_sample = None        # PORT ADDITION: no Trigger feel left on the pad
        Pads.shared().set_triggers('off')
        super().on_dismiss()

    def pads_changed(self) -> None:
        """PORT ADDITION: a controller came or went.  The Joystick category names it and shows its
        buttons, and Miscellaneous names it or dims the choice, so they are laid out again; a button being
        set for a controller that has gone is given up."""
        from ..platform.pad import Pads
        panel = self.control_scheme
        if (panel.pad_capturing is not None
                and panel.pad_capturing_model not in Pads.shared().connected_models()):
            panel.cancel_pad_capture()
        if panel.category in ('joystick', 'misc'):
            panel.reload_data()

    # PORT ADDITION: while a controller button is being set, the host hands this screen the controller's
    # presses as they are, instead of the keys they stand for in a menu
    def takes_pad_input(self) -> bool:
        return self.control_scheme.pad_capturing is not None

    def pad_input(self, name: str) -> None:
        self.control_scheme.handle_captured_pad(name)

    # --- actions ---------------------------------------------------------------------------------
    def validate_button_pressed(self) -> None:            # 0x1000afa58
        self.host.dismiss_presented(self)

    # PORT ADDITION: a row's list of choices takes Escape and Back first, closing itself rather than the
    # screen - the armory does the same for an open weapon page (armory.accessibility_perform_escape)
    def accessibility_perform_escape(self) -> None:
        if self.control_scheme.close_choices():
            return
        super().accessibility_perform_escape()

    def back_button_pressed(self) -> None:                # 0x1000af948
        if self.control_scheme.close_choices():
            return
        pl = _headphones_playlist()
        if pl is not None:
            pl.deactivate()
        App.delegate().go_to_main_menu()


@register('ADPauseViewController')
class PauseScreen(SettingsScreen):
    """ADPauseViewController (tag-2781 view #27): the settings panel plus Resume and End Game."""
    #: the pause screen is inside Play, but it is a fight rather than a menu: no coins, no diamonds
    shows_currencies = False
    page_title = 'Paused'

    panel_title = 'Paused'

    def __init__(self, host, pause_controller=None):
        super().__init__(host)
        self.pause = pause_controller

    def load_view(self) -> None:                          # 0x100055804
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#27')
        self.control_scheme_view = View('', (30, 45, 508, 210), accessible=False, parent=v, name='#66')
        self.resume_button = Button('Resume', (60, 263, 120, 40), parent=v,
                                    actions=[self.validate_button_pressed], name='#58')
        # PORT ADDITION: a challenge you have already lost - a missed time limit, an accuracy you cannot
        # get back - had to be played out or ended and then found again in the list.  It sits between the
        # two nib buttons, so the order read is Resume, Restart challenge, End Game: the least final
        # first and the most final last.  An endless game has no challenge to restart, so it is not built.
        if self.pause is not None and self.pause.challenge_dictionary() is not None:
            Button('Restart challenge', (196, 263, 150, 40), parent=v,
                   actions=[self.restart_button_touched], name='Restart challenge (port)')
        Button('End Game', (358, 263, 150, 40), parent=v, actions=[self.quit_button_touched], name='#29')
        self.first_accessible_element = self.resume_button
        self.roots = [v]

    def view_did_load(self) -> None:                      # 0x100055650
        super().view_did_load()                           # ADSettingsViewController (the panel posts last)
        sb = self.status_bar_view_controller
        sb.back_button.set_title('Resume')
        sb.set_currencies_visibility(False)
        # loadMissionOverlay adds the mission bar at alpha 0
        pl = _headphones_playlist()
        if pl is not None:
            pl.activate()

    def view_will_appear(self) -> None:                   # 0x100055950: only [[self view] setNeedsLayout]
        if self.status_bar_view_controller is not None:
            self.status_bar_view_controller.view_will_appear()

    def validate_button_pressed(self) -> None:            # 0x100055bbc
        if self.pause is not None:
            self.pause.validate_button_pressed()
        else:
            self.host.dismiss_presented(self)

    def restart_button_touched(self) -> None:             # PORT ADDITION
        # The same sound the challenge's own Play button makes (ADChallengeOverviewViewController
        # 0x1000d8b48) and the failed screen's Try again (0x100071ee8): a restart is a level starting,
        # and it should sound like one.  It is played here rather than beside the relaunch because the
        # relaunch waits for killGameplay's clean-up, and a level should start with this sound rather
        # than a fifth of a second after it.
        _play_buttons_sound('start_level_button')
        if self.pause is not None:
            self.pause.restart_button_touched()

    def quit_button_touched(self) -> None:                # 0x1000559c0
        if self.pause is not None:
            self.pause.quit_button_touched()

    def back_button_pressed(self) -> None:                # 0x1000559ac
        if self.control_scheme.close_choices():           # PORT ADDITION: as on the settings screen
            return
        self.validate_button_pressed()
