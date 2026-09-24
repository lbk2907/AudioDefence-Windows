"""The armory, as it is with VoiceOver running: Accessible_ADArmoryViewController and its four tabs.

    Accessible_ADArmoryViewController : ADArmoryViewController : ADViewWithWeaponDetailViewController
        weapons  -> ADArmoryShopViewController            (+ Accessible_ADWeaponDescriptionViewController)
        loadout  -> Accessible_ADArmoryLoadoutViewController (+ Accessible_ADWeaponDescriptionViewController)
        powerup  -> ADArmoryPowerUpViewController         (+ ADArmoryPowerUpUpgraderViewController)
        currency -> ADArmoryCurrencyViewController

The tab controllers' views are all children of the armory's content scroll view; only the selected one is
accessible (-toggleAccessibilityAfterTabWasSelected: 0x100076680 sets accessibilityElementsHidden on the
others), so the port puts them all at the page the scroll view shows.

The currency tab's table asks its `products` array for its row count, and nothing in the binary ever sets
`products` (only -[GAIDictionaryBuilder products] shares the name): the tab is an empty table in the
shipped game, so no in-app purchase is involved and none is ported.
"""
from __future__ import annotations

import logging

from ..app import App
from ..game import data
from ..game.inventory import Inventory
from ..game.weapon_manager import WeaponManager
from ..platform.defaults import ns_float_value, ns_int_value
from ..platform.runloop import RunLoop
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from .accessibility import (Button, View, _is_inside, cross_axis_key, cross_axis_text, menu_tick,
                            play_button_click)
from .challenges import _TableLoader
from .host import AlertScreen, register
from .viewcontroller import ViewControllerScreen

log = logging.getLogger('ui.armory')

WEAPON_UPGRADE_EVENT = 'WEAPON_UPGRADE_EVENT'
POWERUP_UPGRADE_EVENT = 'POWERUP_UPGRADE_EVENT'
PAGE = (0.0, 53.5, 480.0, 234.0)        # a tab's view, centred on the content scroll view's visible page


def _play_click() -> None:
    """-[ADArmoryShopViewController playSound] 0x100090958 (the power-up tab's is the same code)."""
    pl = S3DEngine.engine().play_list_with_name('buttons')
    sound = pl.sound('click_button') if pl is not None else None
    if sound is not None:
        sound.set_gain(3.0)
        sound.play()


def _offset(frame, dx: float, dy: float):
    return (frame[0] + dx, frame[1] + dy, frame[2], frame[3])


