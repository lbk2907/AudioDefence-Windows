"""ADNoBarViewController / ADViewController and the ADStatusBarViewController every menu screen loads.

Layouts are the iPhone nibs' tag-2781 views (the 568x320 layout whose outlets the nib connects directly;
-[UIViewController(ADIPhoneLoader) loADViewBasedOnDeviceWithNibName:WithTagDictionary:] 0x10005d22c).
PORT CHOICE: the port always uses that iPhone layout.
"""
from __future__ import annotations

import logging

from ..platform.cfloat import f32
from ..platform.runloop import RunLoop
from .accessibility import AccessibleScreen, Button, View

log = logging.getLogger('ui.vc')


class StatusBar:
    """ADStatusBarViewController (nib ADStatusBarViewController, tag-2781 view #87)."""

    def __init__(self):                                   # initWithNibName:bundle: 0x10001bd70 / loadView 0x10001c034
        self.screen = None                                # the screen it was made for (`_wanted`)
        self.view = View('', (0, 0, 568, 50), accessible=False, name='#87')
        self.back_button = Button('Back', (8, 0, 150, 40), parent=self.view, name='#74')
        self.back_button.text = '  BACK'
        self.currencies_view = View('', (189, 0, 190, 40), accessible=False, parent=self.view,
                                    name='#108 ADSlidingView')
        self.coins_label = None
        self.diamonds_label = None
        # outlets are connected while the nib loads: -setCoinsLabel: / -setDiamondsLabel: set the labels
        self.set_coins_label(View('', (224, 5, 60, 30), parent=self.currencies_view, name='#1'))
        self.coins_label.text = '50'
        self.set_diamonds_label(View('', (316, 5, 60, 30), parent=self.currencies_view, name='#106'))
        self.diamonds_label.text = '50000'
        self.armory_button = Button('Armory', (410, 0, 150, 40), parent=self.view,
                                    actions=[self.armory_button_pressed], name='#70')
        self.armory_button.text = 'ARMORY'
        self.page_title = None                            # no pageTitle outlet in the iPhone nib: messages go to nil
        self.delegate = None
        self.back_button_delegate = None                  # <ADBackAction>, set by the armory's detail views
        self.armory_loadout_enabled = False
        self.slide_completion = None
        self.animation_timer_for_coins = None
        self.animation_timer_for_diamonds = None
        self.coins_float_value = 0.0
        self.coins_wanted_value = 0
        self.coins_step = 0.0
        self.coin_animation_ratio = 0
        self.diamonds_float_value = 0.0
        self.diamonds_wanted_value = 0
        self.diamonds_step = 0.0
        self.view_did_load()

    def view_did_load(self) -> None:                      # 0x10001be70 (fonts are visual)
        self.armory_button.set_title('Armory')

    def view_will_appear(self) -> None:                   # 0x10001c24c
        self.refresh_coins_and_diamonds()

    def view_did_appear(self) -> None:                    # 0x10001c2a8: [currenciesView slide] (animation)
        pass

    def set_slide_view_callback(self, block) -> None:     # 0x10001c33c
        self.slide_completion = block

    @staticmethod
    def _inventory():
        from ..game.inventory import Inventory
        return Inventory.shared()

    def refresh_coins_and_diamonds(self) -> None:         # 0x10001c3d0
        inv = self._inventory()
        self.coins_label.text = '%d' % inv.coins
        self.diamonds_label.text = '%i' % inv.diamonds
        self.coins_label.label = '%i coins' % inv.coins
        self.diamonds_label.label = '%i diamonds' % inv.diamonds

    def set_coins_label(self, label: View) -> None:       # 0x10001d278
        self.coins_label = label
        self.coins_label.label = '%i coins' % self._inventory().coins

    def set_diamonds_label(self, label: View) -> None:    # 0x10001d394
        self.diamonds_label = label
        self.diamonds_label.label = '%i diamonds' % self._inventory().diamonds

    # --- counters --------------------------------------------------------------------------------
    # DIVERGENCE: -[ADStatusBarViewController animateCoins:] 0x10001c728, animateDiamonds: 0x10001c850
    # and the two timer methods 0x10001ca14 / 0x10001cb68 only ever call -setText:.  The spoken label is
    # set once by setCoinsLabel:/setDiamondsLabel: (0x10001d278 / 0x10001d394) and refreshed only by
    # refreshCoinsAndDiamonds (0x10001c3d0), so in the original a VoiceOver player hears the count from
    # before the purchase until some other screen happens to refresh it - the tarot screen never does.
    # The number on screen is right the whole time, so the port keeps the spoken label in step with it.
    def animate_coins_from_center(self, amount: int, center) -> None:   # animateCoins:fromCenter: 0x10001c704
        self.animate_coins(amount)

    def animate_coins(self, amount: int) -> None:         # animateCoins: 0x10001c728
        self.coins_float_value = f32(self._inventory().coins)
        self.coins_wanted_value = int(f32(f32(amount) + self.coins_float_value))
        self.coins_step = f32(f32(amount) / 60.0)
        if self.coins_step != 0.0:
            self.animation_timer_for_coins = RunLoop.main().schedule_timer(0.0166667, self.animate_coins_tick, True)

    def animate_diamonds(self, amount: int) -> None:      # animateDiamonds: 0x10001c850
        self.diamonds_float_value = f32(self._inventory().diamonds)
        self.diamonds_wanted_value = int(f32(f32(amount) + self.diamonds_float_value))
        if abs(f32(amount)) < 5.0:
            self.diamonds_label.text = '%i' % self.diamonds_wanted_value
            self.diamonds_label.label = '%i diamonds' % self.diamonds_wanted_value
            return
        self.diamonds_step = f32(f32(amount) / 60.0)
        self.animation_timer_for_diamonds = RunLoop.main().schedule_timer(0.0166667, self.animate_diamonds_tick, True)

    def animate_coins_tick(self) -> None:                 # animateCoins 0x10001ca14
        wanted = f32(self.coins_wanted_value)
        before = abs(f32(self.coins_float_value - wanted))            # distance before the step
        self.coins_float_value = f32(self.coins_float_value + self.coins_step)
        if not before >= abs(f32(self.coins_float_value - wanted)):   # the step went past the wanted value
            self.coins_float_value = wanted
            if self.animation_timer_for_coins is not None:
                self.animation_timer_for_coins.invalidate()
            self.coins_step = 0.0
        self.coin_animation_ratio -= 1
        self.coins_label.text = '%i' % int(self.coins_float_value)
        self.coins_label.label = '%i coins' % int(self.coins_float_value)

    def animate_diamonds_tick(self) -> None:              # animateDiamonds 0x10001cb68
        self.diamonds_float_value = f32(self.diamonds_step + self.diamonds_float_value)
        if not abs(f32(self.diamonds_float_value - f32(self.diamonds_wanted_value))) > abs(self.diamonds_step):
            self.diamonds_float_value = f32(self.diamonds_wanted_value)
            if self.animation_timer_for_diamonds is not None:
                self.animation_timer_for_diamonds.invalidate()
        self.diamonds_label.text = '%i' % int(self.diamonds_float_value)
        self.diamonds_label.label = '%i diamonds' % int(self.diamonds_float_value)

    def stop_all_animations(self) -> None:                # 0x10001cc9c
        for t in (self.animation_timer_for_coins, self.animation_timer_for_diamonds):
            if t is not None:
                t.invalidate()

    # --- buttons ---------------------------------------------------------------------------------
    def armory_button_pressed(self) -> None:              # armoryButtonPressed: 0x10001cce8
        from ..app import App
        App.delegate().go_to_armory(self.delegate, self.armory_loadout_enabled)

    def deactivate_buttons(self) -> None:                 # 0x10001cee4
        # DIVERGENCE: the original fades both buttons out (alpha 0) while a screen animates in - on the
        # tarot screen, the 2.3 s the cards take to be dealt - which takes them out of the reading order for
        # those seconds, long enough to arrow past where the Armory button is about to appear.  The port
        # leaves them readable and dims them instead: the lock-out stays, but it is heard as "dimmed"
        # rather than as a button that does not exist yet.
        self.back_button.alpha = 1.0
        self.armory_button.alpha = 1.0
        self.back_button.enabled = False
        self.armory_button.enabled = False
        self.back_button.user_interaction_enabled = False
        self.armory_button.user_interaction_enabled = False

    def activate_buttons(self) -> None:                   # 0x10001d018: 0.5 s fade in, then interaction
        self.back_button.alpha = 1.0
        self.armory_button.alpha = 1.0

        def completion():                                 # activateButtons_block_invoke_2
            self.back_button.enabled = True
            self.armory_button.enabled = True
            self.back_button.user_interaction_enabled = True
            self.armory_button.user_interaction_enabled = True
        RunLoop.main().call_later(0.5, completion)

    # DIVERGENCE (user request): what the coins and the diamonds are shown on is decided by where the
    # player is, not by the screen asking.  In the original each screen says (setCurrenciesVisibility:
    # 0x10001d4b0, setDiamonsdsVisibility: 0x10001d5c8 in its viewDidLoad), and what came out of that is
    # neither here nor there: Settings shows them, the Play menu does not, the challenge list does, the
    # screen after a challenge does not.  They belong to Play: the menus under it are where coins and
    # diamonds are earned and spent, and everywhere else they are two more things to walk past.  So they
    # are shown from the Play menu until the player is back at the main menu (`App.in_play`), which also
    # means a play mode added later has them without being told to, and hidden anywhere else.  A screen
    # can still keep them off while the player is inside Play by saying `shows_currencies = False`; the
    # pause screen does, being a fight rather than a menu.
    def _wanted(self) -> bool:
        from ..app import App
        return bool(App.delegate().in_play) and getattr(self.screen, 'shows_currencies', True)

    def set_currencies_visibility(self, visible: bool) -> None:     # 0x10001d4b0
        self.currencies_view.hidden = not self._wanted()

    def set_armory_button_visibility(self, visible: bool) -> None:  # setArmoryButtonVisibilty: 0x10001d514
        self.armory_button.hidden = not visible
        self.armory_button.user_interaction_enabled = bool(visible)

    def set_diamonds_visibility(self, visible: bool) -> None:       # setDiamonsdsVisibility: 0x10001d5c8
        self.diamonds_label.hidden = not self._wanted()


