"""PORT ADDITION: game controllers - a DualSense, a DualShock, an Xbox or Switch Pro pad, or anything SDL
knows.

The original is played by touch and by turning the phone; the port plays it from the keyboard (keymap.py),
and this is the other way in.  SDL's game controller layer names every pad's buttons the same way - the
bottom face button is ``a`` whatever is printed on it - so the bindings below hold for every controller,
and only the names spoken for them change with the kind of pad.

What a controller does:

* **In play** its buttons are bound to the same actions as the keys (``PAD_DEFAULTS``): R2 fires, R1 is
  melee, and next weapon and reload are L1 and L2 in Button mode, or a flick of a stick up or down in
  Gesture mode - the swipes the Up and Down arrows stand for on the keyboard.  Either stick turns, and
  turns as far as it is pushed: a little is slow, all the way is as fast as the turn keys; the sticks are
  the pad's own and cannot be bound.  For a player who would rather not turn with a stick, two buttons turn
  as well - the D-pad, left and right, to begin with - and those can be bound like any other: they turn at
  the keyboard's speed, since a button is either down or up.
* **In the menus** it stands in for the keys the menus already know: the D-pad or a stick for the arrows -
  which move through a screen and, on the other pair, change tab - the shoulders for moving through it as
  well, the bottom button for Enter, and held for Control (to the first or last), the right one for Escape, the
  top one for Delete, the triggers for Page Down and Page Up (the menu music volume).  ``ui/host.py`` does that
  translation; the key presses it makes are marked ``pad`` so a key being captured in Settings is not
  taken from a controller.

Triggers are read as buttons, pressed past half way and let go below a third.  A stick counts as pushed in
a direction past 60% and let go below 30%, with the direction taken from the larger of its two axes, so
turning with a stick does not flick it up or down by accident.
"""
from __future__ import annotations

import ctypes
import logging
import math
import os
import sys
import time

import pygame

from . import host
from .defaults import UserDefaults

log = logging.getLogger('platform.pad')

#: SDL reads these when its joystick layer starts, which pygame.init() does, so they are set before that.
#: Without them a PlayStation pad over Bluetooth cannot rumble or be given trigger effects: SDL leaves it in
#: the simple report mode Windows' own drivers understand unless it is asked not to.
HINTS = {'SDL_JOYSTICK_HIDAPI_PS5_RUMBLE': '1', 'SDL_JOYSTICK_HIDAPI_PS4_RUMBLE': '1'}


def set_hints() -> None:
    for name, value in HINTS.items():
        os.environ.setdefault(name, value)


# SDL_GameControllerButton values; pygame names the first fifteen, SDL 2.0.14 added the rest
BUTTONS = {
    pygame.CONTROLLER_BUTTON_A: 'a', pygame.CONTROLLER_BUTTON_B: 'b',
    pygame.CONTROLLER_BUTTON_X: 'x', pygame.CONTROLLER_BUTTON_Y: 'y',
    pygame.CONTROLLER_BUTTON_BACK: 'back', pygame.CONTROLLER_BUTTON_GUIDE: 'guide',
    pygame.CONTROLLER_BUTTON_START: 'start',
    pygame.CONTROLLER_BUTTON_LEFTSTICK: 'leftstick', pygame.CONTROLLER_BUTTON_RIGHTSTICK: 'rightstick',
    pygame.CONTROLLER_BUTTON_LEFTSHOULDER: 'leftshoulder',
    pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: 'rightshoulder',
    pygame.CONTROLLER_BUTTON_DPAD_UP: 'dpup', pygame.CONTROLLER_BUTTON_DPAD_DOWN: 'dpdown',
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: 'dpleft', pygame.CONTROLLER_BUTTON_DPAD_RIGHT: 'dpright',
    15: 'misc1', 16: 'paddle1', 17: 'paddle2', 18: 'paddle3', 19: 'paddle4', 20: 'touchpad',
}
LEFT_X, LEFT_Y, RIGHT_X, RIGHT_Y, TRIGGER_LEFT, TRIGGER_RIGHT = range(6)
STICKS = ((LEFT_X, LEFT_Y), (RIGHT_X, RIGHT_Y))
TRIGGERS = {TRIGGER_LEFT: 'lefttrigger', TRIGGER_RIGHT: 'righttrigger'}