# ============================================================================== weapon description view
class WeaponDescriptionView:
    """Accessible_ADWeaponDescriptionViewController (nib view #28), added over the tab's table."""

    def __init__(self, weapon_dictionary, hide_buttons: bool, armory, parent_table: View, parent: View):
        # initWithWeaponDictionary: 0x10006f000
        self.weapon_inventory_dict = weapon_dictionary or {}
        self.weapon_stats_dict = WeaponManager.shared().dictionary_for_weapon_with_name(
            self.weapon_inventory_dict.get('name')) or {}
        self.hide_buttons = hide_buttons
        self.armory = armory
        self.parent_table = parent_table
        self.current_level = 0
        self.current_level_dict = {}
        self.next_level_dict = None
        self.load_view(parent)
        self.view_did_load()

    def load_view(self, parent: View) -> None:
        v = self.view = View('', PAGE, accessible=False, parent=parent, name='#28')
        dx, dy = PAGE[0], PAGE[1]
        # DIVERGENCE (user request): these three are plain UIButtons in the nib (#23, #7, #26), and only
        # ADButtonWithFont plays a sound (playSound 0x100073578), so closing the page and equipping a weapon
        # were the two things in the armory that made none.  They click like everything else now.
        Button('Close weapon description', _offset((0, 0, 203, 47), dx, dy), parent=v, font_button=False,
               actions=[self.back_button_pressed, play_button_click], name='#23')
        self.weapon_name = View('', _offset((205, 0, 275, 47), dx, dy), parent=v, name='#65')
        self.weapon_description = View('', _offset((8, 55, 464, 47), dx, dy), parent=v, name='#78')
        self.weapon_stats = View('', _offset((8, 110, 464, 47), dx, dy), parent=v, name='#37')
        self.buy_or_upgrade_button = Button('Buy or upgrade', _offset((8, 186, 151, 42), dx, dy), parent=v,
                                            actions=[self.buy_or_upgrade_button_pressed], name='#54')
        self.equip1_button = Button('Equip instead of ', _offset((174, 186, 154, 42), dx, dy), parent=v,
                                    font_button=False, name='#7',
                                    actions=[self.equip_slot1_button_pressed, play_button_click])
        self.equip2_button = Button('Equip instead of ', _offset((336, 186, 136, 42), dx, dy), parent=v,
                                    font_button=False, name='#26',
                                    actions=[self.equip_slot2_button_pressed, play_button_click])
        self.equip3_button = View('', (0, 0, 0, 0), accessible=False, name='equip3Button (not connected)')
        self.view.modal = True                            # setAccessibilityViewIsModal:1 by the tab
        self.parent_table.elements_hidden = True          # [tableView setAccessibilityElementsHidden:YES]

    def view_did_load(self) -> None:                      # 0x10006f180
        self.load_informations()

    # --- content ---------------------------------------------------------------------------------
    def load_informations(self) -> None:                  # 0x10006f1dc
        inv = Inventory.shared()
        wm = WeaponManager.shared()
        name = self.weapon_inventory_dict.get('name')
        self.current_level = inv.level_for_weapon(name)
        self.current_level_dict = self.weapon_stats_dict.get('level_%i' % self.current_level) or {}
        self.next_level_dict = self.weapon_stats_dict.get('level_%i' % (self.current_level + 1))
        text = wm.display_name_for_item_with_name(name)
        if inv.has_unlocked_weapon(name):
            text = '%s : level %i' % (text, self.current_level)
            if inv.is_weapon_equipped(name):
                text = '%s : equipped' % text
        else:
            text = '%s : locked' % text
        self.weapon_name.label = self.weapon_name.text = text
        d = self.current_level_dict
        stats = 'Damages : %.1f, Capacity : %i, Spread : %i' % (
            ns_float_value(d.get('damages')), ns_int_value(d.get('capacity')), ns_int_value(d.get('spread')))
        self.weapon_stats.label = self.weapon_stats.text = stats
        description = self.weapon_stats_dict.get('description') or ''
        self.weapon_description.label = self.weapon_description.text = description
        self.check_buy_or_upgrade_button()
        self.check_equip_buttons()

    def check_buy_or_upgrade_button(self) -> None:        # 0x10006fa68
        b = self.buy_or_upgrade_button
        name = self.weapon_inventory_dict.get('name')
        if Inventory.shared().has_unlocked_weapon(name):
            if self.next_level_dict is None:
                b.hidden = True                           # the max level: no title change
                return
            cost = ns_int_value(self.next_level_dict.get('upgradeCost'))
            if cost != 0:
                _set_title(b, 'Upgrade to level %i for %i coins' % (self.current_level + 1, cost))
                return
            diamonds = ns_int_value(self.next_level_dict.get('upgradeCostInDiamonds'))
            if diamonds != 0:
                _set_title(b, 'Upgrade to level %i for %i diamonds' % (self.current_level + 1, diamonds))
            return
        price = ns_int_value(self.weapon_stats_dict.get('price'))
        if price >= 1:
            _set_title(b, 'Buy for %i coins' % price)
        else:
            _set_title(b, 'Buy for %i diamonds' % ns_int_value(self.weapon_stats_dict.get('priceInDiamonds')))

    def check_equip_buttons(self) -> None:                # 0x10006ff8c
        inv = Inventory.shared()
        wm = WeaponManager.shared()
        name = self.weapon_inventory_dict.get('name')
        if self.hide_buttons or inv.is_weapon_equipped(name) or not inv.has_unlocked_weapon(name):
            self.equip1_button.hidden = True
            self.equip2_button.hidden = True
            self.equip3_button.hidden = True
            return
        if wm.is_melee_for_weapon_with_name(name):
            # QUIRK: equip1Button keeps whatever hidden state it had (the nib's: visible)
            _set_title(self.equip1_button,
                       'equip instead of %s' % wm.display_name_for_item_with_name(inv.weapon_slot_melee))
            self.equip2_button.hidden = True
            self.equip3_button.hidden = True
            return
        _set_title(self.equip1_button,
                   'equip instead of %s' % wm.display_name_for_item_with_name(inv.weapon_slot1))
        _set_title(self.equip2_button,
                   'equip instead of %s' % wm.display_name_for_item_with_name(inv.weapon_slot2))
        self.equip1_button.hidden = False
        self.equip2_button.hidden = False
        self.equip3_button.hidden = True

    # --- actions ---------------------------------------------------------------------------------
    def back_button_pressed(self) -> None:                # 0x1000707b4
        self.parent_table.elements_hidden = False
        if self.view.parent is not None and self.view in self.view.parent.children:
            self.view.parent.children.remove(self.view)
        self.armory.detail_closed(self)

    def buy_or_upgrade_button_pressed(self) -> None:      # 0x10007085c
        from ..game.missions import MissionManager
        inv = Inventory.shared()
        name = self.weapon_inventory_dict.get('name')
        nxt = self.next_level_dict or {}
        if inv.has_unlocked_weapon(name):
            cost = ns_int_value(nxt.get('upgradeCost'))
            if cost != 0:
                if inv.coins < cost:
                    self.armory.show_not_enough_money_alert()
                    return                                # no -loadInformations on this path
                inv.set_level_for_weapon(self.current_level + 1, name)
                MissionManager.shared().upgrade_weapon_to_level(self.current_level + 1)
                inv.set_coins(inv.coins - cost)
            else:
                diamonds = ns_int_value(nxt.get('upgradeCostInDiamonds'))
                if diamonds != 0 and inv.diamonds >= diamonds:
                    inv.set_level_for_weapon(self.current_level + 1, name)
                    MissionManager.shared().upgrade_weapon_to_level(self.current_level + 1)
                    inv.set_diamonds(inv.diamonds - diamonds)
                elif self.next_level_dict is not None:
                    self.armory.show_no_diamonds_alert()
                # DIVERGENCE: with no next level there is no cost to compare, so both branches read 0 and
                # the weapon at its maximum level answered "Not enough Diamonds!".  checkBuyOrUpgradeButton
                # 0x10006fa68 hides the button by then, which is why it is hard to reach - but the alert was
                # wrong wherever it appeared.  A weapon that cannot be upgraded now says nothing.
        else:
            price = ns_int_value(self.weapon_stats_dict.get('price'))
            if price >= 1:
                if inv.coins < price:
                    self.armory.show_not_enough_money_alert()
                    return
                inv.unlock_weapon(name)
                inv.set_coins(inv.coins - price)
            else:
                diamonds = ns_int_value(self.weapon_stats_dict.get('priceInDiamonds'))
                if diamonds != 0:
                    if inv.diamonds >= diamonds:
                        inv.unlock_weapon(name)
                        inv.set_diamonds(inv.diamonds - diamonds)
                    else:
                        self.armory.show_no_diamonds_alert()
        self.load_informations()
        sb = self.armory.status_bar_view_controller
        if sb is not None:
            sb.refresh_coins_and_diamonds()
        self.armory.post_screen_changed(self.weapon_stats)
        # (the accessible description does not post WEAPON_UPGRADE_EVENT; only the sighted one does)

    def equip_slot1_button_pressed(self) -> None:         # 0x100071058
        inv = Inventory.shared()
        name = self.weapon_inventory_dict.get('name')
        if WeaponManager.shared().is_melee_for_weapon_with_name(name):
            inv.set_weapon_slot_melee(name)
        else:
            inv.set_weapon_slot1(name)
        self.back_button_pressed()

    def equip_slot2_button_pressed(self) -> None:         # 0x100071228
        Inventory.shared().set_weapon_slot2(self.weapon_inventory_dict.get('name'))
        self.back_button_pressed()


