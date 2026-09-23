"""ADTarotViewController and ADTarotCardViewController: Dr Bastard's tarot, shown before every Endless game."""
from __future__ import annotations

import logging

from ..app import App
from ..game import data
from ..platform import crand
from ..platform.defaults import UserDefaults
from ..platform.runloop import RunLoop
from ..platform.speech import Speech
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from .accessibility import BUTTON, Button, View
from .host import register
from .viewcontroller import ViewControllerScreen

log = logging.getLogger('ui.tarot')


def _cards_for_level(level: int) -> list:
    """[[NSDictionary dictionaryWithContentsOfURL:Tarot.plist] objectForKey:"level_%i"]."""
    return list((data.plist_ro('Tarot') or {}).get('level_%i' % level) or [])


def cards_in_play() -> list:
    """PORT ADDITION: [(1, title), (2, title)] - the two cards this Endless run was dealt, for the game-over
    screen's first row and so for Copy results.

    They are kept as tarotCard1 and tarotCard2, each by its selector, and a selector is looked up in its
    own level of Tarot.plist: the same selector names a different card on another level.  The game-over
    screen clears them as it opens after a long enough run, so it has to ask before that."""
    out = []
    defaults = UserDefaults.standard()
    for level in (1, 2):                                  # cardsToLoad is 2: one card from each level
        selector = defaults.object('tarotCard%i' % level)
        if selector is None:
            continue
        title = next((card.get('title') for card in _cards_for_level(level)
                      if card.get('selector') == selector), None)
        if title:
            out.append((level, title))
    return out


def _flip_sound_play() -> None:
    pl = S3DEngine.engine().play_list_with_name('tarot')
    sound = pl.any_sound_containing('flip') if pl is not None else None
    if sound is not None:
        sound.play()


