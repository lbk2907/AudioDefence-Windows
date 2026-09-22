"""VoiceOver stand-in for the ported UIKit screens.

A ported screen builds its nib's views as ``View`` objects (frame from the iPhone nib, text, accessibility
label / hint, hidden / alpha / enabled state and the touch-up-inside target-actions) and the controller code
changes them exactly as the original does.  ``AccessibleScreen`` then behaves like VoiceOver on that view
tree:

    Right / Tab                 next element          (flick right)
    Left / Shift+Tab            previous element      (flick left)
    Ctrl+Right / Ctrl+Left      last / first element, as End / Home and Ctrl+Tab / Ctrl+Shift+Tab do
    Down / Up                   next / previous tab or category, where the screen has them
    Ctrl+Down / Ctrl+Up         last / first tab or category
    Enter                       activate              (double tap)
    Shift+Enter                 a row's second action, where it has one (PORT ADDITION)
    Escape / Backspace          accessibilityPerformEscape (two-finger scrub)

Settings -> Miscellaneous -> Menu layout swaps those two pairs: the arrows that move through the elements
and the arrows that change tab are always the two different pairs.

PORT APPROXIMATION: VoiceOver's reading order.  VoiceOver visits the elements of a screen top to bottom,
then left to right.  Elements are put in the same row when their vertical centres are closer than half the
height of the smaller one; a row is read left to right.  Views with ``ordered=True`` (a table) keep the order
of their children and are placed by their own frame.  Hidden views and views whose alpha is 0 (or inside
such a view) are skipped, like VoiceOver skips invisible views.
"""
from __future__ import annotations

import logging

import pygame

from ..platform import host as system
from .. import localization
from .. import localization
from .. import localization
from .. import localization
from ..s3d.engine import S3DEngine
from .screens import Screen, menu_music_volume_key

log = logging.getLogger('ui.a11y')

BUTTON = 'button'
STATIC_TEXT = 'static text'
HEADER = 'header'
CELL = 'cell'               # a UITableViewCell: selectable, read without a trait


def menu_tick() -> None:
    """PORT ADDITION: a tick on the controller as the cursor moves - one element or one tab to the next -
    so a menu is felt as well as heard (user request).  Settings -> Miscellaneous -> Joystick vibration
    scales it with everything else, and Off silences it."""
    from ..platform.haptics import Haptics
    Haptics.shared().menu()


def menu_toggle() -> None:
    """PORT ADDITION: a firmer click than the cursor's when something is activated - a setting stepped or
    toggled, a button pressed - so a change is felt as well as heard (user request)."""
    from ..platform.haptics import Haptics
    Haptics.shared().toggled()


def play_button_click() -> None:
    """-[ADButtonWithFont playSound] 0x100073578 (also ADStatusBarViewController 0x10001cde8 and
    ADPlayMenuViewController 0x1000aba0c, which are the same code)."""
    pl = S3DEngine.engine().play_list_with_name('buttons')
    sound = pl.sound('click_button') if pl is not None else None
    if sound is None:
        return
    sound.set_gain(3.0)
    sound.play()