TRIGGER_DOWN, TRIGGER_UP = 0.5, 0.3
#: R2 on a DualSense with the gun feel: the wall holds from GUN_TRIGGER's start until here, where it breaks
#: and the shot goes, so the wall is pressed through rather than nudged.  GUN_UP is a pistol's reset: it
#: comes back to just under the wall, not all the way out, before it will fire again.  An ordinary trigger -
#: another pad, or a DualSense with the Trigger feel off - has no wall to press through and keeps the plain
#: half-way TRIGGER_DOWN.
GUN_DOWN, GUN_UP = 0.72, 0.50
PUSH_DOWN, PUSH_UP = 0.6, 0.3
#: how far a stick has to move before it turns at all: a stick at rest seldom reads exactly zero
DEAD_ZONE = 0.18

# --- what the buttons are called ------------------------------------------------------------------------
NAMES = {
    'playstation': {'a': 'Cross', 'b': 'Circle', 'x': 'Square', 'y': 'Triangle',
                    'leftshoulder': 'L1', 'rightshoulder': 'R1', 'lefttrigger': 'L2', 'righttrigger': 'R2',
                    'back': 'Create', 'start': 'Options', 'guide': 'PS button',
                    'leftstick': 'L3', 'rightstick': 'R3', 'touchpad': 'Touchpad', 'misc1': 'Mute button'},
    'xbox': {'a': 'A', 'b': 'B', 'x': 'X', 'y': 'Y',
             'leftshoulder': 'LB', 'rightshoulder': 'RB', 'lefttrigger': 'LT', 'righttrigger': 'RT',
             'back': 'View', 'start': 'Menu', 'guide': 'Xbox button',
             'leftstick': 'Left stick click', 'rightstick': 'Right stick click', 'misc1': 'Share button'},
    # SDL reports Nintendo face buttons by the letter printed on them
    # (SDL_HINT_GAMECONTROLLER_USE_BUTTON_LABELS is on by default in SDL 2), so the letters are right
    'nintendo': {'a': 'A', 'b': 'B', 'x': 'X', 'y': 'Y',
                 'leftshoulder': 'L', 'rightshoulder': 'R', 'lefttrigger': 'ZL', 'righttrigger': 'ZR',
                 'back': 'Minus', 'start': 'Plus', 'guide': 'Home',
                 'leftstick': 'Left stick click', 'rightstick': 'Right stick click', 'misc1': 'Capture'},
    'generic': {'a': 'A button', 'b': 'B button', 'x': 'X button', 'y': 'Y button',
                'leftshoulder': 'Left shoulder', 'rightshoulder': 'Right shoulder',
                'lefttrigger': 'Left trigger', 'righttrigger': 'Right trigger',
                'back': 'Back', 'start': 'Start', 'guide': 'Guide',
                'leftstick': 'Left stick click', 'rightstick': 'Right stick click', 'touchpad': 'Touchpad',
                'misc1': 'Extra button'},
}
COMMON_NAMES = {'dpup': 'D-pad up', 'dpdown': 'D-pad down', 'dpleft': 'D-pad left', 'dpright': 'D-pad right',
                'stickup': 'Stick up', 'stickdown': 'Stick down', 'stickleft': 'Stick left',
                'stickright': 'Stick right',
                'paddle1': 'Paddle 1', 'paddle2': 'Paddle 2', 'paddle3': 'Paddle 3', 'paddle4': 'Paddle 4'}


def family(controller_name: str) -> str:
    """Which set of names a pad's buttons go by, from the name SDL gives it."""
    n = (controller_name or '').lower()
    if any(w in n for w in ('ps5', 'ps4', 'ps3', 'dualsense', 'dualshock', 'playstation')):
        return 'playstation'
    if any(w in n for w in ('xbox', 'xinput')):
        return 'xbox'
    if any(w in n for w in ('nintendo', 'switch', 'joy-con', 'joycon')):
        return 'nintendo'
    return 'generic'


def input_name(name: str, kind: str = 'generic', controller_name: str = '') -> str:
    """'righttrigger' -> 'R2' on a PlayStation pad, 'RT' on an Xbox one."""
    if name == 'back' and kind == 'playstation' and 'ps4' in (controller_name or '').lower():
        return 'Share'                                    # the PS4's is Share; the PS5's Create
    return NAMES.get(kind, NAMES['generic']).get(name) or COMMON_NAMES.get(name) or name