def _set_title(button: View, title: str) -> None:
    """setTitle:forState:0 on a button without an accessibility label: VoiceOver reads the title."""
    button.set_title(title)
    button.label = title


# ================================================================================ power-up upgrader view
class PowerUpUpgraderView:
    """ADArmoryPowerUpUpgraderViewController (nib tag-2781 view #69), added over the whole armory."""

    def __init__(self, power_up_dictionary, armory, alert_view_delegate):
        self.power_up_dictionary = power_up_dictionary or {}   # initWithPowerupDictionary: 0x10004d738
        self.armory = armory
        self.alert_view_delegate = alert_view_delegate
        self.load_view(armory.view)
        self.view_did_load()

    def load_view(self, parent: View) -> None:            # 0x10004d89c
        v = self.view = View('', (0, 0, 568, 320), accessible=False, parent=parent, name='#69')
        # DIVERGENCE (user request): the nib's button for this page is "Back" (`voiceOverBack`, given its
        # action in viewDidLoad 0x10004d848), where the weapon page's says what it closes - "Close weapon
        # description".  A page you reach from a list wants the same words for the way out of it.
        # and it sits below the status bar, where the weapon page's does (its nib frames are offset by the
        # page's origin), so both pages read the same way round: the bar first, then the way out, then the
        # page itself.  In the nib this button is at the very top, level with the bar
        self.voice_over_back = Button('Close powerup description', (0, 53.5, 150, 40), parent=v,
                                      actions=[self.back_button_pressed], name='#103')
        self.power_up_title = View('', (95, 70, 380, 40), parent=v, name='#124')
        self.power_up_description = View('', (221, 120, 245, 129), parent=v, name='#9 UITextView')
        self.upgrade_button = Button('UPDATE', (100, 257, 194, 38), parent=v,
                                     actions=[self.upgrade_button_pressed], name='#46')
        self.badge_image = None                           # no badgeImage outlet in the iPhone nib
        # DIVERGENCE (user request): the original adds this page to the armory's own view and makes it
        # modal (addSubview: 0x10003b68c, setAccessibilityViewIsModal:1 0x10003b6d8), and a modal view hides
        # every one of its siblings - the status bar among them.  So the one page in the game where you
        # decide what to spend coins on was the one page that would not tell you how many you have, while
        # the weapon page, which is added to its tab's view instead, keeps them.  This page hides the
        # tab underneath it instead of being modal, which leaves the status bar where it is.
        self.armory.content_container.elements_hidden = True

    def view_did_load(self) -> None:                      # 0x10004d7a8
        self.load_information()
        # with VoiceOver the back button gets its action; without it, it is hidden

    def load_information(self) -> None:                   # 0x10004da74
        inv = Inventory.shared()
        d = self.power_up_dictionary
        level = inv.level_for_power_up(d.get('name'))
        # DIVERGENCE (user request): the title says which level the power-up is on, as the weapon page's
        # does ("Fire grenade : level 2").  The original's is the name alone (0x10004da74) and nothing else
        # on the page says what you already have, so the price stood on its own.
        _set_text(self.power_up_title, '%s : level %i' % (d.get('displayName') or '', level))
        _set_text(self.power_up_description, d.get('upgradeText') or '')
        b = self.upgrade_button
        if level >= 4:
            b.user_interaction_enabled = False
            _set_title(b, 'No Upgrade')
            return
        cost = ns_int_value((d.get('level_%i' % (level + 1)) or {}).get('upgradeCost'))
        # DIVERGENCE: the original's title is "Upgrade for %i" and the currency is a coin image drawn next
        # to it (setCoins: / centerButtonTextWithCoinsImage), which VoiceOver cannot read.  The button keeps
        # the original's text; what is spoken says what the number is.
        b.set_title('Upgrade for %i' % cost)
        b.label = 'Upgrade for %i coins' % cost

    def upgrade_button_pressed(self) -> None:             # 0x10004e1b4
        inv = Inventory.shared()
        d = self.power_up_dictionary
        name = d.get('name')
        level = inv.level_for_power_up(name)
        if level > 3:
            return
        cost = ns_int_value((d.get('level_%i' % (level + 1)) or {}).get('upgradeCost'))
        if inv.coins < cost:
            self.armory.show_not_enough_money_alert(delegate=self.alert_view_delegate)
            return
        inv.set_level_for_power_up(level + 1, name)
        sb = App.delegate().status_bar
        if sb is not None:
            sb.animate_coins(-cost)
        inv.set_coins(inv.coins - cost)
        RunLoop.main().post(POWERUP_UPGRADE_EVENT, self, {'name': name})
        Tracker.shared().record_weapon_upgrade(name, float(cost))
        self.show_next_level()
        # DIVERGENCE: the original waits a second before loadInformation (the dispatch_after before
        # 0x10004ea84), because that second is its badge animation.  The button's words are the next
        # level's price, so for that second it offers a price that is no longer the one you would pay -
        # and a screen reader that lands back on the button inside it reads the old number as fact.  The
        # words are refreshed at once; the delayed call stays, so the animation still ends as it did.
        self.load_information()
        RunLoop.main().call_later(1.0, self.load_information)   # dispatch_after 1 s

    def show_next_level(self) -> None:                    # 0x10004ea98 (badge image transition)
        self.upgrade_button.user_interaction_enabled = False

        def done():                                       # showNextLevel_block_invoke_2
            self.upgrade_button.user_interaction_enabled = True
        RunLoop.main().call_later(0.5, done)

    def back_button_pressed(self) -> None:                # 0x10004ee38
        self.remove()

    def remove(self) -> None:
        if self.view.parent is not None and self.view in self.view.parent.children:
            self.view.parent.children.remove(self.view)
        self.armory.content_container.elements_hidden = False   # the tab underneath can be read again
        self.armory.detail_closed(self)