class View:
    """A UIView as VoiceOver sees it."""

    def __init__(self, label: str = '', frame=(0.0, 0.0, 0.0, 0.0), *, traits=STATIC_TEXT, hint: str | None = None,
                 accessible: bool = True, parent: 'View | None' = None, hidden: bool = False, alpha: float = 1.0,
                 ordered: bool = False, name: str = ''):
        self.name = name                       # nib object, for logs
        self.label = label                     # accessibilityLabel (or the text / title VoiceOver reads)
        self.frame = tuple(float(v) for v in frame)   # absolute, in points
        self.traits = traits
        self.hint = hint
        self.accessible = accessible           # isAccessibilityElement (containers are not)
        self.parent = parent
        self.hidden = hidden
        self.alpha = alpha
        self.ordered = ordered                 # keep the children's order (UITableView)
        self.children: list[View] = []
        self.enabled = True                    # UIControl enabled
        # PORT ADDITION: a label of the port's that names a key a controller button stands for in a menu
        # ("press Enter to upgrade"): it is said in the controller's words when those are chosen and one
        # is connected, worked out as it is spoken so a controller coming or going is followed at once
        self.label_key_words = False
        self.user_interaction_enabled = True
        self.selected = False                  # a selected UITableViewCell: VoiceOver says "Selected"
        self.elements_hidden = False           # accessibilityElementsHidden (the view and its subtree)
        self.modal = False                     # accessibilityViewIsModal (VoiceOver skips the view's siblings)
        self.actions: list = []                # touch-up-inside target-actions, in the order they were added
        self.shift_actions: list = []           # PORT ADDITION: what Shift+Enter does on this element
        self.text = label                      # title / text shown on screen, when it differs from the label
        if parent is not None:
            parent.children.append(self)

    def __repr__(self) -> str:
        return f'<View {self.name or self.label!r}>'

    # --- text for the player --------------------------------------------------------------------
    # PORT ADDITION: the label, the hint and the text go through the localization layer as they are
    # read, so choosing another language takes effect at once and what is stored stays English.
    @property
    def label(self) -> str:
        return localization.translate(self._label)

    @label.setter
    def label(self, value: str) -> None:
        self._label = value

    @property
    def hint(self):
        return localization.translate(self._hint)

    @hint.setter
    def hint(self, value) -> None:
        self._hint = value

    @property
    def text(self) -> str:
        return localization.translate(self._text)

    @text.setter
    def text(self, value: str) -> None:
        self._text = value

    # --- UIControl -------------------------------------------------------------------------------
    def add_target(self, fn) -> None:          # addTarget:action:forControlEvents:UIControlEventTouchUpInside
        if fn not in self.actions:             # UIControl keeps one entry per target-action pair
            self.actions.append(fn)

    def set_title(self, title: str) -> None:   # setTitle:forState:0 (VoiceOver keeps the accessibilityLabel)
        self.text = title

    # --- visibility ------------------------------------------------------------------------------
    def is_visible(self) -> bool:
        v = self
        while v is not None:
            if v.hidden or v.alpha <= 0.0:
                return False
            v = v.parent
        return True

    def interaction_allowed(self) -> bool:
        v = self
        while v is not None:
            if not v.user_interaction_enabled:
                return False
            v = v.parent
        return True

    def spoken(self) -> str:
        label = self.label
        if getattr(self, 'label_key_words', False):       # PORT ADDITION: see __init__
            from ..platform.pad import menu_words
            label = menu_words(label)
        parts = ([localization.translate('Selected')] if self.selected else []) + [label]
        if self.traits == BUTTON:
            if not self.enabled:
                parts.append(localization.translate('dimmed'))
            parts.append(localization.translate('button'))
        elif self.traits == CELL and not self.enabled:      # PORT ADDITION: a row that cannot be used now
            parts.append(localization.translate('dimmed'))
        elif self.traits == HEADER:
            parts.append(localization.translate('heading'))
        text = ', '.join(p for p in parts if p)
        if self.hint:
            from ..platform.pad import menu_words         # PORT ADDITION: in a controller's words, if chosen
            text += f'. {menu_words(self.hint)}'
        return text

    def activate(self, shift: bool = False) -> bool:
        """accessibilityActivate: a double tap sends a touch to the element's centre.  PORT ADDITION: with
        Shift held, an element that has a second action runs that one instead."""
        if self.traits not in (BUTTON, CELL) or not self.enabled or not self.interaction_allowed():
            return False
        menu_toggle()                                   # PORT ADDITION: a change is felt as well as heard
        for fn in list(self.shift_actions if (shift and self.shift_actions) else self.actions):
            fn()
        return True


#: PORT ADDITION: the modifier that turns a step into a jump to the first or last: Control, and on the Mac
#: Command as well, since Command with an arrow is how a Mac goes to the start or the end of anything
JUMP_MODS = pygame.KMOD_CTRL | (pygame.KMOD_GUI if system.MAC else 0)


def navigation_key(event) -> str | None:
    """PORT ADDITION: VoiceOver is driven by swipes, so the keys that move its cursor are the port's own.

    Settings -> Keyboard chooses which pair of arrows moves through a screen (Left and Right by default);
    the other pair does nothing.  Control with that pair jumps to the first or last element, as Home and
    End do, and Tab and Shift+Tab move whichever pair is chosen."""
    from ..game.parameters import GameParameters
    k = event.key
    if k == pygame.K_TAB:
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        if event.mod & JUMP_MODS:                        # an end, wherever the cursor is
            return 'first' if shift else 'last'
        return 'previous' if shift else 'next'
    if k == pygame.K_HOME:
        return 'first'
    if k == pygame.K_END:
        return 'last'
    vertical = GameParameters.shared().menu_axis() == 'vertical'
    forward, back = (pygame.K_DOWN, pygame.K_UP) if vertical else (pygame.K_RIGHT, pygame.K_LEFT)
    ctrl = bool(event.mod & JUMP_MODS)
    if k == forward:
        return 'last' if ctrl else 'next'
    if k == back:
        return 'first' if ctrl else 'previous'
    return None


