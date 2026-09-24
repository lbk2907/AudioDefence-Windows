"""Keyboard screens that stand in for the original view controllers.

Every screen is navigated with the keyboard and speaks through ``Speech`` (VoiceOver's role).
A ``MenuScreen`` presents a view's accessible elements in the order VoiceOver would visit them:
Left/Right (or Tab/Shift+Tab) move, Enter/Space activate, Escape triggers the screen's back action.
"""
from __future__ import annotations

import logging

import pygame

from ..platform.speech import Speech

log = logging.getLogger('ui')


class Screen:
    """Base class: a presented controller."""

    def __init__(self, host):
        self.host = host

    # lifecycle (viewDidLoad / viewWillAppear / viewDidAppear / viewWillDisappear)
    def on_present(self) -> None:
        pass

    def on_dismiss(self) -> None:
        pass

    def on_focus(self, restore: bool = True) -> None:
        """Called when the screen becomes the top screen again (an overlay was dismissed).

        ``restore`` is false when the cursor should not go back to where this screen left it."""

    def key_down(self, event) -> None:
        pass

    def key_up(self, event) -> None:
        pass

    def mouse_motion(self, event) -> None:
        pass

    def frame(self) -> None:
        """Called once per main-loop pass."""

    @staticmethod
    def speak(text, interrupt: bool = True) -> None:
        Speech.shared().speak(text, interrupt)


def menu_music_volume_key(screen, event) -> bool:
    """PORT ADDITION: Page Up and Page Down make the menu music louder and quieter, on every menu screen.

    Not in a game: while the screen underneath is the gameplay, the pause and revive screens over it
    leave the keys alone too, since no menu music plays there.  The volume goes from 0 to 100% in steps
    of 10 and holds at both ends; 100% is the music as loud as the original plays it, never louder.
    Returns True when the key was used."""
    if event.key not in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
        return False
    from .gameplay_screen import GameplayScreen
    if isinstance(getattr(screen.host, 'screen', None), GameplayScreen):
        return False
    from ..app import App
    from ..game.parameters import GameParameters
    params = GameParameters.shared()
    steps = params.MENU_MUSIC_VOLUMES
    step = 1 if event.key == pygame.K_PAGEUP else -1
    volume = steps[min(max(steps.index(params.menu_music_volume()) + step, 0), len(steps) - 1)]
    params.set_menu_music_volume(volume)
    App.apply_menu_music_volume()
    Speech.shared().speak('Menu music volume %i%%' % volume)
    return True


class MenuItem:
    def __init__(self, label, action=None, hint: str | None = None, enabled=True):
        self._label = label
        self.action = action
        self.hint = hint
        self._enabled = enabled

    @property
    def label(self) -> str:
        return self._label() if callable(self._label) else str(self._label)

    @property
    def enabled(self) -> bool:
        return bool(self._enabled() if callable(self._enabled) else self._enabled)

    def spoken(self) -> str:
        text = self.label
        if not self.enabled:
            text += ', dimmed'
        if self.hint:
            from ..platform.pad import menu_words         # PORT ADDITION: in a controller's words, if chosen
            text += f'. {menu_words(self.hint)}'
        return text


#: what already ends a sentence, so a full stop after it would be a second one
ENDS_A_SENTENCE = '.!?:'


def joined(parts) -> str:
    """PORT ADDITION: the parts of a line, read one after another with a full stop between them - and not
    a second one where a part already ends a sentence of its own.

    An alert is two of those in a row: its title ends in a mark ("Not enough Coins!") and its message in a
    stop, so the line read out was "Not enough Coins!. ... playing Endless Mode.. OK".
    """
    out = ''
    for part in parts:
        part = str(part).strip()
        if not part:
            continue
        if out:
            out += ' ' if out[-1] in ENDS_A_SENTENCE else '. '
        out += part
    return out


class MenuScreen(Screen):
    title = ''

    def __init__(self, host, items=None, title: str | None = None, back=None):
        super().__init__(host)
        self.items: list[MenuItem] = list(items or [])
        if title is not None:
            self.title = title
        self.back_action = back
        self.index = 0

    def on_present(self) -> None:
        self.announce_screen()

    def on_focus(self, restore: bool = True) -> None:
        self.announce_screen()

    def announce_screen(self) -> None:
        parts = []
        if self.title:
            parts.append(self.title)
        if self.items:
            self.index = min(self.index, len(self.items) - 1)
            parts.append(self.items[self.index].spoken())
        self.speak(joined(parts))

    def current(self) -> MenuItem | None:
        return self.items[self.index] if self.items else None

    def move(self, step: int) -> None:
        from .accessibility import menu_tick             # imported here: accessibility imports this module
        if not self.items:
            return
        # VoiceOver stops at the first and last element rather than wrapping round, and so does this
        self.index = max(0, min(len(self.items) - 1, self.index + step))
        menu_tick()                                       # PORT ADDITION: felt as well as heard
        self.speak(self.items[self.index].spoken())

    def activate(self) -> None:
        from .accessibility import menu_toggle           # imported here: accessibility imports this module
        item = self.current()
        if item is None:
            return
        if not item.enabled:
            self.speak(item.spoken())
            return
        menu_toggle()                                   # PORT ADDITION: felt as well as heard
        if item.action is not None:
            item.action()

    def key_down(self, event) -> None:
        from .accessibility import menu_tick, navigation_key   # here: accessibility imports this module
        if menu_music_volume_key(self, event):
            return
        k = event.key
        move = navigation_key(event)
        if move in ('next', 'previous'):
            self.move(1 if move == 'next' else -1)
        elif move in ('first', 'last') and self.items:
            self.index = 0 if move == 'first' else len(self.items) - 1
            menu_tick()
            self.speak(self.items[self.index].spoken())
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):   # not Space: it is the fire key in a game
            self.activate()
        elif k == pygame.K_ESCAPE and self.back_action is not None:
            self.back_action()


class PlaceholderScreen(MenuScreen):
    """A screen whose controller is not ported.  A presented one closes; a loaded one offers the main menu."""

    def __init__(self, host, class_name: str, presented: bool = False, **kwargs):
        from ..app import App
        super().__init__(host, title=f'{class_name} is not ported yet')
        self.class_name = class_name
        if presented:
            self.items = [MenuItem('Close', lambda: host.dismiss_presented(self))]
            self.back_action = lambda: host.dismiss_presented(self)
        else:
            self.items = [MenuItem('Main menu', App.delegate().go_to_main_menu)]
            self.back_action = App.delegate().go_to_main_menu