def _set_text(label: View, text: str) -> None:
    label.label = label.text = text


# ============================================================================================== tabs
class _Tab:
    """A tab controller's view inside the armory's content scroll view."""

    view_name = ''

    def __init__(self, armory):
        self.armory = armory
        self.view = View('', PAGE, accessible=False, parent=armory.content_container, name=self.view_name)
        self.detail_view = None
        self.build()

    def build(self) -> None:
        pass

    def reload_data(self) -> None:
        pass

    def dealloc(self) -> None:
        pass


class ShopTab(_Tab):
    """ADArmoryShopViewController (tag-2781 view #19, table #5).  Cells are ADCustomTableViewCellWithSubtitles:
    VoiceOver reads the title label then the detail label."""

    view_name = '#19 ADArmoryShopViewController'

    def build(self) -> None:                              # viewDidLoad 0x10008ea00
        self.table_view = View('', PAGE, accessible=False, parent=self.view, ordered=True, name='#5')
        RunLoop.main().add_observer(self, WEAPON_UPGRADE_EVENT, lambda *_: self.reload_data())

    def dealloc(self) -> None:
        RunLoop.main().remove_observer(self)

    def reload_data(self) -> None:                        # viewWillLayoutSubviews 0x100090f64
        inv = Inventory.shared()
        t = _TableLoader(self.table_view)
        for row, weapon in enumerate(WeaponManager.shared().get_all_weapons_array()):
            # tableView:cellForRowAtIndexPath: 0x10008ef90, the UIAccessibilityIsVoiceOverRunning branch
            name, display = weapon.get('name'), weapon.get('displayName')
            if inv.has_unlocked_weapon(name):
                title = '%s : owned : level %i' % (display, inv.level_for_weapon(name))
            elif weapon.get('price') is not None:
                title = '%s : buy for %i coins' % (display, ns_int_value(weapon.get('price')))
            else:
                title = '%s : buy for %i diamonds' % (display, ns_int_value(weapon.get('priceInDiamonds')))
            # the buy button is hidden and disabled while VoiceOver runs
            t.cell(title, weapon.get('description'), action=lambda r=row: self.did_select_row(r))

    def did_select_row(self, row: int) -> None:           # tableView:didSelectRowAtIndexPath: 0x100090a54
        _play_click()
        weapon = WeaponManager.shared().get_all_weapons_array()[row]
        self.show_accessible_detail_view_for_weapon_with_name(weapon.get('name'))

    def show_accessible_detail_view_for_weapon_with_name(self, name) -> None:   # 0x100090c30
        d = WeaponManager.shared().dictionary_for_weapon_with_name(name)
        self.detail_view = WeaponDescriptionView(d, True, self.armory, self.table_view, self.view)
        self.armory.detail_opened(self.detail_view)