# --- the hints, in a controller's words -----------------------------------------------------------------
#: the keys the port's hints name, and the controller input that stands for each in a menu (ui/host.py):
#: longest first, so "Shift plus Enter" is not read as a Shift and an Enter
_MENU_KEY_WORDS = ((r'Shift plus Enter|Shift\+Enter|Shift Enter', 'x'), (r'\bEnter\b', 'a'),
                   (r'\bDelete\b', 'y'), (r'\bEscape\b', 'b'))


def menu_words(text):
    """A hint as it should be spoken: as written, or - when the player has chosen Controller buttons in
    Settings -> Miscellaneous -> Names in hints and tutorial and a controller is connected - with the keys it
    names turned into that controller's buttons that do the same in a menu: "Press Cross to select", "Square
    for the previous"."""
    if not text:
        return text
    from ..game.parameters import GameParameters
    kind = GameParameters.shared().controller_names()
    if not kind:
        return text
    import re
    for pattern, name in _MENU_KEY_WORDS:
        text = re.sub(pattern, input_name(name, kind), text)
    return text


def button_words(action: str, mode: str | None = None):
    """How a line names an action's binding on the controller the lines name (GameParameters.
    names_controller): 'the R2 button', 'a stick flicked up', or None when there is none."""
    from ..game.parameters import GameParameters
    model = GameParameters.shared().names_controller()
    if model is None:
        return None
    padmap = PadMap.for_model(model)
    names = padmap.names(action, mode)
    if not names:
        return None
    return ' or '.join('a stick flicked %s' % name[len('stick'):] if name in ('stickup', 'stickdown')
                       else 'the %s button' % padmap.name_of(name) for name in names)


# --- what the buttons do in play ------------------------------------------------------------------------
#: action -> default inputs; a dict means one binding per control scheme, as in keymap.py.  Turning is
#: here as two buttons, which turn at the keyboard's speed; the sticks turn as well, sideways and by how
#: far they are pushed (Pads.turn), and are not bound to anything - they are the pad's own.
PAD_DEFAULTS = {
    'fire': ('righttrigger',),
    'melee': ('rightshoulder',),
    'next_weapon': {'button': ('leftshoulder',), 'gesture': ('stickup',)},
    'reload': {'button': ('lefttrigger',), 'gesture': ('stickdown',)},
    'turn_left': ('dpleft',),                             # the sticks turn as well, and are not bound here
    'turn_right': ('dpright',),
    'pause': ('start',),
    'skip': ('a',),
    'timer': ('x',),
}
#: keys.json: every kind of controller that has been connected, by the name it gives itself, with its
#: bindings.  Before that there was one set for all of them ('padmap'); the first kind connected after takes
#: it over.
PAD_PROFILES_KEY = 'padmaps'
#: what Settings -> Joystick calls a row, where the keyboard's name for the action would not do: the
#: sticks turn too, and are a row of their own above these, so the buttons that turn are named apart.
PAD_LABELS = {'turn_left': 'Alternate turn left', 'turn_right': 'Alternate turn right'}

PAD_DEFAULTS_KEY = 'padmap'


def _default_bindings() -> dict:
    return {action: ({mode: list(names) for mode, names in d.items()} if isinstance(d, dict) else list(d))
            for action, d in PAD_DEFAULTS.items()}


