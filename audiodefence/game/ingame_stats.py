"""ADInGameStats and the stats notification bus (NSObject(StatsNotifier), ADInGameStats(NotificationDispatcher))."""
from __future__ import annotations

import logging

from ..platform.defaults import ns_bool_value, ns_int_value, ns_float_value
from ..platform.runloop import RunLoop
from . import data
from .modifiers import GameModifiers
from .persistent_stats import PersistentStats, build_from_dictionary

log = logging.getLogger('stats')

SUBSCRIBED = ('UPDATE_WEAPON_DATA', 'UPDATE_COINS_FOR_KILL', 'TIME_ELAPSED', 'UPDATE_KILLED_ENEMY_POWERUP',
              'UPDATE_CHALLENGE_TIME_ELAPSED', 'BRICK_TIME_ELAPSED', 'UPDATE_KILLED_ENEMY_WITH_WEAPON',
              'UPDATE_MELEE_WEAPON_DATA', 'PLAYER_DIED', 'UPDATE_DIAMONDS')


def notify_stats(name: str, *args) -> None:
    """-[NSObject(StatsNotifier) notifyStatsSystemWithNotificationWithName:AndData:...] 0x1000bda04.

    The variadic list is nil-terminated, so arguments after the first None are dropped."""
    params = []
    for a in args:
        if a is None:
            break
        params.append(a)
    RunLoop.main().post(name, None, {'PARAM_ARRAY': params})