def cross_axis_key(event) -> str | None:
    """PORT ADDITION: the arrows the menu navigation is *not* using, which is what a screen with tabs or
    categories changes tab with.  Returns 'next', 'previous', 'first', 'last' or None.

    It reads like the element keys one axis over: the bare pair steps a tab, and Control with that pair
    jumps to the first or last tab the way Control with the other pair jumps to the first or last element.
    Tab is not part of this - it belongs to the elements, whichever way round the arrows are."""
    from ..game.parameters import GameParameters
    ctrl = bool(event.mod & JUMP_MODS)
    shift = bool(event.mod & pygame.KMOD_SHIFT)
    if shift or event.mod & pygame.KMOD_ALT:
        return None
    forward, back = ((pygame.K_RIGHT, pygame.K_LEFT) if GameParameters.shared().menu_axis() == 'vertical'
                     else (pygame.K_DOWN, pygame.K_UP))
    if event.key == forward:
        return 'last' if ctrl else 'next'
    if event.key == back:
        return 'first' if ctrl else 'previous'
    return None


def cross_axis_text() -> str:
    """How to say those two keys, for a screen that tells the player about them - or, with a
    controller's names chosen in Settings -> Miscellaneous, the buttons: the D-pad changes tab on the
    pair the movement is not using and the shoulders move as well (ui/host.py), "D-pad up and down
    change tab, D-pad left and right or L1 and R1 move through it"."""
    from ..game.parameters import GameParameters
    params = GameParameters.shared()
    vertical = params.menu_axis() == 'vertical'
    kind = params.controller_names()
    if kind:
        from ..platform.pad import input_name
        return 'D-pad %s change tab, D-pad %s or %s and %s move through it' % (
            'left and right' if vertical else 'up and down',
            'up and down' if vertical else 'left and right',
            input_name('leftshoulder', kind), input_name('rightshoulder', kind))
    if vertical:
        return 'Left and Right change tab, Up and Down move through it'
    return 'Up and Down change tab, Left and Right move through it'


def Button(label: str, frame, *, parent=None, actions=(), font_button: bool = True, name: str = '') -> View:
    """A nib button.  ADButtonWithFont -awakeFromNib (0x100072f7c) adds -playSound after the nib's own
    connections, so the click comes after the connected actions."""
    b = View(label, frame, traits=BUTTON, parent=parent, name=name)
    for fn in actions:
        b.add_target(fn)
    if font_button:
        b.add_target(play_button_click)
    return b


def reading_order(views) -> list[View]:
    """Visible accessible elements of ``views`` (roots or flat) in VoiceOver order."""
    units = []                                  # (frame, [elements]) sortable units

    def collect(v: View) -> None:
        if not v.is_visible() or v.elements_hidden:
            return
        if v.ordered:
            flat = []
            _flatten_ordered(v, flat)
            if flat:
                units.append((v.frame, flat))
            return
        if v.accessible:
            units.append((v.frame, [v]))
        for c in _visible_children(v):
            collect(c)

    seen = set()
    for v in views:
        root = v
        if id(root) in seen:
            continue
        seen.add(id(root))
        collect(root)

    units.sort(key=lambda u: (u[0][1] + u[0][3] / 2.0, u[0][0]))
    rows: list[list] = []
    for unit in units:
        f = unit[0]
        cy, h = f[1] + f[3] / 2.0, f[3]
        if rows:
            first = rows[-1][0][0]
            fcy, fh = first[1] + first[3] / 2.0, first[3]
            if abs(cy - fcy) < min(h, fh) / 2.0:
                rows[-1].append(unit)
                continue
        rows.append([unit])
    out: list[View] = []
    for row in rows:
        row.sort(key=lambda u: u[0][0])
        for _frame, elements in row:
            out.extend(elements)
    return out


def _visible_children(v: View) -> list:
    """accessibilityViewIsModal: VoiceOver ignores the elements of the modal view's siblings."""
    modal = [c for c in v.children if c.modal and c.is_visible() and not c.elements_hidden]
    return [modal[-1]] if modal else v.children


def _is_inside(v: View, container: View) -> bool:
    while v is not None:
        if v is container:
            return True
        v = v.parent
    return False