class PadMap:
    """One kind of controller's bindings, like KeyMap's: the defaults, and a player's changes kept in
    keys.json.  Each kind - by the name the controller gives itself, "DualSense Wireless Controller", "Xbox
    Series X Controller" - has its own, made from the defaults and saved the first time it is connected."""

    _profiles: dict = {}

    @classmethod
    def for_model(cls, model: str) -> 'PadMap':
        model = model or 'Controller'
        padmap = cls._profiles.get(model)
        if padmap is None:
            padmap = cls._profiles[model] = PadMap(model)
        return padmap

    def __init__(self, model: str):
        self.model = model
        defaults = UserDefaults.standard()
        profiles = defaults.object(PAD_PROFILES_KEY)
        stored = profiles.get(model) if isinstance(profiles, dict) else None
        new = not isinstance(stored, dict)
        legacy = defaults.object(PAD_DEFAULTS_KEY) if new else None
        if isinstance(legacy, dict):
            stored = legacy
        self.bindings = _default_bindings()
        if isinstance(stored, dict):
            for action, value in stored.items():
                if action not in self.bindings:
                    continue
                if isinstance(self.bindings[action], dict) and isinstance(value, dict):
                    for mode, names in value.items():
                        if mode in self.bindings[action] and isinstance(names, list):
                            self.bindings[action][mode] = [str(n) for n in names]
                elif isinstance(value, list):
                    self.bindings[action] = [str(n) for n in value]
        if new:                                           # a kind not seen before gets a profile now
            self.save()
            if isinstance(legacy, dict):
                defaults.remove(PAD_DEFAULTS_KEY)
                defaults.synchronize()

    @staticmethod
    def mode() -> str:
        from .keymap import KeyMap
        return KeyMap.mode()

    def names(self, action: str, mode: str | None = None) -> list:
        value = self.bindings.get(action, [])
        if isinstance(value, dict):
            return list(value.get(mode or self.mode(), []))
        return list(value)

    def action_for(self, name: str, mode: str | None = None):
        for action in self.bindings:
            if name in self.names(action, mode):
                return action
        return None

    def name_of(self, name: str) -> str:
        """An input in this kind of controller's own names: 'righttrigger' -> 'R2' or 'RT'."""
        return input_name(name, family(self.model), self.model)

    def text(self, action: str, mode: str | None = None) -> str:
        """'R2', or 'L1 or Triangle', in this controller's names."""
        names = self.names(action, mode)
        if not names:
            return 'not set'
        return ' or '.join(self.name_of(n) for n in names)

    def is_default(self, action: str, mode: str | None = None) -> bool:
        default = PAD_DEFAULTS[action]
        if isinstance(default, dict):
            default = default[mode or self.mode()]
        return self.names(action, mode) == list(default)

    # --- changes, as KeyMap makes them ----------------------------------------------------------------
    #: what a player cannot bind: a stick pushed sideways turns, and the PS / Xbox / Home button is often
    #: kept by Windows or by Steam, so a binding to it could not be relied on
    UNBINDABLE = frozenset({'stickleft', 'stickright', 'guide'})

    def _store(self, action: str, names: list, mode: str) -> None:
        if isinstance(self.bindings[action], dict):
            self.bindings[action][mode] = names
        else:
            self.bindings[action] = names

    def _take_from_others(self, action: str, name: str, mode: str) -> None:
        """A button belongs to one action at a time, within the scheme it is bound for."""
        for other in self.bindings:
            if other != action and name in self.names(other, mode):
                self._store(other, [n for n in self.names(other, mode) if n != name], mode)

    def add(self, action: str, name: str) -> None:
        mode = self.mode()
        self._take_from_others(action, name, mode)
        names = self.names(action, mode)
        if name not in names:
            names.append(name)
        self._store(action, names, mode)
        self.save()

    def set(self, action: str, name: str) -> None:
        mode = self.mode()
        self._take_from_others(action, name, mode)
        self._store(action, [name], mode)
        self.save()

    def remove_last(self, action: str):
        """The button added last, taken off; None when it is the action's only one, which stays."""
        mode = self.mode()
        names = self.names(action, mode)
        if len(names) < 2:
            return None
        self._store(action, names[:-1], mode)
        self.save()
        return names[-1]

    def restore_defaults(self) -> None:
        self.bindings = _default_bindings()
        self.save()

    def save(self) -> None:
        stored = {}
        for action, bound in self.bindings.items():
            if isinstance(bound, dict):
                stored[action] = {mode: list(v) for mode, v in bound.items()}
            else:
                stored[action] = list(bound)
        defaults = UserDefaults.standard()
        profiles = defaults.object(PAD_PROFILES_KEY)
        profiles = dict(profiles) if isinstance(profiles, dict) else {}
        profiles[self.model] = stored
        defaults.set_object(profiles, PAD_PROFILES_KEY)
        defaults.synchronize()


# --- SDL itself, for what pygame does not wrap -----------------------------------------------------------
# pygame opens the controllers; the motion sensors and the DualSense's trigger effects are reached through
# the same SDL2.dll pygame loaded, by the controller's instance id, so both work on the one SDL object.  On the
# Mac it is libSDL2-2.0.0.dylib in pygame's .dylibs folder, or wherever PyInstaller put it in a build; opening
# the file pygame already has open hands back the same library rather than a second SDL.
SENSOR_ACCELEROMETER = 1                                  # SDL_SENSOR_ACCEL
TYPE_PS5 = 7                                              # SDL_CONTROLLER_TYPE_PS5
_sdl = None


