"""Accessible_ADGameOverEndlessViewController: the Endless game over screen used while VoiceOver runs.

Class chain: Accessible_ADGameOverEndlessViewController : ADGameOverEndlessViewController :
ADGameOverWithStatsViewController : ADViewController.

QUIRK: -[Accessible_ADGameOverEndlessViewController viewDidLoad] (0x100099f50) does not call
[super viewDidLoad].  ADGameOverEndlessViewController's viewDidLoad (0x1000d306c), which starts the
"game_over_theme" menu music, and ADViewController's (status bar, first element) never run for VoiceOver
users: this screen is silent, and the status bar is loaded by the accessible viewDidLoad itself.
"""
from __future__ import annotations

import logging

from .. import localization
from ..app import App
from ..platform.defaults import UserDefaults
from ..s3d.engine import S3DEngine
from . import results
from .accessibility import Button, View
from .host import register
from .viewcontroller import ViewControllerScreen

log = logging.getLogger('ui.gameover')


def time_string_from_seconds(seconds: int) -> str:     # timeStringFromSeconds: 0x10009be74
    minutes = int(seconds / 60)                         # C division truncates toward zero
    rest = seconds - minutes * 60
    return '%i:%s' % (minutes, '%s%i' % ('0' if rest < 10 else '', rest))


def compute_current_enemy_kill_count(stats) -> int:     # -[ADInGameStats computeCurrentEnemyKillCount] 0x1000bab3c
    from ..platform.defaults import ns_int_value
    if not stats.enemy_list:
        return 0
    total = 0
    for entry in stats.enemy_list.values():
        value = entry.get('Killed') if isinstance(entry, dict) else None
        total += ns_int_value(value) if value is not None else 0
    return total


def tarot_row(cards):
    """PORT ADDITION: the run's cards as one line - ('Tarot cards', 'More Power Ups!, Glue Barrels and
    Black Cat') - or ('Tarot card', title) for one, or None when the run had none."""
    titles = [title for _level, title in cards]
    if not titles:
        return None
    label = 'Tarot card' if len(titles) == 1 else 'Tarot cards'
    listed = ' and '.join([', '.join(titles[:-1]), titles[-1]] if len(titles) > 2 else titles)
    return localization.translate(label), listed        # PORT ADDITION: chosen language