class LoadoutTab(_Tab):
    """Accessible_ADArmoryLoadoutViewController (nib view #22, table #17).  Cells are plain
    (UITableViewCellStyleDefault): only the text label is read."""

    view_name = '#22 Accessible_ADArmoryLoadoutViewController'

    def build(self) -> None:                              # viewDidLoad 0x100049410
        self.table_view = View('', PAGE, accessible=False, parent=self.view, ordered=True, name='#17')

    @staticmethod
    def index_for(section: int, row: int) -> int:
        wm = WeaponManager.shared()
        if section == 1:                                  # melee weapons are the end of the weapons array
            return len(wm.get_all_weapons_array()) + row - len(wm.get_all_melee_weapons())
        return row

    @staticmethod
    def weapon_name(index: int):                          # weaponName: 0x100049a8c
        weapons = WeaponManager.shared().get_all_weapons_array()
        if 0 <= index < len(weapons):
            return weapons[index].get('displayName')
        return None

    @staticmethod
    def weapon_status(index: int):                        # weaponStatus: 0x100049c1c
        inv = Inventory.shared()
        weapon = WeaponManager.shared().get_all_weapons_array()[index]
        name = weapon.get('name')
        if not inv.has_unlocked_weapon(name):
            # DIVERGENCE: weaponStatus: 0x100049c1c always formats @"price" as "Locked, costs : %i coins",
            # so the Sonic Cannon - which has no price key, only priceInDiamonds - is announced as
            # "costs : 0 coins" while its own detail view says "Buy for 100 diamonds".  The split here is
            # the one checkBuyOrUpgradeButton 0x10006fa68 uses: a price of 0 means the diamond price.
            price = ns_int_value(weapon.get('price'))
            if price >= 1:
                return 'Locked, costs : %i coins' % price
            return 'Locked, costs : %i diamonds' % ns_int_value(weapon.get('priceInDiamonds'))
        if inv.is_weapon_equipped(name):
            return 'equipped'
        return None                                       # the cell then shows the name alone

    def reload_data(self) -> None:                        # viewWillLayoutSubviews 0x10004a6e8
        wm = WeaponManager.shared()
        melee = len(wm.get_all_melee_weapons())
        rows = {0: len(wm.get_all_weapons_array()) - melee, 1: melee}
        t = _TableLoader(self.table_view)
        for section in range(2):                          # numberOfSectionsInTableView: 2
            t.header('Range weapons' if section == 0 else 'Melee weapons')
            for row in range(rows[section]):
                index = self.index_for(section, row)
                status = self.weapon_status(index)
                name = self.weapon_name(index)
                text = '%s : %s' % (name, status) if status is not None else name
                t.cell(text, action=lambda i=index: self.did_select_index(i))
        # the header of section 0 posts UIAccessibilityScreenChangedNotification with itself
        self.armory.post_screen_changed(self.table_view.children[0] if self.table_view.children else None)

    def did_select_index(self, index: int) -> None:       # tableView:didSelectRowAtIndexPath: 0x10004a264
        # DIVERGENCE (user request): opening a weapon here made no sound.  The original's own selection
        # (0x10004a264) has no [self playSound], where the shop's (0x100090a88) and the power-ups'
        # (0x10003b53c) both have one, and its sighted twin is no different - handleItemTap: 0x10000adf4
        # goes straight to openDescriptionForItemWithName:.  So the loadout was the odd one out in the
        # original, and every other way into a weapon page clicks.
        _play_click()
        weapon = WeaponManager.shared().get_all_weapons_array()[index]
        self.detail_view = WeaponDescriptionView(weapon, False, self.armory, self.table_view, self.view)
        self.armory.detail_opened(self.detail_view)