def _sdl_path() -> str:
    """Where pygame's own SDL is: SDL2.dll beside pygame on Windows, libSDL2 in its .dylibs on the Mac."""
    here = os.path.dirname(pygame.__file__)
    if not host.MAC:
        return os.path.join(here, 'SDL2.dll')
    name = 'libSDL2-2.0.0.dylib'
    roots = [os.path.join(here, '.dylibs'), here, getattr(sys, '_MEIPASS', '')]
    for root in roots:
        if root and os.path.isfile(os.path.join(root, name)):
            return os.path.join(root, name)
    for root in roots:                                    # PyInstaller may keep pygame/.dylibs under its root
        candidate = os.path.join(root, 'pygame', '.dylibs', name)
        if root and os.path.isfile(candidate):
            return candidate
    return name                                           # let the loader look


def sdl():
    """pygame's SDL2, or None where it cannot be reached (then there is no shake and no trigger feel)."""
    global _sdl
    if _sdl is None:
        try:
            lib = ctypes.CDLL(_sdl_path())
            lib.SDL_GameControllerFromInstanceID.restype = ctypes.c_void_p
            lib.SDL_GameControllerFromInstanceID.argtypes = [ctypes.c_int32]
            lib.SDL_GameControllerGetType.argtypes = [ctypes.c_void_p]
            lib.SDL_GameControllerHasSensor.argtypes = [ctypes.c_void_p, ctypes.c_int]
            lib.SDL_GameControllerSetSensorEnabled.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
            lib.SDL_GameControllerGetSensorData.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                            ctypes.POINTER(ctypes.c_float), ctypes.c_int]
            lib.SDL_GameControllerSendEffect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            _sdl = lib
        except (OSError, AttributeError) as exc:
            log.info('SDL is not reachable directly (%s): no shake, no trigger effects', exc)
            _sdl = False
    return _sdl or None


# --- the DualSense's adaptive triggers ------------------------------------------------------------------
# SDL_GameControllerSendEffect hands a PS5 pad a DS5EffectsState_t: 47 bytes, of which the first says what
# to change (0x04 the right trigger, 0x08 the left) and bytes 10 and 21 start the two triggers' effects.
# The effects are the pad's own simple modes, the ones SDL's test program uses: 0x05 off, 0x01 resistance
# from a point on, 0x02 resistance between two points that gives way past the second, as a gun's trigger
# breaks.  Positions and strength run 0 to 255.
DS5_RIGHT_TRIGGER, DS5_LEFT_TRIGGER = 0x04, 0x08
TRIGGER_OFF = (0x05,)
#: R2 is a pistol's trigger: take-up, where it moves freely and nothing happens, then the wall, where the
#: sear holds and it will not go on, and pressing through the wall breaks it and fires.  The pad's own weapon
#: effect does that - resistance from `start` to `end`, then it gives way - so the take-up runs to 55% of the
#: travel, the wall holds from there to 72%, and the break at 72% is the shot; letting the trigger back out
#: to just under the wall (GUN_UP) is the reset, and it will fire again from there.  This was the catch
#: sitting just before half the travel and breaking at half,
#: which is where the game fires (GUN_DOWN): the shot comes with the break, not before it.  The catch used
#: to begin at a quarter of the travel and break half way, which felt like a long hard squeeze and then a
#: shot before the wall had been pressed through.
#: How hard it is to press through is what Settings -> Miscellaneous -> Trigger feel sets; the scale was
#: softened a step after playing with it (0xC0 was too stiff to fire at all, then Medium at 0x50 was still
#: hard), so what was Light is Medium now and Light is softer than anything there was.
GUN_TRIGGER = {'light': (0x02, 0x8C, 0xB8, 0x14), 'medium': (0x02, 0x8C, 0xB8, 0x28),
               'strong': (0x02, 0x8C, 0xB8, 0x50)}
#: L2, the reload under Button, pulls against a spring - softened the same way
RELOAD_TRIGGER = {'light': (0x01, 0x40, 0x0C), 'medium': (0x01, 0x40, 0x18), 'strong': (0x01, 0x40, 0x30)}