def _flatten_ordered(v: View, out: list) -> None:
    for c in _visible_children(v):
        if not c.is_visible() or c.elements_hidden:
            continue
        if c.accessible:
            out.append(c)
        _flatten_ordered(c, out)


#: PORT ADDITION: the label each screen was last left on, so going back returns the cursor there
_LAST_FOCUS: dict = {}


class AccessibleScreen(Screen):
    """A presented view controller driven through the VoiceOver stand-in."""

    has_escape = False          # -[ADViewController accessibilityPerformEscape] exists (ADNoBar does not)
    #: PORT ADDITION: what the screen is called, said before the element the cursor lands on.  These are the
    #: game's own names: every one of these screens sends -[ADStatusBarViewController setPageTitle:] in its
    #: viewDidLoad, and the iPhone nib has no pageTitle outlet, so the title goes to nil and is never seen
    #: or heard.  The capitals the original writes them in are not shouted here.
    page_title: str | None = None

    def __init__(self, host):
        super().__init__(host)
        self.roots: list[View] = []             # the view hierarchy: nib view first, added views after
        self.focus: View | None = None
        self._pending_focus = None              # UIAccessibilityScreenChangedNotification argument
        self._pending_prefix = None             # PORT ADDITION: said before the element it lands on
        self._screen_changed = False
        self._loaded = False
        self.presented = False

    # --- lifecycle, as UIKit drives it -----------------------------------------------------------
    def on_present(self) -> None:
        self.presented = True
        if not self._loaded:
            self._loaded = True
            self.load_view()
            self.view_did_load()
        self.view_will_appear()
        self.view_did_appear()
        self._announce_title = True                       # PORT ADDITION: name the screen as it opens
        if not self._screen_changed:
            # a presentation moves VoiceOver to the new screen: the first element gets the focus
            self.post_screen_changed(None)

    def on_dismiss(self) -> None:
        self.remember_focus()
        self.presented = False
        self.dealloc()

    def remember_focus(self) -> None:
        """PORT ADDITION: where the cursor was when this screen was left."""
        if self.focus is not None and self.focus.label:
            _LAST_FOCUS[type(self).__name__] = self.focus.label

    def reappear(self) -> None:
        """A controller presented over this one was dismissed.  The app is built with the iOS 8.3 SDK, where
        presentations are full screen: the presenting controller gets viewWillAppear: / viewDidAppear: again."""
        self._pending_focus = None
        self.view_will_appear()
        self.view_did_appear()
        self._reposted = self._pending_focus is not None

    def on_focus(self, restore: bool = True) -> None:
        # an overlay was dismissed: VoiceOver returns to this screen, unless the screen moved it itself
        if getattr(self, '_reposted', False):
            self._reposted = False
            return
        self._announce_title = True
        # PORT ADDITION: `restore` is false when a whole screen was closed over this one and cursor memory
        # is off.  The cursor then lands on this screen's first element, the way it does when the screen is
        # built fresh, instead of sitting on the row that opened the screen you just left.
        element = self.focus if restore and self.focus in self.elements() else None
        # This screen was never torn down, so where the cursor actually is beats the label remembered from
        # the last time it was closed - which can be several visits old.
        self._returning_to_live_focus = element is not None
        self.post_screen_changed(element)

    def load_view(self) -> None:
        pass

    def view_did_load(self) -> None:
        pass

    def view_will_appear(self) -> None:
        pass

    def view_did_appear(self) -> None:
        pass

    def dealloc(self) -> None:
        pass

    # --- UIAccessibility -------------------------------------------------------------------------
    def elements(self) -> list[View]:
        return reading_order(self.roots)

    def post_screen_changed(self, element: View | None, prefix: str | None = None) -> None:
        # UIAccessibilityScreenChangedNotification.  PORT ADDITION: ``prefix`` names what the player just
        # opened - a tab, a category - so it is heard before the element VoiceOver lands on.
        self._screen_changed = True
        self._pending_focus = (element,)
        self._pending_prefix = prefix

    def first_content_element(self, elements: list):
        """PORT ADDITION: where the cursor lands when nothing else has decided.

        VoiceOver starts at the first element of the screen, which on every screen with a status bar is its
        Back button, then the coins and the diamonds - chrome you have to walk past before reaching what the
        screen is for.  The cursor starts on the screen's own first element instead; Back and the currencies
        are still there, one step back."""
        if not elements:
            return None
        bar = getattr(self, 'status_bar_view_controller', None)
        bar_view = getattr(bar, 'view', None) if bar is not None else None
        if bar_view is not None:
            content = [e for e in elements if not _is_inside(e, bar_view)]
            if content:
                return content[0]
        return elements[0]

    def frame(self) -> None:
        if self._pending_focus is not None and self.host.top() is self:
            element = self._pending_focus[0]
            self._pending_focus = None
            prefix, self._pending_prefix = self._pending_prefix, None
            # PORT ADDITION: a screen names itself as you enter it, ahead of anything else it wants said.
            # Screens that post their own focus (the challenge list, the armory's tab) get the name too,
            # unless what they are saying already begins with it.
            entering, self._announce_title = getattr(self, '_announce_title', False), False
            if entering:
                title = localization.translate(self.page_title) if self.page_title else None
                if title and not (prefix or '').startswith(title):
                    prefix = '%s. %s' % (title, prefix) if prefix else title
            elements = self.elements()
            if entering:
                # PORT ADDITION: coming back to a screen puts the cursor where you left it, rather than at
                # the top.  The original rebuilds the screen every time and VoiceOver starts at the first
                # element, so leaving a challenge, the armory or the settings meant walking back down the
                # list to where you were.  The rows are new objects after the rebuild, so the element is
                # found again by its label; a screen seen for the first time has nothing to restore and
                # opens where it always did.
                from ..game.parameters import GameParameters
                live = getattr(self, '_returning_to_live_focus', False)
                self._returning_to_live_focus = False
                remembered = (_LAST_FOCUS.get(type(self).__name__)
                              if not live and GameParameters.shared().remember_focus() else None)
                if remembered:
                    element = next((e for e in elements if e.label == remembered), element)
            if element is not None and element not in elements:
                # a container was posted (a table, or a view that just became modal): VoiceOver lands on
                # the first element inside it
                inside = [e for e in elements if _is_inside(e, element)]
                element = inside[0] if inside else None
            if element is None or element not in elements:
                element = self.first_content_element(elements)
            self.focus = element
            if element is not None:
                self.speak('%s. %s' % (prefix, element.spoken()) if prefix else element.spoken())
            elif prefix:
                self.speak(prefix)

    def accessibility_perform_escape(self) -> None:
        # -[ADViewController accessibilityPerformEscape] 0x1000728e4
        if self.has_escape:
            self.back_button_pressed()

    # REMOVED (user request): the magic tap.  VoiceOver's two-finger double tap is a gesture with no
    # keyboard equivalent on iOS, and the port had bound it to F2 - a second way to press a button that
    # every screen already reads out, and on the revive screen a second way to end the run.  The original's
    # own implementations are listed in docs/PORTING_NOTES.md, with -[ADViewController
    # accessibilityPerformMagicTap] 0x100072940, whose only job was to announce that a screen has none.
    # `post_announcement`, the port's UIAccessibilityAnnouncementNotification, went with it: that
    # announcement was its only caller, and Windows has no gesture to announce the absence of.

    def back_button_pressed(self) -> None:          # -[ADNoBarViewController backButtonPressed] 0x1000195e8
        log.info('Back button')

    # --- keys ------------------------------------------------------------------------------------
    def _move(self, step: int) -> None:
        elements = self.elements()
        if not elements:
            return
        if self.focus in elements:
            i = elements.index(self.focus) + step
        else:
            i = 0 if step > 0 else len(elements) - 1
        i = max(0, min(len(elements) - 1, i))           # VoiceOver does not wrap
        self.focus = elements[i]
        menu_tick()
        self.speak(self.focus.spoken())

    def _jump(self, last: bool) -> None:
        elements = self.elements()
        if elements:
            self.focus = elements[-1] if last else elements[0]
            menu_tick()
            self.speak(self.focus.spoken())

    def key_down(self, event) -> None:
        if menu_music_volume_key(self, event):             # PORT ADDITION: Page Up / Page Down
            return
        k = event.key
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        move = navigation_key(event)
        if move == 'next':
            self._move(1)
        elif move == 'previous':
            self._move(-1)
        elif move == 'first':
            self._jump(False)
        elif move == 'last':
            self._jump(True)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            # Space activated too, until it was taken off (user request).  It stays the gameplay
            # fire key, which is its only job now.
            if self.focus is not None and self.focus in self.elements():
                self.focus.activate(shift)
        elif k in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.accessibility_perform_escape()