class PowerUpTab(_Tab):
    """ADArmoryPowerUpViewController (tag-2781 view #26, table #16)."""

    view_name = '#26 ADArmoryPowerUpViewController'

    def build(self) -> None:                              # viewDidLoad 0x10003a3cc
        self.table_view = View('', PAGE, accessible=False, parent=self.view, ordered=True, name='#16')
        RunLoop.main().add_observer(self, POWERUP_UPGRADE_EVENT, lambda *_: self.reload_data())

    def dealloc(self) -> None:
        RunLoop.main().remove_observer(self)

    def reload_data(self) -> None:                        # viewWillLayoutSubviews 0x10003bbe4
        inv = Inventory.shared()
        t = _TableLoader(self.table_view)
        for row, pu in enumerate(WeaponManager.shared().get_all_power_ups_array()):
            # tableView:cellForRowAtIndexPath: 0x10003a96c
            detail = pu.get('upgradeText') or ''
            # PORT INPUT: the original appends "double tap to view" / "double tap to upgrade"
            detail = '%s %s' % (detail, 'press Enter to view' if inv.level_for_power_up(pu.get('name')) >= 4
                                else 'press Enter to upgrade')
            cell = t.cell(pu.get('displayName'), detail, action=lambda r=row: self.did_select_row(r))
            cell.label_key_words = True                   # PORT ADDITION: or the controller's button

    def did_select_row(self, row: int) -> None:           # tableView:didSelectRowAtIndexPath: 0x10003b4ec
        _play_click()
        pu = WeaponManager.shared().get_all_power_ups_array()[row]
        self.detail_view = PowerUpUpgraderView(pu, self.armory, self)
        self.armory.detail_opened(self.detail_view)
        # the upgrader is added to the armory's view, and the status bar's back button now closes it
        self.armory.status_bar_view_controller.back_button_delegate = self

    def handle_back_action_from_status_bar(self) -> None:   # 0x10003a7ac
        self.remove_detail_view()

    def remove_detail_view(self) -> None:                 # 0x10003bc90 (the view tagged 99)
        if self.detail_view is not None:
            self.detail_view.remove()

    def alert_view_will_dismiss_with_button_index(self, title: str) -> None:   # 0x10003ba08
        if title != data.localized('COINS_ALERT_MORE'):
            return
        self.remove_detail_view()
        self.armory.status_bar_view_controller.back_button_delegate = None


# REMOVED (user request): ADArmoryCurrencyViewController, the armory's fourth tab.  Its table asked
# `products` for its row count and nothing in the binary ever set `products`, so the tab was blank on every
# device that ever ran the game.  What it was built to hold was four "free coins" offers - follow the game
# on Facebook, follow it on Twitter, see the studio's other games, rate it on the App Store - each opening a
# web page.  Those links are long dead and the offers were never wired up, so there is nothing to port and
# nothing to show: the tab is gone rather than kept as a dead end to step past.