def ds5_effect(right=None, left=None) -> bytes:
    """The 47 bytes that set the right and/or left trigger; None leaves that trigger as it is."""
    state = bytearray(47)
    if right is not None:
        state[0] |= DS5_RIGHT_TRIGGER
        state[10:10 + len(right)] = bytes(right)
    if left is not None:
        state[0] |= DS5_LEFT_TRIGGER
        state[21:21 + len(left)] = bytes(left)
    return bytes(state)


# --- the controllers themselves -------------------------------------------------------------------------
class Pads:
    """Every controller plugged in, and what their buttons and sticks are doing.

    ``handle`` turns SDL's controller events into presses and releases of named inputs, each tagged with
    where it came from - ``(pad, input)``, or ``(pad, input, stick)`` for a stick's direction - so two pads,
    or both sticks, can hold the same input without letting go of each other."""

    _shared: 'Pads | None' = None

    @classmethod
    def shared(cls) -> 'Pads':
        if cls._shared is None:
            cls._shared = Pads()
        return cls._shared

    def __init__(self):
        self.pads: dict = {}                              # SDL instance id -> Controller
        self.names: dict = {}                             # SDL instance id -> the pad's name
        self.seen: dict = {}                              # the same, kept after it goes (a button let go)
        self.editing = None                               # whose buttons Settings -> Joystick sets
        self.axes: dict = {}                              # SDL instance id -> six axes, -1 to 1
        self.pushed: dict = {}                            # (instance id, stick) -> 'stickup' or the like
        self.held: set = set()                            # sources down now
        self.handles: dict = {}                           # SDL instance id -> SDL_GameController*
        self.accelerometers: set = set()                  # instance ids whose accelerometer is on
        self.dualsenses: set = set()                      # instance ids of PS5 pads (trigger effects)
        self.triggers_set: dict = {}                      # instance id -> the trigger feel it was given
        self.last_shake = 0.0
        self.started = False
        self.speak = None                                 # set by the host: says a pad came or went
        self.changed = None                               # set by the host: the screens are told

    def start(self) -> None:
        try:
            from pygame._sdl2 import controller
            controller.init()
            count = controller.get_count()
        except (pygame.error, ImportError) as exc:
            log.warning('game controllers are not available: %s', exc)
            self._keys_when_none()
            return
        self.started = True
        for index in range(count):
            self._open(index)
        self._keys_when_none()

    def _keys_when_none(self) -> None:
        """With no controller connected - the game starting without one, or the last one going, wherever
        the player is - Names in hints and tutorial goes back to Keyboard keys, and is saved so."""
        if self.pads:
            return
        from ..game.parameters import GameParameters
        params = GameParameters.shared()
        if params.key_names() != 'keys':
            params.set_key_names('keys')
            log.info('no controller connected: the hints name keys again')

    def _open(self, index: int):
        from pygame._sdl2 import controller
        try:
            if not controller.is_controller(index):
                return None
            pad = controller.Controller(index)
            iid = pad.as_joystick().get_instance_id()
        except pygame.error as exc:
            log.warning('controller %d could not be opened: %s', index, exc)
            return None
        if iid in self.pads:
            return None
        self.pads[iid] = pad
        self.names[iid] = self.seen[iid] = str(getattr(pad, 'name', '') or 'Controller')
        self.axes[iid] = [0.0] * 6
        PadMap.for_model(self.names[iid])                 # a kind seen for the first time gets its profile
        self._open_extras(iid)
        log.info('controller connected: %s (%s names%s%s)', self.names[iid], family(self.names[iid]),
                 ', shake' if iid in self.accelerometers else '',
                 ', trigger effects' if iid in self.dualsenses else '')
        return pad

    def _open_extras(self, iid) -> None:
        """The accelerometer, for shaking, and whether this is a DualSense, for the trigger effects."""
        lib = sdl()
        if lib is None:
            return
        handle = lib.SDL_GameControllerFromInstanceID(iid)
        if not handle:
            return
        self.handles[iid] = handle
        if lib.SDL_GameControllerHasSensor(handle, SENSOR_ACCELEROMETER):
            if lib.SDL_GameControllerSetSensorEnabled(handle, SENSOR_ACCELEROMETER, 1) == 0:
                self.accelerometers.add(iid)
        if lib.SDL_GameControllerGetType(handle) == TYPE_PS5:
            self.dualsenses.add(iid)

    # --- what is plugged in ---------------------------------------------------------------------------
    def connected(self) -> bool:
        return bool(self.pads)

    def last_name(self) -> str:
        return self.names[next(reversed(self.names))] if self.names else ''

    def connected_models(self) -> list:
        """The kinds of controller connected, by name, each once, the one connected last at the end."""
        models = []
        for name in self.names.values():
            if name in models:
                models.remove(name)
            models.append(name)
        return models

    def can_shake(self, model: str) -> bool:
        """Whether a connected controller of this kind has the movement sensor a shake needs - a DualSense,
        a DualShock 4 or a Switch Pro has; most others have not."""
        return any(iid in self.accelerometers for iid, name in self.names.items() if name == model)

    def padmap_for(self, iid) -> 'PadMap':
        """The bindings of the pad with this instance id, even just after it went."""
        return PadMap.for_model(self.names.get(iid) or self.seen.get(iid) or '')

    def editing_model(self):
        """Whose buttons Settings -> Joystick sets: the one chosen there, while it is connected, else the
        one connected last; None with none connected."""
        models = self.connected_models()
        if not models:
            return None
        return self.editing if self.editing in models else models[-1]

    # --- events ---------------------------------------------------------------------------------------
    def handle(self, event):
        """[(pressed, source, input), ...] for a controller event; None for anything else."""
        t = event.type
        if t == pygame.CONTROLLERDEVICEADDED:
            if self.started and self._open(event.device_index) is not None:
                if self.speak:
                    self.speak('%s connected.' % self.last_name())
                if self.changed:
                    self.changed()
            return []
        if t == pygame.CONTROLLERDEVICEREMOVED:
            return self._removed(self._iid(event))
        if t in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
            name = BUTTONS.get(event.button)
            if name is None or self._iid(event) not in self.pads:
                return []
            return self._set((self._iid(event), name), name, t == pygame.CONTROLLERBUTTONDOWN)
        if t == pygame.CONTROLLERAXISMOTION:
            iid = self._iid(event)
            if iid not in self.pads:
                return []
            value = max(-1.0, min(1.0, event.value / 32767.0))
            self.axes[iid][event.axis] = value
            if event.axis in TRIGGERS:
                name = TRIGGERS[event.axis]
                down = (iid, name) in self.held
                presses, lets_go = self.trigger_points(iid, name)
                if not down and value >= presses:
                    return self._set((iid, name), name, True)
                if down and value < lets_go:
                    return self._set((iid, name), name, False)
                return []
            return self._stick(iid, 0 if event.axis in STICKS[0] else 1)
        if t in (pygame.JOYAXISMOTION, pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYHATMOTION,
                 pygame.JOYBALLMOTION, pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED,
                 pygame.CONTROLLERDEVICEREMAPPED):
            return []                                     # the same pad, seen by the lower layer: not ours
        return None

    def trigger_points(self, iid, name: str):
        """How far this trigger goes down before it counts as pressed, and comes back up before it counts
        as let go.  R2 with the gun feel on it is pressed through its wall (GUN_DOWN); everything else is
        an ordinary trigger, half way down."""
        if name == 'righttrigger' and str(self.triggers_set.get(iid, 'off')).startswith('gun'):
            return GUN_DOWN, GUN_UP
        return TRIGGER_DOWN, TRIGGER_UP

    @staticmethod
    def _iid(event):
        return getattr(event, 'instance_id', getattr(event, 'which', None))

    def _set(self, source, name, pressed: bool) -> list:
        if pressed == (source in self.held):
            return []
        (self.held.add if pressed else self.held.discard)(source)
        return [(pressed, source, name)]

    def _stick(self, iid, stick: int) -> list:
        """A stick's direction as a pressed input: 'stickup', 'stickdown', 'stickleft' or 'stickright'."""
        x, y = self.axes[iid][STICKS[stick][0]], self.axes[iid][STICKS[stick][1]]
        key = (iid, stick)
        current = self.pushed.get(key)
        out = []
        if current is not None:
            along = {'stickup': -y, 'stickdown': y, 'stickleft': -x, 'stickright': x}[current]
            if along >= PUSH_UP:
                return []
            out += self._set((iid, current, stick), current, False)
            self.pushed[key] = current = None
        if max(abs(x), abs(y)) >= PUSH_DOWN:
            if abs(x) > abs(y):
                current = 'stickright' if x > 0 else 'stickleft'
            else:
                current = 'stickdown' if y > 0 else 'stickup'
            self.pushed[key] = current
            out += self._set((iid, current, stick), current, True)
        return out

    def _removed(self, iid) -> list:
        pad = self.pads.pop(iid, None)
        if pad is None:
            return []
        name = self.names.pop(iid, 'Controller')
        self.axes.pop(iid, None)
        self.handles.pop(iid, None)
        self.accelerometers.discard(iid)
        self.dualsenses.discard(iid)
        self.triggers_set.pop(iid, None)
        if not self.dualsenses:                           # its sound card goes with it
            from .haptic_audio import HapticAudio
            HapticAudio.shared().close()
        for key in [k for k in self.pushed if k[0] == iid]:
            del self.pushed[key]
        out = [(False, source, source[1]) for source in list(self.held) if source[0] == iid]
        self.held -= {source for _p, source, _n in out}
        log.info('controller disconnected: %s', name)
        self._keys_when_none()
        if self.speak:
            self.speak('%s disconnected.' % name)
        if self.changed:
            self.changed()
        return out

    # --- shaking --------------------------------------------------------------------------------------
    #: how hard a shake has to be: the accelerometer reads about 9.8 m/s2 at rest (gravity), and a firm
    #: shake of the hand goes well past twice that.  One shake is one melee, however long it goes on.
    SHAKE_ACCELERATION = 25.0
    SHAKE_INTERVAL = 0.5

    def shaken(self) -> bool:
        """Whether a pad has just been shaken - the phone game's shake, which is a melee under Gesture."""
        lib = sdl()
        if lib is None or not self.accelerometers:
            return False
        reading = (ctypes.c_float * 3)()
        now = time.monotonic()
        for iid in list(self.accelerometers):
            handle = self.handles.get(iid)
            if not handle:
                continue
            if lib.SDL_GameControllerGetSensorData(handle, SENSOR_ACCELEROMETER, reading, 3) != 0:
                continue
            size = math.sqrt(reading[0] ** 2 + reading[1] ** 2 + reading[2] ** 2)
            if size >= self.SHAKE_ACCELERATION and now - self.last_shake >= self.SHAKE_INTERVAL:
                self.last_shake = now
                return True
        return False

    # --- the DualSense's triggers --------------------------------------------------------------------
    def set_triggers(self, feel, level: str = 'medium', only=None) -> None:
        """Give every DualSense - or only the one with instance id `only` - the trigger feel `feel` names
        - 'gun' (R2 only), 'gun and reload' (R2 and L2) or 'off' - at `level` ('light', 'medium' or
        'strong'), unless it has it already.  Other pads have no such thing and are left alone."""
        lib = sdl()
        if lib is None:
            return
        if level not in GUN_TRIGGER:
            feel = 'off'
        wanted = feel if feel == 'off' else '%s, %s' % (feel, level)
        for iid in ([only] if only is not None else list(self.dualsenses)):
            if iid not in self.dualsenses or self.triggers_set.get(iid) == wanted or iid not in self.handles:
                continue
            right = GUN_TRIGGER[level] if feel in ('gun', 'gun and reload') else TRIGGER_OFF
            left = RELOAD_TRIGGER[level] if feel == 'gun and reload' else TRIGGER_OFF
            data = ds5_effect(right, left)
            if lib.SDL_GameControllerSendEffect(self.handles[iid], data, len(data)) == 0:
                self.triggers_set[iid] = wanted
            else:
                log.info('the trigger effect could not be sent to %s', self.names.get(iid))
                self.dualsenses.discard(iid)              # do not try again every frame

    def stop(self) -> None:
        """The game is closing: a DualSense keeps a trigger effect until it is told otherwise."""
        self.set_triggers('off')
        from .haptic_audio import HapticAudio
        HapticAudio.shared().close()

    # --- turning --------------------------------------------------------------------------------------
    def turn(self) -> float:
        """-1 (full left) to 1 (full right): whichever stick, on whichever pad, is pushed furthest sideways.
        Inside the dead zone it is 0; past it the speed grows in proportion to the push."""
        best = 0.0
        for axes in self.axes.values():
            for x_axis, _y_axis in STICKS:
                if abs(axes[x_axis]) > abs(best):
                    best = axes[x_axis]
        size = abs(best)
        if size <= DEAD_ZONE:
            return 0.0
        return math.copysign(min(1.0, (size - DEAD_ZONE) / (1.0 - DEAD_ZONE)), best)