class NoBarScreen(AccessibleScreen):
    """ADNoBarViewController."""

    def __init__(self, host):
        super().__init__(host)
        self.status_bar_view_controller: StatusBar | None = None
        self.mission_topbar_view_controller = None

    def view_will_appear(self) -> None:
        # the status bar controller's view is a subview of this screen: it appears with it
        if self.status_bar_view_controller is not None:
            self.status_bar_view_controller.view_will_appear()

    def view_did_appear(self) -> None:
        if self.status_bar_view_controller is not None:
            self.status_bar_view_controller.view_did_appear()

    def load_status_bar(self) -> None:                    # 0x100018f50
        from ..app import App
        sb = StatusBar()
        sb.screen = self
        self.status_bar_view_controller = sb
        view = getattr(self, 'view', None)
        if view is not None:                              # [[self view] addSubview:] at origin 0,0
            sb.view.parent = view
            view.children.append(sb.view)
        else:
            self.roots.append(sb.view)
        sb.set_currencies_visibility(True)                # whatever the screen goes on to ask for, the
        sb.set_diamonds_visibility(True)                  # rule decides: a screen that never asks is right
        sb.back_button.add_target(self.back_button_pressed)
        sb.delegate = self
        App.delegate().status_bar = sb
        # the ADArmoryViewController "Close armory" label is set when self is the armory

    def show_no_diamonds_alert(self) -> None:             # 0x100019990
        self.host.show_no_diamonds_alert()

    def dealloc(self) -> None:                            # 0x100019478
        sb = self.status_bar_view_controller
        if sb is not None:
            if sb.view in self.roots:
                self.roots.remove(sb.view)
            if sb.view.parent is not None and sb.view in sb.view.parent.children:
                sb.view.parent.children.remove(sb.view)
            sb.delegate = None
        self.status_bar_view_controller = None


class ViewControllerScreen(NoBarScreen):
    """ADViewController."""

    has_escape = True

    def __init__(self, host):
        super().__init__(host)
        self.first_accessible_element: View | None = None     # IBOutlet firstAccessibleElement
        self.background = None

    def view_did_load(self) -> None:                      # 0x100072248
        # [self addParticles] (iOS 7+, background set) returns at once while VoiceOver runs; it is visual
        self.load_status_bar()
        if self.first_accessible_element is not None:
            self.post_screen_changed(self.first_accessible_element)