class TarotCardViewController:
    """ADTarotCardViewController (an ADNoBarViewController whose view the tarot screen adds as a subview).

    Card views (nib ADTarotCardViewController): view #18 (140x190), cardFront #62 (image, cardTitle #79,
    cardDescription #22, changeCardButton #42), cardBack #75 (image).  Frames of the subviews are relative to
    the card view; ``place`` turns them into screen frames once the tarot screen has positioned the card.
    """

    def __init__(self, host, card_level: int, modifier=None):   # initWithCardLevel:modifier: 0x1000a54c4
        self.host = host
        self.card_level = card_level
        self.card_dictionary = None
        cards = _cards_for_level(card_level)
        for entry in cards:
            if modifier is not None and entry.get('selector') == modifier:
                self.card_dictionary = entry
        if self.card_dictionary is None and cards:
            self.card_dictionary = cards[crand.rand() % len(cards)]
        self.tarot_view_controller = None
        self.cost = 0
        self.current_title = None
        self.flipped = False
        self.accessible_card: View | None = None
        self._view: View | None = None
        self._relative: dict = {}

    # --- view ------------------------------------------------------------------------------------
    @property
    def view(self) -> View:
        if self._view is None:
            self.load_view()
            self.view_did_load()
        return self._view

    def load_view(self) -> None:                          # UIViewController loadView (nib ADTarotCardViewController)
        self._view = View('', (0, 0, 140, 190), accessible=False, name='card #18')
        self.card_front = View('', (0, 0, 130, 190), accessible=False, name='cardFront #62')
        self.card_title = View('Label', (15, 39, 100, 25), parent=self.card_front, name='#79')
        self.card_description = View('Label', (15, 64, 100, 77), parent=self.card_front, name='#22')
        self.change_card_button = Button('Button', (15, 141, 100, 25), parent=self.card_front,
                                         actions=[self.change_card_button_pressed], name='#42')
        self.card_back = View('', (0, 0, 130, 190), accessible=False, name='cardBack #75')
        for v in (self.card_front, self.card_title, self.card_description, self.change_card_button, self.card_back):
            self._relative[id(v)] = v.frame

    def set_center(self, cx: float, cy: float) -> None:   # [[card view] setCenter:] in the container's coordinates
        w, h = self._view.frame[2], self._view.frame[3]
        self._view.frame = (cx - w / 2.0, cy - h / 2.0, w, h)
        self.place()

    def place(self) -> None:
        ox, oy = self._view.frame[0], self._view.frame[1]
        for child in self._view.children:
            self._place_tree(child, ox, oy)

    def _place_tree(self, v: View, ox: float, oy: float) -> None:
        rel = self._relative.get(id(v))
        if rel is not None:
            v.frame = (ox + rel[0], oy + rel[1], rel[2], rel[3])
        for c in v.children:
            self._place_tree(c, ox, oy)

    def _set_card_face(self, face: View) -> None:          # transitionFromView:toView: swaps the subview
        for old in (self.card_front, self.card_back):
            if old in self._view.children:
                self._view.children.remove(old)
                old.parent = None
        face.parent = self._view
        self._view.children.append(face)
        self.place()

    def view_did_load(self) -> None:                      # 0x1000a4bd4
        if self.card_level == 1:
            self.cost = 3
        if self.card_level == 2:
            self.cost = 2
        if self.card_level == 3:
            self.cost = 1
        # changeCardButton setDiamonds:cost -> -setTitle:forState: labels it "<title> diamonds"
        title = 'Change for %d' % self.cost
        self.change_card_button.set_title(title)
        self.change_card_button.label = '%s diamonds' % title
        if self.host.screen_reader_running():
            self._view.children.clear()                   # [[view subviews] makeObjectsPerformSelector:removeFromSuperview]
            # [[ADButtonWithFont alloc] initWithFrame:view.frame]: no -awakeFromNib, so no click sound
            self.accessible_card = View('', self._view.frame, traits=BUTTON, parent=self._view, name='accessibleCard')
            self.accessible_card.label_key_words = True   # PORT ADDITION: "press Enter to change", or a button
            self._relative[id(self.accessible_card)] = self._view.frame
            self.refresh_card()
        else:
            self.refresh_card()
            self._set_card_face(self.card_back)

    def refresh_card(self) -> None:                       # 0x1000a58e0
        if self.host.screen_reader_running():
            card = self.accessible_card
            self.refresh_accessible_text()
            card.add_target(self.change_card_button_pressed)
            # makeAccessible / setupAsAccessibleTarotCardInfo: colours and fonts
        else:
            self.card_title.label = self.card_dictionary.get('title')
            self.card_description.label = self.card_dictionary.get('description')
            # backgroundImage: cards_front_bad / cards_front_good
        self.current_title = self.card_dictionary.get('title')

    def flip_card(self, animated_change: bool) -> None:   # flipCard: 0x1000a5e50
        if self.host.screen_reader_running():
            # DIVERGENCE: the original leaves here (UIAccessibilityIsVoiceOverRunning at 0x1000a5e78), and
            # since the flip sound is played at the end of the animation, a VoiceOver player hears nothing
            # while the cards are dealt - the deal is two seconds of silence.  The port keeps the animation
            # skipped and plays the sound, so the deal is something you can hear.
            _flip_sound_play()
            return
        to_view = self.card_back if self.flipped else self.card_front
        self._set_card_face(to_view)

        def completion():                                 # flipCard:_block_invoke 0x1000a60d0
            self.flipped = not self.flipped
            if animated_change:
                self.change_card()
                self.flip_card(False)
        RunLoop.main().call_later(0.5, completion)
        _flip_sound_play()

    def refresh_accessible_text(self) -> None:
        """PORT ADDITION: what refreshCard says, without re-adding the card's action.

        The action is added once, when the card is dealt.  Anything that only needs the words again -
        coming back to this screen with a different number of diamonds - calls this instead, because
        adding the target twice would change the card twice, and charge twice, on one press."""
        from ..game.inventory import Inventory
        card = self.accessible_card
        card.set_title(self.accessible_description())
        card.label = self.accessible_description()
        card.hint = 'You have %i diamonds' % Inventory.shared().diamonds

    def accessible_description(self) -> str:             # 0x1000a61a0
        # PORT INPUT: the original says "(double tap to change for %i diamonds)"; the port names its key
        return 'Tarot card number %i : %s \n\n %s \n\n(press Enter to change for %i diamonds)' % (
            self.card_level, self.card_dictionary.get('title'), self.card_dictionary.get('description'), self.cost)

    def change_card_button_pressed(self) -> None:         # changeCardButtonPressed: 0x1000a62b8
        from ..game.inventory import Inventory
        if not Inventory.shared().diamonds >= self.cost:
            self.host.show_no_diamonds_alert()
            return
        if self.host.screen_reader_running():
            _flip_sound_play()
            self.change_card()
        else:
            self.flip_card(True)
        status_bar = App.delegate().status_bar
        if status_bar is not None:
            status_bar.animate_diamonds(-self.cost)
        Inventory.shared().set_diamonds(Inventory.shared().diamonds - self.cost)
        # DIVERGENCE: changeCardButtonPressed: 0x1000a62b8 runs -changeCard (0x1000a63fc, which ends in
        # -refreshCard) BEFORE -setDiamonds: at 0x1000a6518, so the card's "You have %i diamonds" hint is
        # built from the count you had before paying; the other card is never refreshed at all and keeps
        # the number it was dealt with.  Both cards are refreshed here, after the money has moved.
        if self.host.screen_reader_running():
            screen = self.tarot_view_controller
            for card in (screen.tarot_cards if screen is not None else [self]):
                card.refresh_card()
            # PORT ADDITION: the card's label is rewritten under a cursor that is already on it, and a
            # screen reader has no reason to read a label it is not being moved onto, so the player was
            # left holding a card whose words they could only hear by arrowing off it and back.  Saying
            # it is what the cursor would say if it landed here now - View.spoken(), the same text the
            # arrow keys produce - so the new card is heard exactly as a card is normally heard.
            self.announce_card()

    def announce_card(self) -> None:                      # PORT ADDITION
        """Read the card out the way the cursor reads it, after it has changed under the cursor."""
        card = self.accessible_card
        if card is None:
            return
        screen = self.tarot_view_controller
        speak = screen.speak if screen is not None else Speech.shared().speak
        speak(card.spoken())

    def change_card(self) -> None:                        # 0x1000a65a4
        cards = _cards_for_level(self.card_level)
        self.card_dictionary = cards[crand.rand() % len(cards)]
        while self.card_dictionary.get('title') == self.current_title:
            self.card_dictionary = cards[crand.rand() % len(cards)]
        self.refresh_card()
        # DIVERGENCE (user request): the original never stores the card you paid for.  Only
        # loadCardWithNumber: 0x100035390 writes tarotCardN, and only when the key is missing, so leaving
        # the screen and coming back deals the stored card again and the diamonds are gone.  The new card
        # is saved here under the same key, the way the deal saves the first one.  Nothing else changes:
        # applyAllModifiers 0x100035a5c still reads the live card, and resetCardsModifiersIfNeeded
        # 0x1000d42a8 still clears all three keys after an endless game lasting over 60 seconds.
        defaults = UserDefaults.standard()
        defaults.set_object(self.modifier_name(), 'tarotCard%i' % self.card_level)
        defaults.synchronize()

    def modifier_name(self):                              # 0x1000a68c8
        return self.card_dictionary.get('selector')

    def is_good(self) -> bool:                            # 0x1000a68ec
        return self.card_dictionary.get('goodbad') == 'good'