@register('Accessible_ADGameOverEndlessViewController')
class AccessibleGameOverEndlessScreen(ViewControllerScreen):
    page_title = 'Game over'

    def __init__(self, host):                            # initWithNibName:bundle: 0x100099c68
        super().__init__(host)
        self.completed_missions: list = []
        self.init_missions()

    def init_missions(self) -> None:                     # 0x100099d80: empty
        pass

    def load_view(self) -> None:                         # 0x100099d84: nib Accessible_ADGameOverEndlessViewController (#16)
        v = self.view = View('', (0, 0, 480, 320), accessible=False, name='#16')
        self.table_view = View('', (0, 31, 480, 251), accessible=False, parent=v, ordered=True, name='#39 UITableView')
        # REMOVED (user request): the "Share on twitter" button #22 (AccessibleTwitterButtonPressed: 0x10009c0cc)
        # PORT ADDITION: what the removed Twitter button was for, in a form that does not need an account
        # and works with whatever the player shares things in.  It is read straight after the results it
        # copies, before the button that leaves the screen (user request).
        copy = Button(results.COPY_LABEL, (265, 290, 133, 30), parent=v, font_button=False,
                      actions=[self.copy_results_button_pressed], name='Copy results (port)')
        copy.hint = results.COPY_HINT
        # DIVERGENCE (user request): the nib's button #47 is titled PLAY AGAIN.  It is called Close here and
        # read after Copy results, one row lower; it does what it always did (playAgainButtonPressed:
        # 0x10009bf54) - leave for the Endless screen, where the cards are dealt - and the hint says so.
        close = Button('Close', (265, 320, 133, 30), parent=v, font_button=False,
                       actions=[self.play_again_button_pressed], name='#47')
        close.hint = 'Press Enter to go back to the Endless screen, where you can play again.'
        self.roots = [v]

    def view_did_load(self) -> None:                     # 0x100099f50 (no [super viewDidLoad])
        from ..game.ingame_stats import InGameStats
        from ..game.inventory import Inventory
        from ..game.persistent_stats import PersistentStats
        # [[statusBarViewController pageTitle] setText:@"GAME OVER"] goes to nil
        PersistentStats.shared().save_score(InGameStats.singleton().game_score)
        # PORT ADDITION: which cards this run had, for the first row - asked now, because the line below
        # clears them after any run longer than a minute
        from .tarot import cards_in_play
        self.cards_played = cards_in_play()
        self.reset_cards_modifiers_if_needed()
        # REMOVED (user request): [self reportScoreToGameCenter] (0x1000d46f4); Windows has no Game Center
        if self.status_bar_view_controller is None:
            self.load_status_bar()
        self.status_bar_view_controller.set_armory_button_visibility(True)
        self.status_bar_view_controller.armory_loadout_enabled = True
        inv = Inventory.shared()
        inv.set_coins(inv.coins + InGameStats.singleton().total_coins)
        inv.set_diamonds(inv.diamonds + InGameStats.singleton().diamond_loot)
        # QUIRK KEPT: the missing [super viewDidLoad] also skips startMenuMusic:@"game_over_theme"
        # (0x1000d37cc), so this screen is silent - which is what it should be: it is the score you just
        # lost, not a menu.  The theme starts again on the card screen (Close) or the main menu.

    def view_will_appear(self) -> None:                  # 0x10009c020
        super().view_will_appear()                       # ADGameOverEndlessViewController 0x1000d424c: positionView
        self.init_missions()
        self.reload_data()

    # --- ADGameOverEndlessViewController ---------------------------------------------------------
    @staticmethod
    def reset_cards_modifiers_if_needed() -> None:       # 0x1000d42a8
        from ..game.ingame_stats import InGameStats
        if not InGameStats.singleton().time_elapsed > 60.0:
            return
        defaults = UserDefaults.standard()
        for i in range(1, 4):
            defaults.set_object(None, 'tarotCard%i' % i)
        defaults.synchronize()

    def dealloc(self) -> None:                           # ADGameOverEndlessViewController dealloc 0x1000d4e18
        pl = S3DEngine.engine().play_list_with_name('revive')
        if pl is not None:
            pl.deactivate()
        super().dealloc()

    # --- table (UITableViewDataSource) -----------------------------------------------------------
    def reload_data(self) -> None:                       # [tableView reloadData]
        """DIVERGENCE (user request): one row per line, read exactly as Copy results pastes it.

        The original's table (numberOfSectionsInTableView: 0x10009a89c, tableView:numberOfRowsInSection:
        0x10009a674) has two sections under the headers "Rewards" and "Statistics"
        (tableView:viewForHeaderInSection: 0x10009a690), and its rewards are sentences - "Coins, You earned
        87 coins for killing zombies" (cellForRewardsAtIndex: 0x10009aa80).  Here there are no header rows,
        each value is one line - "Coins Earned: 87", "Score: 1200" - and the run's tarot cards come first,
        which the original never shows at all.  Copy results reads this same table, so the screen and the
        paste say the same lines; only the paste's heading is not on the screen, which has its title."""
        from ..game.ingame_stats import InGameStats
        stats = InGameStats.singleton()
        t = self.table_view
        t.children.clear()
        for n, (text, detail) in enumerate(self.result_rows(stats)):
            cell = View(results.line(text, detail), t.frame, parent=t, name='row %i' % n)
            results.mark_cell(cell, text, detail)

    def result_rows(self, stats) -> list:
        """(text, value) for each line: the tarot cards, the two rewards, the five statistics."""
        rows = []
        cards = tarot_row(getattr(self, 'cards_played', []))
        if cards is not None:
            rows.append(cards)
        rows += [self.copy_for_rewards_at_index(row, stats) for row in range(2)]
        rows += [self.cell_for_stats_at_index(row, stats) for row in range(5)]
        return rows

    @staticmethod
    def cell_for_rewards_at_index(row: int, stats):      # cellForRewardsAtIndex: 0x10009aa80
        """The original's sentences.  The Endless screen no longer reads them (see reload_data); the
        challenge completed screen, which inherits this, still does."""
        if row == 0:
            return 'Coins', 'You earned %i coins for killing zombies' % stats.total_coins
        if row == 1:
            return 'Diamonds', 'You earned %i diamonds' % stats.diamond_loot
        return '', ''

    @staticmethod
    def copy_for_rewards_at_index(row: int, stats):      # PORT ADDITION: a reward as one line
        if row == 0:
            return 'Coins Earned', '%i' % stats.total_coins
        if row == 1:
            return 'Diamonds Earned', '%i' % stats.diamond_loot
        return '', ''

    @staticmethod
    def cell_for_stats_at_index(row: int, stats):        # cellForStatsAtIndex: 0x10009b7cc
        if row == 0:
            return 'Score', '%i' % stats.game_score
        if row == 1:
            return 'Kills', '%i' % compute_current_enemy_kill_count(stats)
        if row == 2:
            return 'Accuracy', '%.2f %%' % (stats.current_accuracy() * 100)
        if row == 3:
            return 'Survival time', time_string_from_seconds(int(stats.time_elapsed))
        if row == 4:
            return 'Maximum combo', '%i' % stats.highest_combo
        return '', ''

    # --- actions ---------------------------------------------------------------------------------
    def back_button_pressed(self) -> None:               # 0x10009a330
        App.delegate().go_to_main_menu()

    @staticmethod
    def play_again_button_pressed() -> None:             # playAgainButtonPressed: 0x10009bf54
        App.delegate().go_to_tarot()

    def copy_results_button_pressed(self) -> None:       # PORT ADDITION: the table, cards and all
        results.copy_results(self, 'Audio Defence Endless Statistics')

    # REMOVED (user request): the magic tap 0x10009bff8 pressed Play again (the Close button here).
