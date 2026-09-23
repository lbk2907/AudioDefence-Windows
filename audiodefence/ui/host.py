"""The window's root: presents one controller at a time plus modal overlays (UIKit presentation stand-in)."""
from __future__ import annotations

import logging
import time

import pygame

from ..game import data
from ..platform.speech import Speech
from .screens import MenuItem, MenuScreen, PlaceholderScreen, Screen

log = logging.getLogger('ui.host')


class AlertScreen(MenuScreen):
    """UIAlertView: title, message, buttons."""

    def __init__(self, host, title: str, message: str, buttons):
        """`buttons` are (label, action) pairs, or (label, action, hint) where a button needs saying more
        about - a PORT ADDITION: UIAlertView buttons have no hints."""
        super().__init__(host, title=f'{title}. {message}')
        self.items = [MenuItem(button[0], (lambda a=button[1]: (host.pop_overlay(), a and a())),
                               hint=button[2] if len(button) > 2 else None) for button in buttons]
        self.back_action = lambda: host.pop_overlay()


class ScreenManager:
    def __init__(self):
        self.screen: Screen | None = None                 # presented controller's screen
        self.overlays: list[Screen] = []                  # modal presentations on top of it
        self._held = None                                 # (event, screen, when the next repeat is due)
        self._pad_jump = False                            # Cross held: the menus' Control (see below)
        self._pad_jumped = False                          # and whether it was used as that, not tapped
        self.request_quit = lambda: log.info('quit requested with no window running')

    # --- services --------------------------------------------------------------------------------
    @staticmethod
    def screen_reader_running() -> bool:
        return Speech.shared().screen_reader_running()

    def top(self) -> Screen | None:
        return self.overlays[-1] if self.overlays else self.screen

    def top_overlay(self) -> Screen | None:
        return self.overlays[-1] if self.overlays else None

    # --- presentation (ADAppDelegate loadViewController:) ----------------------------------------
    def create_view_controller(self, class_name: str, presented: bool = False, **kwargs):
        from . import (armory, challenges, gameover, menus, settings,  # noqa: F401  (they register)
                       statsportal, tarot)
        factory = SCREEN_FACTORIES.get(class_name)
        if factory is None:
            log.warning('screen %s not ported', class_name)
            return PlaceholderScreen(self, class_name, presented=presented, **kwargs)
        return factory(self, **kwargs)

    def load_view_controller(self, controller) -> None:
        from ..game.gameplay import GameplayController
        from .gameplay_screen import GameplayScreen
        screen = GameplayScreen(self, controller) if isinstance(controller, GameplayController) else controller
        while self.overlays:
            self.pop_overlay(refocus=False)
        if self.screen is not None:
            self.screen.on_dismiss()
        self.screen = screen
        self._felt_screen_change(True)                    # PORT ADDITION: the screen you are on is felt
        screen.on_present()

    def present_over(self, _from_vc, screen) -> None:
        screen.presented_controller = True                # presentViewController: (full screen, iOS 8.3 SDK)
        self.push_overlay(screen)

    def push_overlay(self, screen: Screen) -> None:
        self.overlays.append(screen)
        self._felt_screen_change(True)                    # PORT ADDITION: going into a screen is felt
        screen.on_present()

    def pop_overlay(self, refocus: bool = True) -> None:
        if not self.overlays:
            return
        screen = self.overlays.pop()
        screen.on_dismiss()
        top = self.top()
        if refocus:                                       # PORT ADDITION: and coming back out of one
            self._felt_screen_change(False)               # the pops that clear the stack are not a way back
        if refocus and top is not None:
            presented = getattr(screen, 'presented_controller', False)
            if presented and hasattr(top, 'reappear'):
                top.reappear()
            # PORT ADDITION: closing a screen presented over this one is going *back* to a screen, so it
            # obeys "Remember cursor position": with that off the cursor starts at the top again, as it
            # does everywhere else.  An alert is not going back - the screen never went away - so the
            # cursor stays on the row that raised it whatever the setting says.
            restore = True
            if presented:
                from ..game.parameters import GameParameters
                restore = GameParameters.shared().remember_focus()
            top.on_focus(restore=restore)

    @staticmethod
    def _felt_screen_change(entering: bool) -> None:
        """PORT ADDITION: two knocks on a controller for a screen, low to high going in and high to low
        coming back out (user request).  Joystick vibration scales them like everything else."""
        from ..platform.haptics import Haptics
        if entering:
            Haptics.shared().screen_entered()
        else:
            Haptics.shared().screen_left()

    def quit_game(self) -> None:
        """PORT ADDITION: iOS apps have no Quit, so the main menu's Quit button ends the run loop.

        The engine is left running on purpose.  Shutting it down here closed the audio device while the
        rest of that main-loop pass was still to come - the button's own click sound among it - and
        S3DEngine.engine() would then open a second device to play it.  The main loop's teardown shuts the
        engine down exactly once, after the last pass."""
        log.info('quit from the main menu')
        self.request_quit()

    def show_no_diamonds_alert(self) -> None:             # -[ADNoBarViewController showNoDiamondsAlert] 0x100019990
        self.push_overlay(AlertScreen(self, data.localized('DIAMONDS_ALERT_TITLE'),
                                      data.localized('DIAMONDS_ALERT_CONTENT'), [('OK', None)]))

    def dismiss_presented(self, screen) -> None:        # [presentingViewController dismissViewControllerAnimated:]
        if screen in self.overlays:
            while self.overlays and self.overlays[-1] is not screen:
                self.pop_overlay(refocus=False)
            self.pop_overlay()

    # --- events ----------------------------------------------------------------------------------
    def handle_event(self, event) -> None:
        from ..platform.pad import Pads
        moves = Pads.shared().handle(event)               # PORT ADDITION: a game controller
        if moves is not None:
            for pressed, source, name in moves:
                self._pad_input(pressed, source, name)
            return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LCTRL, pygame.K_RCTRL) and not getattr(event, 'pad', False):
                # PORT ADDITION: Control stops the speech, as it does in a screen reader (user request).
                # The key goes on to the screen as well: it is the melee key, and held with an arrow it
                # still reaches the first or last row.
                Speech.shared().stop()
            top = self.top()
            if top is not None:
                self._hold_navigation_key(event, top)
                top.key_down(event)
        elif event.type == pygame.KEYUP:
            if self._held is not None and event.key == self._held[0].key:
                self._held = None
            # key-ups go to every screen so a key released after an overlay opened is not left "down"
            for screen in [self.screen] + list(self.overlays):
                if screen is not None:
                    screen.key_up(event)
        elif event.type == pygame.MOUSEMOTION:
            top = self.top()
            if top is not None:
                top.mouse_motion(event)

    def pads_changed(self) -> None:
        """PORT ADDITION: a controller came or went; a screen that shows something about it is told."""
        top = self.top()
        refresh = getattr(top, 'pads_changed', None)
        if refresh is not None:
            refresh()

    # PORT ADDITION: a game controller.  In play its buttons are the game's own actions (pad.PadMap); on any
    # other screen they are the keys that screen already understands, so every menu works with a pad without
    # knowing one exists.  The key presses made here carry `pad`, so a key being captured in Settings is
    # not taken from a controller button.
    def _pad_input(self, pressed: bool, source, name: str) -> None:
        from .gameplay_screen import GameplayScreen
        top = self.top()
        if isinstance(top, GameplayScreen):
            (top.pad_down if pressed else top.pad_up)(source, name)
            return
        if not pressed and isinstance(self.screen, GameplayScreen):
            self.screen.pad_up(source, name)              # held into a pause: let go in the game as well
        takes = getattr(top, 'takes_pad_input', None)
        if pressed and takes is not None and takes():     # Settings is waiting for a button to bind
            if name == self.JUMP_BUTTON:
                self._pad_jumped = True                   # bound, so letting it go is not an Enter
            top.pad_input(name)
            return
        if name == self.JUMP_BUTTON:
            self._pad_jump = pressed
            if pressed:
                self._pad_jumped = False
                return                                    # held, it may yet be the Control: wait and see
            if self._pad_jumped:                          # it was the Control, not a press of its own
                return
            for kind in (pygame.KEYDOWN, pygame.KEYUP):   # tapped alone: Enter, which is what it is for
                self.handle_event(pygame.event.Event(kind, key=pygame.K_RETURN, mod=0, unicode='',
                                                     scancode=0, pad=True))
            return
        key = self._pad_menu_key(name)
        if key is None:
            return
        code, mod = key
        if self._pad_jump:
            self._pad_jumped = True                       # Triangle was held for this, so it is not Delete
            if code in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
                mod |= pygame.KMOD_CTRL                   # to the first or last, as Control with an arrow
        self.handle_event(pygame.event.Event(pygame.KEYDOWN if pressed else pygame.KEYUP, key=code, mod=mod,
                                             unicode='', scancode=0, pad=True))

    #: PORT ADDITION: Cross held is the menus' Control: with a direction or a shoulder it goes to the first
    #: or last, as Control with an arrow does.  Tapped on its own it is Enter, which it does on the way up,
    #: since until it is let go it may yet be the Control.
    JUMP_BUTTON = 'a'

    def _pad_menu_key(self, name: str):
        """The key a controller input stands for in the menus, as (key, modifiers), or None."""
        from ..game.parameters import GameParameters
        from .gameplay_screen import GameplayScreen
        # the D-pad and the sticks are all four arrows, so they move through a screen and change tab with
        # the pair the movement is not using (Menu layout); the shoulders move through it as well, since
        # one hand on them is easier than reaching the D-pad for every row
        if GameParameters.shared().menu_axis() == 'vertical':
            move_next, move_previous = pygame.K_DOWN, pygame.K_UP
        else:
            move_next, move_previous = pygame.K_RIGHT, pygame.K_LEFT
        keys = {'dpup': pygame.K_UP, 'dpdown': pygame.K_DOWN,
                'dpleft': pygame.K_LEFT, 'dpright': pygame.K_RIGHT,
                'stickup': pygame.K_UP, 'stickdown': pygame.K_DOWN,
                'stickleft': pygame.K_LEFT, 'stickright': pygame.K_RIGHT,
                'b': pygame.K_ESCAPE, 'y': pygame.K_DELETE,
                'leftshoulder': move_previous, 'rightshoulder': move_next,
                'lefttrigger': pygame.K_PAGEDOWN, 'righttrigger': pygame.K_PAGEUP}
        if name == 'x':                                   # a row's second action, as Shift+Enter is
            return pygame.K_RETURN, pygame.KMOD_SHIFT
        if name == 'start' and isinstance(self.screen, GameplayScreen):
            return pygame.K_ESCAPE, 0                     # Options closes the pause screen it opened
        return (keys[name], 0) if name in keys else None

    # PORT ADDITION: a key held down keeps moving through a menu, the way a list behaves anywhere else.
    # Only the keys that step one element repeat: a jump to an end has nowhere to go, an activation must
    # happen once, and a held turn key in a game is the game's own business.
    REPEAT_AFTER = 0.4                                    # seconds held before the first repeat
    REPEAT_EVERY = 0.09                                   # and between repeats after that

    def _hold_navigation_key(self, event, top) -> None:
        from .accessibility import AccessibleScreen, navigation_key
        from .screens import MenuScreen
        if not isinstance(top, (AccessibleScreen, MenuScreen)):
            self._held = None
            return
        self._held = ((event, top, time.perf_counter() + self.REPEAT_AFTER)
                      if navigation_key(event) in ('next', 'previous') else None)

    def _repeat_held_key(self) -> None:
        if self._held is None:
            return
        event, screen, due = self._held
        if screen is not self.top():                      # the screen changed under the held key
            self._held = None
            return
        now = time.perf_counter()
        if now >= due:
            self._held = (event, screen, now + self.REPEAT_EVERY)
            screen.key_down(event)

    def frame(self) -> None:
        self._repeat_held_key()
        if self.screen is not None:
            self.screen.frame()
        for o in list(self.overlays):
            o.frame()


SCREEN_FACTORIES: dict = {}


def register(class_name: str):
    def deco(factory):
        SCREEN_FACTORIES[class_name] = factory
        return factory
    return deco