@register('ADTarotViewController')
class TarotScreen(ViewControllerScreen):
    """ADTarotViewController."""
    #: the original's own title here is "Dr Bastard's Tarot"; this screen is how Endless starts,
    #: and the button that reaches it says Endless, so it is named for where you are.
    page_title = 'Endless'

    def __init__(self, host):
        super().__init__(host)
        self.backbuttonpressed = False
        self.dealing = False                              # PORT ADDITION: the cards are being dealt
        self.tarot_playlist = None
        self.tarot_cards: list[TarotCardViewController] = []
        self.cards_to_load = 0

    def load_view(self) -> None:                          # 0x1000351c4 (view #121)
        v = self.view = View('', (0, 0, 568, 320), accessible=False, name='#121')
        self.info_text = View("Dr. Bastard's tarot cards will disrupt your game", (96, 55, 392, 39), parent=v,
                              name='#20')
        self.card_container = View('', (60, 95, 460, 190), accessible=False, parent=v, name='#115')
        self.play_button = Button('Play', (234, 272, 100, 60), parent=v, actions=[self.play_button_pressed],
                                  name='#71')
        self.play_button.alpha = 0.0                      # nib alpha
        self.mission_button = None                        # no missionButton outlet in the nib
        self.roots = [v]

    def view_will_appear(self) -> None:
        # DIVERGENCE: -refreshCard 0x1000a58e0 runs when a card is dealt and when one is changed, and
        # nothing runs it when this screen comes back.  A card's hint carries the count of diamonds you
        # had when it was dealt, so after spending in the armory - which is presented over this screen -
        # the card still said "You have 500 diamonds" until something else happened to rebuild it.  The
        # words are refreshed on the way in; the card, its cost and its action are untouched.
        super().view_will_appear()
        for card in self.tarot_cards:
            if getattr(card, 'accessible_card', None) is not None and self.host.screen_reader_running():
                card.refresh_accessible_text()

    def view_did_load(self) -> None:                      # 0x10003461c
        super().view_did_load()
        # [self loadMissionOverlay]: ADMissionTopbarViewController's view is added with alpha 0 behind the
        # screen and only its missionButton (not connected) or showMissionsOverlay: (not connected) open it,
        # so VoiceOver never reaches it.  Not ported.
        sb = self.status_bar_view_controller
        sb.set_armory_button_visibility(True)
        sb.armory_button.alpha = 0.0
        sb.set_currencies_visibility(True)
        sb.set_diamonds_visibility(True)
        sb.armory_loadout_enabled = False
        sb.delegate = self
        self.tarot_playlist = S3DEngine.engine().play_list_with_name('tarot')
        if self.tarot_playlist is not None:
            self.tarot_playlist.activate()
        if UserDefaults.standard().object('tarotCard1') is not None:
            self.info_text.text = data.localized('TAROT_NO_RELOAD')
        else:
            self.info_text.text = data.localized('TAROT_INFO')
        self.info_text.label = data.spoken_text(self.info_text.text)
        self.tarot_cards = []
        if self.host.screen_reader_running():
            # the original already lets a VoiceOver player press Play before the deal finishes.
            # DIVERGENCE: the Armory and Back buttons are dimmed until then (deactivate_buttons), and Play
            # was the one button on the screen that was not; it is dimmed with them now, and comes back
            # when the cards are dealt, as it does for a sighted player.
            self.play_button.alpha = 1.0
            self.play_button.enabled = False
            self.play_button.user_interaction_enabled = False
        else:
            self.play_button.user_interaction_enabled = False
        sb.deactivate_buttons()
        self.dealing = True
        self.cards_to_load = 2
        n = 0
        while True:
            self.load_card_with_number(n + 1)
            n += 1
            if not n < self.cards_to_load:
                break
        RunLoop.main().call_later(2.3, self._cards_dealt)

    def _cards_dealt(self) -> None:                       # viewDidLoad_block_invoke 0x100034e84
        self.dealing = False
        if self.backbuttonpressed:
            return
        sb = self.status_bar_view_controller
        self.play_button.alpha = 1.0                      # 0.5 s animation
        if sb is not None:
            sb.armory_button.alpha = 1.0                  # 1 s animation (missionButton is nil)
            sb.activate_buttons()
        self.play_button.enabled = True
        self.play_button.user_interaction_enabled = True
        if sb is not None:
            sb.armory_loadout_enabled = True
            sb.set_armory_button_visibility(True)

    def load_card_with_number(self, number: int) -> None:   # loadCardWithNumber: 0x100035390
        defaults = UserDefaults.standard()
        key = 'tarotCard%i' % number
        if defaults.object(key) is not None:
            card = TarotCardViewController(self.host, number, defaults.object(key))
        else:
            card = TarotCardViewController(self.host, number, None)
            defaults.set_object(card.modifier_name(), key)
            defaults.synchronize()
        card.tarot_view_controller = self
        self.tarot_cards.append(card)
        container = self.card_container.frame
        card_view = card.view                              # loads the card (its viewDidLoad runs here)
        card_view.parent = self.card_container
        self.card_container.children.append(card_view)
        w = card_view.frame[2]
        t1 = (container[2] - w * float(self.cards_to_load)) / float(self.cards_to_load + 1)
        cx = (t1 + w * 0.5) + float(number - 1) * (t1 + w)
        cy = container[3] * 0.5 + -10.0
        card.set_center(container[0] + cx, container[1] + cy)
        # QUIRK: dispatch_after is given the card number as its dispatch_time_t, a time already past, so the
        # block runs on the next pass; it then flips the card after <number> seconds
        RunLoop.main().call_soon(
            lambda: RunLoop.main().call_later(float(number), lambda: card.flip_card(False)))

    def reroll_card_with_number(self, number: int) -> None:   # 0x100035a48
        self.record_card_reload_with_number(number)

    def apply_all_modifiers(self) -> None:                # 0x100035a5c
        dims = {}
        for card in self.tarot_cards:
            self.apply_modifier(card.modifier_name())
            dims[card.modifier_name()] = bool(card.is_good())
        Tracker.shared().init_game_play_tracker()        # +[ADTracker initGamePlayTracker]
        Tracker.shared().set_modifier_dimensions(dims)

    @staticmethod
    def apply_modifier(name) -> None:                     # applyModifier: 0x100035da4
        from ..game.modifiers import GameModifiers
        values = {}
        if name and GameModifiers.shared().has_setter(name):
            values[name] = True
        for key, value in values.items():                 # setValuesForKeysWithDictionary:
            GameModifiers.shared().apply_setter(key, value)

    def play_button_pressed(self) -> None:                # playButtonPressed: 0x100036020
        from ..game.modifiers import GameModifiers
        GameModifiers.shared().reset_modifiers()
        self.apply_all_modifiers()
        App.delegate().go_to_gameplay()

    def show_missions_overlay(self) -> None:              # showMissionsOverlay: 0x1000361b8 (not connected)
        pass

    def record_card_reload_with_number(self, number: int) -> None:   # 0x100036220: analytics only
        pass

    #: PORT DIVERGENCE: Escape - and Circle on a controller, which stands for it - does nothing while the
    #: cards are being dealt (user request).  The Back button is dimmed for those two seconds
    #: (`deactivate_buttons`) and so is Play, but `accessibilityPerformEscape` 0x1000728e4 goes straight to
    #: `backButtonPressed` without asking whether the button it stands for can be pressed, so the original
    #: leaves the screen mid-deal and the port did too.  The screen says why rather than doing nothing
    #: silently, since a key that does nothing at all reads as a game that has stopped listening.
    DEALING_ESCAPE = 'The cards are still being dealt.'

    def accessibility_perform_escape(self) -> None:
        if self.dealing:
            self.speak(self.DEALING_ESCAPE)
            return
        super().accessibility_perform_escape()

    def back_button_pressed(self) -> None:                # 0x1000364e8
        if self.dealing:                                  # the button itself is dimmed; this is the rest
            return
        self.backbuttonpressed = True
        App.delegate().go_to_play_menu()

    def dealloc(self) -> None:                            # 0x100036598
        if self.tarot_playlist is not None:
            self.tarot_playlist.deactivate()
        super().dealloc()

    # REMOVED (user request): the magic tap 0x100036634 pressed Play.