# ============================================================================================ armory
@register('Accessible_ADArmoryViewController')
class ArmoryScreen(ViewControllerScreen):
    """Accessible_ADArmoryViewController (nib Accessible_ADArmoryViewController, view #81)."""
    page_title = 'Armory'

    def __init__(self, host, loadout_enabled: bool = False):
        # initWithNibName:bundle:loadoutEnabled: 0x10007e044 -> ADArmoryViewController 0x100073864
        super().__init__(host)
        self.loadout_enabled = bool(loadout_enabled)
        self.previous_tab = None
        self.browse_dt = 0
        self.item_names: list = []
        self.hide_equip_buttons_on_detail_view = True
        self.tabs: dict = {}
        self.current_tab = None
        self.detail_view = None
        self.detail_opened_from = None

    def load_view(self) -> None:
        v = self.view = View('', (0, 0, 480, 320), accessible=False, name='#81')
        # PORT INPUT: the nib label reads "Change tabs at the bottom of the screen to navigate the armory",
        # which is a phone's tab bar.  Here the tabs are on the arrows the menu navigation is not using, and
        # the line is said when the armory opens rather than kept as an element to walk past.
        self.tab_hint_label = View(cross_axis_text(), (0, 0, 480, 59), accessible=False, parent=v, name='#2')
        self.content_container = View('', (0, 60, 480, 221), accessible=False, parent=v, name='#39')
        self.weapons_button = Button('Weapons', (0, 284, 112, 36), parent=v, font_button=False,
                                     actions=[self.weapons_button_pressed], name='#38')
        self.load_out_button = Button('Loadout', (120, 284, 125, 36), parent=v, font_button=False,
                                      actions=[self.loadout_button_pressed], name='#6')
        self.power_up_button = Button('Powerup', (245, 284, 110, 36), parent=v, font_button=False,
                                      actions=[self.power_up_button_pressed], name='#76')
        self.currency_button = Button('Currency', (363, 284, 117, 36), parent=v, font_button=False,
                                      actions=[self.currency_button_pressed], name='#10')
        # DIVERGENCE: the nib's tab bar is four buttons VoiceOver reads at the end of every tab; the port
        # changes tab with the arrows instead (and names the tab it lands on), so the buttons stay as the
        # controllers' own state - selected, hints - without being read.
        for b in (self.weapons_button, self.load_out_button, self.power_up_button, self.currency_button):
            b.accessible = False
        self.roots = [v]

    def view_did_load(self) -> None:                      # ADArmoryViewController viewDidLoad 0x100073e98
        super().view_did_load()
        sb = self.status_bar_view_controller
        sb.delegate = self
        sb.armory_button.label = 'Close armory'           # -[ADNoBarViewController loadStatusBar] 0x1001929c
        sb.set_armory_button_visibility(False)
        # DIVERGENCE: the 1 ms NSTimer that counts browsing time only feeds the analytics tracker; the port
        # does not run it (-updateBrowseTimer: 0x100074980, -trackBrowsingTime 0x1000761f8)
        self.weapons_button_pressed()
        self.previous_tab = 'weaponsTab'
        inv = Inventory.shared()                          # [[ADTracker sharedInstance] trackerInventory]
        Tracker.shared().tracker_inventory.update({'slot1': inv.weapon_slot1, 'slot2': inv.weapon_slot2,
                                                   'slotMelee': inv.weapon_slot_melee})
        self.item_names = [w.get('name') for w in WeaponManager.shared().get_all_weapons_array()]
        self.hide_equip_buttons_on_detail_view = True

    def view_will_appear(self) -> None:
        super().view_will_appear()
        self.tab_hint_label.label = cross_axis_text()      # the player may have changed the menu arrows
        self.reload_current_tab()
        tab = self.current_tab.view if self.current_tab is not None else None
        name = self.TAB_TITLES.get(self._current_tab_key(), '')
        self.post_screen_changed(tab, '%s. %s' % (name, cross_axis_text()) if name else cross_axis_text())

    # --- changing tab with the other pair of arrows (PORT ADDITION) -------------------------------
    #: the tab buttons, in the order they sit along the bottom of the nib
    # REMOVED (user request): the Currency tab.  See CurrencyTab below for what it held.
    TAB_ORDER = ('weapons', 'loadout', 'powerup')
    TAB_TITLES = {'weapons': 'Weapons', 'loadout': 'Loadout', 'powerup': 'Powerup'}

    def _current_tab_key(self):
        return next((k for k, tab in self.tabs.items() if tab is self.current_tab), None)

    def key_down(self, event) -> None:
        where = cross_axis_key(event)
        if where is not None and self.detail_view is None:
            self.move_tab(where)
            return
        super().key_down(event)

    def move_tab(self, where: str) -> None:
        """'next', 'previous', 'first' or 'last', as the element keys do one axis over."""
        # Loadout is skipped when it is not enabled: pressing its button only raises the EQUIP alert
        keys = [k for k in self.TAB_ORDER if k != 'loadout' or self.loadout_enabled]
        current = next((k for k, tab in self.tabs.items() if tab is self.current_tab), keys[0])
        if current not in keys:
            return
        step = {'next': 1, 'previous': -1}.get(where)
        if step is None:
            i = 0 if where == 'first' else len(keys) - 1
        else:
            i = max(0, min(len(keys) - 1, keys.index(current) + step))  # the ends hold, as elsewhere
        menu_tick()                                       # PORT ADDITION: felt as well as heard
        buttons = {'weapons': self.weapons_button, 'loadout': self.load_out_button,
                   'powerup': self.power_up_button}
        if keys[i] != current:
            {'weapons': self.weapons_button_pressed, 'loadout': self.loadout_button_pressed,
             'powerup': self.power_up_button_pressed}[keys[i]]()
        self.focus_current_tab(buttons[keys[i]])

    def focus_current_tab(self, button: View) -> None:
        """Land inside the tab the way VoiceOver lands after a screen change, but name the tab first."""
        inside = [e for e in self.elements() if _is_inside(e, self.current_tab.view)]
        self._pending_focus = None                        # the tab's own reload posted one; this wins
        self._pending_prefix = None
        self.focus = inside[0] if inside else None
        self.speak('%s. %s' % (button.label, self.focus.spoken() if self.focus is not None else 'empty'))

    def dealloc(self) -> None:
        for tab in self.tabs.values():
            tab.dealloc()
        super().dealloc()

    # --- tabs ------------------------------------------------------------------------------------
    def _tab(self, key: str):
        tab = self.tabs.get(key)
        if tab is None:
            tab = self.tabs[key] = {'weapons': ShopTab, 'loadout': LoadoutTab,
                                    'powerup': PowerUpTab}[key](self)
        return tab

    def _select(self, key: str, button: View) -> None:
        self.update_tabs_after_button_pressed(button)
        tab = self._tab(key)
        self.current_tab = tab
        self.toggle_accessibility_after_tab_was_selected(tab.view)
        tab.reload_data()

    def reload_current_tab(self) -> None:
        if self.current_tab is not None:
            self.current_tab.reload_data()

    def weapons_button_pressed(self) -> None:             # 0x10007555c
        self.previous_tab = 'weaponsTab'
        self._select('weapons', self.weapons_button)

    def loadout_button_pressed(self) -> None:             # 0x10007571c
        if not self.loadout_enabled:
            self.host.push_overlay(AlertScreen(self.host, data.localized('EQUIP_ALERT_TITLE'),
                                               data.localized('EQUIP_ALERT_CONTENT'), [('OK', None)]))
            return
        self.previous_tab = 'loadOutTab'
        self._select('loadout', self.load_out_button)

    def power_up_button_pressed(self) -> None:            # 0x100075a68
        self.previous_tab = 'powerupTab'
        self._select('powerup', self.power_up_button)

    def currency_button_pressed(self) -> None:            # 0x100075c28
        # REMOVED (user request): the Currency tab.  Its button is left unreachable rather than deleted, so
        # the nib's four buttons still line up with the original's layout; nothing routes to it.
        pass

    def update_tabs_after_button_pressed(self, button: View) -> None:
        # -[Accessible_ADArmoryViewController updateTabsAfterButtonPressed:] 0x10007e0d8 (no [super ...]:
        # the buttons keep their enabled / selected state).  PORT INPUT: "Double tap" -> "Press Enter".
        hint = 'Press Enter to display this tab in the armory'
        self.currency_button.hint = hint
        self.load_out_button.hint = hint
        self.weapons_button.hint = hint
        self.power_up_button.hint = hint + ' '            # the original's power-up hint ends with a space
        button.hint = 'This tab is currently selected'

    def toggle_accessibility_after_tab_was_selected(self, view: View) -> None:   # 0x100076680
        for tab in self.tabs.values():
            tab.view.elements_hidden = tab.view is not view
        self.post_layout_changed()

    def post_layout_changed(self) -> None:                # UIAccessibilityLayoutChangedNotification(nil)
        pass

    # --- detail views ----------------------------------------------------------------------------
    def detail_opened(self, detail) -> None:
        self.detail_view = detail
        self.detail_opened_from = self.focus               # PORT ADDITION: the row it was opened from
        self.post_screen_changed(detail.view)             # a modal view: VoiceOver moves into it

    def detail_closed(self, detail) -> None:
        if self.detail_view is detail:
            self.detail_view = None
        self.reload_current_tab()
        # DIVERGENCE: the original posts a screen change with no element, so VoiceOver starts at the top of
        # the armory again; the rows are the same objects after a reload, so the port goes back to the one
        # the detail was opened from.
        back_to, self.detail_opened_from = self.detail_opened_from, None
        self.post_screen_changed(back_to if back_to in self.elements() else None)

    def close_detail_view(self) -> None:
        """PORT ADDITION: what the detail's own Back button does, for Escape."""
        detail = self.detail_view
        if detail is not None and hasattr(detail, 'back_button_pressed'):
            detail.back_button_pressed()

    def accessibility_perform_escape(self) -> None:
        # DIVERGENCE: -[ADArmoryViewController backButtonPressed] 0x100076080 dismisses the armory even
        # when a detail view has taken the back button, so Escape inside a weapon or a power-up threw you
        # out of the armory altogether.  Escape closes the detail first, as its own Back button does.
        if self.detail_view is not None:
            self.close_detail_view()
            return
        super().accessibility_perform_escape()

    # --- alerts ----------------------------------------------------------------------------------
    def show_not_enough_money_alert(self, delegate=None) -> None:   # 0x1000768d4
        # REMOVED (user request): the alert's second button, "More coins", opened the Currency tab, and the
        # last sentence of its text sent you to the same place - "You can also get coins in the Armory's
        # currency tab".  With the tab gone both would be pointing at nothing, so the button is dropped and
        # the text stops after the two ways of earning coins that do work.
        content = data.localized('COINS_ALERT_CONTENT').split('You can also get coins')[0].strip()
        self.host.push_overlay(AlertScreen(self.host, data.localized('COINS_ALERT_TITLE'), content,
                                           [('OK', None)]))

    def alert_view_will_dismiss_with_button_index(self, title: str) -> None:   # 0x100076b80
        return                                            # nothing routes here now
        # [self sendDetailViewToBack] only moves the non-accessible detail scroller

    # --- status bar ------------------------------------------------------------------------------
    def back_button_pressed(self) -> None:                # 0x100076080
        sb = self.status_bar_view_controller
        delegate = getattr(sb, 'back_button_delegate', None)
        had_detail = self.detail_view is not None
        if delegate is not None:
            delegate.handle_back_action_from_status_bar()
            sb.back_button_delegate = None
        # DIVERGENCE: backButtonPressed 0x100076080 lets the open detail view take the back button
        # (handleBackActionFromStatusBar at 0x076120) and then dismisses the armory anyway, in the tail
        # call at 0x0761b8 - so one press on Back closed the weapon page and threw you out of the armory
        # in the same breath, skipping the list you were browsing.  Back now does one step, like Escape
        # (accessibility_perform_escape): it closes the detail and leaves you on the row you opened it
        # from, and a second press leaves the armory.
        if had_detail:
            if self.detail_view is not None:
                self.close_detail_view()
            return
        self.host.dismiss_presented(self)