class InGameStats:
    _shared: 'InGameStats | None' = None

    @classmethod
    def singleton(cls) -> 'InGameStats':
        if cls._shared is None:
            cls._shared = InGameStats()
        return cls._shared

    def __init__(self):
        self.session_completed = False
        self.number_of_enemy_kills = 0
        self.death = False
        self.number_missions_completed = 0
        self.number_missions_skipped = 0
        self.game_mode = None
        self.shots_on_target = 0
        self.total_shots_fired = 0
        self.highest_combo = 0
        self.game_score = 0
        self._combo = 0
        self.melee_hits = 0
        self.melee_swings = 0
        self.coins_for_kill = 0
        self.diamond_loot = 0
        self.time_elapsed = 0.0
        self.challenge_time_elapsed = 0.0
        self.brick_time = 0.0
        self.num_critical_hits = 0
        self.weapon_critical_hits: dict = {}
        self.number_of_bricks_defeated = 0
        self.total_coins = 0
        self.enemy_list: dict = {}
        self.weapons_data: dict = {}
        self.post_game_data: dict = {}
        self.enemy_kills_with_powerup = 0

    # --- subscription ----------------------------------------------------------------------------
    @classmethod
    def toggle_on_off(cls, on: bool) -> None:               # +[ADInGameStats toggleOnOff:] 0x1000b7df4
        loop = RunLoop.main()
        s = cls.singleton()
        for name in SUBSCRIBED:
            loop.remove_observer(s, name)
            if on:
                loop.add_observer(s, name, s.act_upon_notification)

    # --- combo -----------------------------------------------------------------------------------
    @property
    def combo(self) -> int:
        return self._combo

    def set_combo(self, value: int) -> None:                # 0x1000ba90c
        self._combo = int(value)
        if self.highest_combo < self._combo:
            self.highest_combo = self._combo

    def decrement_combo(self) -> None:                      # 0x1000ba240
        if self._combo != 0:
            self.set_combo(self._combo - 1)

    # --- lifecycle -------------------------------------------------------------------------------
    def start_new_level(self, mode: str) -> None:           # 0x1000b83d4
        self.session_completed = False
        self.number_of_enemy_kills = 0
        self.death = False
        self.number_missions_completed = 0
        self.number_missions_skipped = 0
        self.game_mode = mode
        self.shots_on_target = 0
        self.total_shots_fired = 0
        self.highest_combo = 0
        self.game_score = 0
        self.set_combo(10)
        if GameModifiers.shared().baseComboBonus:
            self.set_combo(20)
        self.melee_hits = 0
        self.melee_swings = 0
        self.coins_for_kill = 0
        self.diamond_loot = 0
        self.time_elapsed = 0.0
        self.challenge_time_elapsed = 0.0
        self.brick_time = 0.0
        self.num_critical_hits = 0
        self.weapon_critical_hits = {}
        self.number_of_bricks_defeated = 0
        self.total_coins = 0
        self.enemy_list = data.plist('enemies')
        self.weapons_data = build_from_dictionary(data.plist_ro('Weapons'))
        InGameStats.toggle_on_off(True)

    def end_level(self) -> None:                            # 0x1000b89f0
        self.session_completed = True
        self.filter_enemies_by_display_name()
        self.filter_weapons_by_shots_fired()
        self.build_misc_post_game_data()
        if self.coins_for_kill > 0:
            self.total_coins += self.coins_for_kill
            self.total_coins += self.highest_combo
            self.total_coins = self.total_coins + int(((self.time_elapsed * self.time_elapsed) / 200.0)
                                                      * self.current_accuracy())
        if GameModifiers.shared().metalDetector:
            self.total_coins = int(float(self.total_coins) * 1.15) & 0xFFFFFFFF
        if GameModifiers.shared().lessCoins:              # PORT ADDITION: Holes in Your Pockets
            self.total_coins = int(float(self.total_coins) * 0.85) & 0xFFFFFFFF
        InGameStats.toggle_on_off(False)

    def save_stats(self) -> None:                           # 0x1000b8c0c
        ps = PersistentStats.shared()
        if self.death:
            ps.update_deaths()
        ps.save_enemy_data(self.enemy_list)
        ps.save_play_time_data(self.time_elapsed, self.game_mode)
        ps.save_shots_data(self.prepare_totals_stats())
        ps.save_weapons_data(self.weapons_data)
        if self.game_mode == 'ENDLESS':
            ps.save_endless_mode_kills(self.number_of_enemy_kills)

    def filter_enemies_by_display_name(self) -> None:       # 0x1000b8f50
        from .brick_manager import BrickManager
        out: dict = {}
        for key, entry in self.enemy_list.items():
            display = (BrickManager.dictionary_for_enemy_name(key) or {}).get('displayName')
            if display is None:
                continue
            if display in out:
                out[display]['Killed'] = ns_int_value(out[display]['Killed']) + ns_int_value(entry.get('Killed'))
                out[display]['Casualty'] = ns_int_value(out[display]['Casualty']) + ns_int_value(entry.get('Casualty'))
            else:
                out[display] = {'Killed': entry.get('Killed'), 'Casualty': entry.get('Casualty')}
        self.enemy_list = out

    def filter_weapons_by_shots_fired(self) -> None:        # 0x1000b9618
        out = {}
        for key, entry in self.weapons_data.items():
            fired = ns_int_value(entry.get('shotsFired'))
            if fired:
                self.total_shots_fired += fired
                self.shots_on_target += ns_int_value(entry.get('shotsHit'))
                out[key] = entry
        self.weapons_data = out

    def prepare_totals_stats(self) -> dict:                 # 0x1000b9a14
        return {'Shots fired': self.total_shots_fired, 'Melee swings': self.melee_swings}

    def build_misc_post_game_data(self) -> None:            # 0x1000bacfc
        # DIVERGENCE: buildMiscPostGameData 0x1000bacfc labels entry 4 "Highest combo" and then fills it
        # from numberOfEnemyKills (the load at 0x1000bb1fc), so the post-game statistics reported your kill
        # count twice and never showed the combo the game had been tracking all along.  highestCombo is
        # maintained right beside it and is what the label says.
        values = [('Enemy kill count', self.number_of_enemy_kills), ('Shots on target', self.shots_on_target),
                  ('Total shots fired', self.total_shots_fired), ('Critical hit count', self.num_critical_hits),
                  ('Highest combo', self.highest_combo), ('Melee swing count', self.melee_swings),
                  ('Melee hit count', self.melee_hits), ('Defeated brick count', self.number_of_bricks_defeated)]
        self.post_game_data = {i: {'name': n, 'value': v} for i, (n, v) in enumerate(values)}

    def force_complete_accuracy(self) -> None:              # 0x1000b7cb0
        self.total_shots_fired = 1
        self.shots_on_target = 1

    def reset_powerup_kills(self) -> None:                  # 0x1000bace8
        self.enemy_kills_with_powerup = 0

    def current_accuracy(self) -> float:                    # 0x1000baacc
        if self.total_shots_fired == 0:
            return 0.0
        return float(self.shots_on_target) / float(self.total_shots_fired)

    # --- events ----------------------------------------------------------------------------------
    def killed_enemi(self, enemy) -> None:                  # 0x1000b9b60
        entry = self.enemy_list.get(enemy.name)
        if entry is not None:
            entry['Killed'] = ns_int_value(entry.get('Killed')) + 1
        self.number_of_enemy_kills += 1
        self.set_combo(self._combo + enemy.combo_bonus)
        self.coins_for_kill += enemy.coins_reward
        if enemy.score < 2:
            add = self._combo
        else:
            add = enemy.score * self._combo
        self.game_score += add

    def death_by_enemy_with_name(self, name: str) -> None:  # 0x1000ba098
        entry = self.enemy_list.get(name)
        if entry is not None:
            entry['Casualty'] = ns_int_value(entry.get('Casualty')) + 1

    def update_melee_weapons(self, name: str, hit: bool) -> None:   # 0x1000ba2a0
        if hit:
            self.melee_hits += 1
        self.melee_swings += 1
        self.update_data_for_weapon(name, True, hit, False, False, -1.0)

    def update_data_for_weapon(self, name, fired, hit, killed, critical, seconds) -> None:  # 0x1000ba374
        entry = self.weapons_data.get(name)
        if entry is None:
            entry = {}
            self.weapons_data[name] = entry
        if fired:
            entry['shotsFired'] = ns_int_value(entry.get('shotsFired')) + 1
        if hit:
            entry['shotsHit'] = ns_int_value(entry.get('shotsHit')) + 1
        if fired and not hit:
            self.decrement_combo()
        if killed:
            entry['kills'] = ns_int_value(entry.get('kills')) + 1
        if critical:
            display = entry.get('displayName')
            self.weapon_critical_hits[display] = ns_int_value(self.weapon_critical_hits.get(display)) + 1
        if seconds > 0.0:
            entry['timeSpentWithWeapon'] = ns_float_value(entry.get('timeSpentWithWeapon')) + seconds

    def act_upon_notification(self, name: str, obj, user_info) -> None:   # 0x10005614c
        params = (user_info or {}).get('PARAM_ARRAY')
        if params is None:
            log.info('Returned from the actUponNotification with data = nil')
            return
        if name == 'TIME_ELAPSED':
            self.time_elapsed += ns_float_value(params[0])
        if name == 'BRICK_TIME_ELAPSED':
            self.brick_time += ns_float_value(params[0])
        if name == 'UPDATE_CHALLENGE_TIME_ELAPSED':
            self.challenge_time_elapsed += ns_float_value(params[0])
        if name == 'UPDATE_MELEE_WEAPON_DATA':
            self.update_melee_weapons(params[0], ns_bool_value(params[1]))
        if name == 'UPDATE_WEAPON_DATA':
            f, h, k, c = (ns_bool_value(p) for p in params[1:5])
            if f or h or k or c:
                self.update_data_for_weapon(params[0], f, h, k, c, ns_float_value(params[5]))
            else:
                self.update_data_for_weapon(params[0], False, False, False, False, ns_float_value(params[5]))
        if name == 'UPDATE_KILLED_ENEMY_WITH_WEAPON':
            if params[1].get_type() != 1:
                self.update_data_for_weapon(params[0], False, False, True, False, -1.0)
                InGameStats.singleton().killed_enemi(params[1])
        if name == 'UPDATE_KILLED_ENEMY_POWERUP':
            if params[0].get_type() != 1:
                self.killed_enemi(params[0])
        if name == 'PLAYER_DIED':
            self.death = True
            self.death_by_enemy_with_name(params[0])
        if name == 'UPDATE_DIAMONDS':
            self.diamond_loot += ns_int_value(params[0])
