"""ADPersistentStats - lifetime statistics in NSUserDefaults (ENEMY_DATA, TOTALS_DATA, WEAPON_DATA)."""
from __future__ import annotations

import math

from ..platform.defaults import UserDefaults, ns_bool_value, ns_int_value
from . import data

ENEMY_DATA = 'ENEMY_DATA'
TOTALS_DATA = 'TOTALS_DATA'
WEAPON_DATA = 'WEAPON_DATA'


def build_from_dictionary(weapons_plist: dict) -> dict:   # -[ADPersistentStats buildFromDictionary:ClearItems:] 0x100084608
    out = {}
    for w in weapons_plist.get('Weapons', []):
        out[w.get('name')] = {'shotsFired': 0, 'shotsHit': 0, 'kills': 0,
                              'melee': w.get('melee') is not None, 'displayName': w.get('displayName')}
    return out


class PersistentStats:
    _shared: 'PersistentStats | None' = None

    @classmethod
    def shared(cls) -> 'PersistentStats':     # +[ADPersistentStats persistentStats] 0x100083aec
        if cls._shared is None:
            ps = PersistentStats()
            cls._shared = ps
            d = ps.defaults
            if not isinstance(d.object(ENEMY_DATA), dict):
                enemies = data.plist_ro('enemies')
                seeded = {}
                for key, e in enemies.items():
                    if e.get('displayName') is not None:
                        seeded[e['displayName']] = {'Killed': 0, 'Casualty': 0}
                d.set_object(seeded, ENEMY_DATA)
                d.synchronize()
            if not isinstance(d.object(TOTALS_DATA), dict):
                from .inventory import Inventory
                totals = data.plist('totalsStats')
                totals['Weapons obtained'] = Inventory.shared().number_of_weapons_unlocked()
                d.set_object(totals, TOTALS_DATA)
                d.set_object('0', 'TOTAL_TIME_PLAYED')
                d.synchronize()
            if not isinstance(d.object(WEAPON_DATA), dict):
                d.set_object(build_from_dictionary(data.plist_ro('Weapons')), WEAPON_DATA)
                d.synchronize()
        return cls._shared

    def __init__(self):
        self.defaults = UserDefaults.standard()
        self.unlocked_enemies: list = []

    # --- accessors -------------------------------------------------------------------------------
    def enemy_stat_data(self) -> dict:
        return self.defaults.object(ENEMY_DATA) or {}

    def total_stat_data(self) -> dict:
        return self.defaults.object(TOTALS_DATA) or {}

    def weapon_stat_data(self) -> dict:
        return self.defaults.object(WEAPON_DATA) or {}

    def enemy_list_with_kills_greater_than(self, count: int) -> dict:   # 0x100088edc
        return {name: entry for name, entry in self.enemy_stat_data().items()
                if ns_int_value(entry.get('Killed')) > count}

    def unlocked_weapons(self) -> dict:                  # getUnlockedWeapons 0x100089188
        from .inventory import Inventory
        stats = self.weapon_stat_data()
        out = {}
        for entry in Inventory.shared().weapons:          # ADInventory weapons is an array of dictionaries
            if ns_bool_value(entry.get('purchased')):
                out[entry.get('name')] = stats.get(entry.get('name'))
        return out

    def compute_challenges_won_and_save(self) -> None:   # 0x100088b54
        from .challenge_data import ChallengeData
        totals = dict(self.total_stat_data())
        totals['Challenge stars unlocked'] = ChallengeData.shared().compute_total_challenges_won()
        self._save_totals(totals)

    def _save_totals(self, totals: dict) -> None:
        self.defaults.set_object(totals, TOTALS_DATA)
        self.defaults.synchronize()

    # --- unlocks ---------------------------------------------------------------------------------
    def compute_total_enemy_kill_count(self) -> int:     # 0x10008895c
        total = 0
        for v in self.enemy_stat_data().values():
            if isinstance(v, dict):
                total += ns_int_value(v.get('Killed'))
        return total

    def kill_requirement_for_enemy(self, name: str) -> int:   # 0x100084ea8
        from .brick_manager import BrickManager
        d = BrickManager.dictionary_for_enemy_name(name) or {}
        req = ns_int_value((d.get('bestiary') or {}).get('Unlock requirement'))
        if req < 1:
            return 0
        return max(0, req - self.compute_total_enemy_kill_count())

    def all_unlocked_enemies(self) -> list:              # 0x100085dd4 (keys are display names - QUIRK)
        return [k for k in self.enemy_stat_data() if self.kill_requirement_for_enemy(k) == 0]

    def enemy_kills_by_name(self, name: str) -> int:
        return ns_int_value((self.enemy_stat_data().get(name) or {}).get('Killed'))

    # --- saving a run ----------------------------------------------------------------------------
    def save_enemy_data(self, run_enemies: dict) -> None:     # 0x1000850e4
        before = set(self.all_unlocked_enemies())
        stored = self.enemy_stat_data()
        merged = {}
        for key, cur in stored.items():
            run = run_enemies.get(key)
            if run is not None:
                merged[key] = {'Killed': ns_int_value(run.get('Killed')) + ns_int_value(cur.get('Killed')),
                               'Casualty': ns_int_value(run.get('Casualty')) + ns_int_value(cur.get('Casualty'))}
            else:
                merged[key] = {'Killed': ns_int_value(cur.get('Killed')),
                               'Casualty': ns_int_value(cur.get('Casualty'))}
        self.defaults.set_object(merged, ENEMY_DATA)
        self.unlocked_enemies = [e for e in self.all_unlocked_enemies() if e not in before]
        self.defaults.synchronize()

    def save_endless_mode_kills(self, kills: int) -> None:    # 0x1000861e0
        t = dict(self.total_stat_data())
        t['Total kills'] = ns_int_value(t.get('Total kills')) + kills
        if ns_int_value(t.get('Best number of kills')) < kills:
            t['Best number of kills'] = kills
        self._save_totals(t)

    def save_play_time_data(self, seconds: float, mode: str) -> None:   # 0x1000864b4
        t = dict(self.total_stat_data())
        if mode == 'CHALLENGE':
            t['Total play time in Challenge Mode'] = self._add_time(t.get('Total play time in Challenge Mode'), seconds)
        elif mode == 'ENDLESS':
            t['Total play time in Endless Mode'] = self._add_time(t.get('Total play time in Endless Mode'), seconds)
            longest = self._to_seconds(t.get('Longest Endless Mode'))
            if longest < seconds:
                t['Longest Endless Mode'] = game_time_to_string(seconds)
        self._save_totals(t)
        self.defaults.set_object(str(self.total_time_played()), 'TOTAL_TIME_PLAYED')
        self.defaults.synchronize()

    @staticmethod
    def _to_seconds(text) -> int:
        parts = str(text or '00:00:00').split(':') + ['0', '0', '0']
        return ns_int_value(parts[0]) * 3600 + ns_int_value(parts[1]) * 60 + ns_int_value(parts[2])

    @staticmethod
    def _add_time(text, seconds: float) -> str:          # updateTotalPlayTime:WithKey: 0x1000884c0
        parts = str(text or '00:00:00').split(':') + ['0', '0', '0']
        s = int(math.floor(seconds) + ns_int_value(parts[2]))
        m = ns_int_value(parts[1]) + s // 60
        h = ns_int_value(parts[0]) + m // 60
        return f'{h:02d}:{m % 60:02d}:{s % 60:02d}'

    def total_time_played(self) -> int:                  # hours, rounded (getTotalTimePlayed 0x100089488)
        t = self.total_stat_data()
        hours = 0
        for key in ('Total play time in Challenge Mode', 'Total play time in Endless Mode'):
            parts = str(t.get(key) or '00:00:00').split(':') + ['0', '0']
            h = ns_int_value(parts[0])
            hours += h + 1 if ns_int_value(parts[1]) > 29 else h
        return hours

    # DIVERGENCE: the original writes only what was spent, and its stats screen asks for "Money earned"
    # and "Diamonds collected" - keys nothing ever writes, so both rows read 0 for ever.  The port fills
    # them in as the run's rewards are credited, and shows the spent totals beside them.
    def save_coins_earned(self, earned: int) -> None:    # PORT ADDITION
        t = dict(self.total_stat_data())
        t['Money earned'] = ns_int_value(t.get('Money earned')) + int(earned)
        self._save_totals(t)

    def save_diamonds_earned(self, earned: int) -> None:  # PORT ADDITION
        t = dict(self.total_stat_data())
        t['Diamonds collected'] = ns_int_value(t.get('Diamonds collected')) + int(earned)
        self._save_totals(t)

    def save_coins_data(self, spent: int) -> None:       # 0x1000869f4
        t = dict(self.total_stat_data())
        t['Total Money Spent'] = ns_int_value(t.get('Total Money Spent')) + spent
        self._save_totals(t)

    def save_diamonds_data(self, spent: int) -> None:    # 0x100086c2c
        t = dict(self.total_stat_data())
        t['Total Diamonds Spent'] = ns_int_value(t.get('Total Diamonds Spent')) + spent
        self._save_totals(t)

    def save_shots_data(self, shots: dict) -> None:      # 0x100086e64
        t = dict(self.total_stat_data())
        t['Shots fired'] = ns_int_value(shots.get('Shots fired')) + ns_int_value(t.get('Shots fired'))
        t['Melee swings'] = ns_int_value(shots.get('Melee swings')) + ns_int_value(t.get('Melee swings'))
        self._save_totals(t)

    def save_weapons_data(self, run: dict) -> None:      # 0x1000871b8
        stored = self.weapon_stat_data()
        merged = {}
        for key, cur in stored.items():
            r = run.get(key) or {}
            merged[key] = {'shotsFired': ns_int_value(r.get('shotsFired')) + ns_int_value(cur.get('shotsFired')),
                           'shotsHit': ns_int_value(r.get('shotsHit')) + ns_int_value(cur.get('shotsHit')),
                           'kills': ns_int_value(cur.get('kills')) + ns_int_value(r.get('kills'))}
        self.defaults.set_object(merged, WEAPON_DATA)
        self.defaults.synchronize()

    def update_counter(self, key: str) -> None:          # 0x1000878f4
        t = dict(self.total_stat_data())
        t[key] = ns_int_value(t.get(key)) + 1
        self._save_totals(t)

    def update_missions_completed(self, n: int) -> None:
        t = dict(self.total_stat_data())
        t['Total number of missions completed'] = ns_int_value(t.get('Total number of missions completed')) + n
        self._save_totals(t)

    def update_missions_skipped(self, n: int) -> None:   # 0x100087d7c
        t = dict(self.total_stat_data())
        t['Total number of missions skipped'] = ns_int_value(t.get('Total number of missions skipped')) + n
        self._save_totals(t)

    def update_deaths(self) -> None:                     # 0x100087fb4
        self.update_counter('Deaths')

    def update_number_of_weapons_owned(self) -> None:    # 0x1000881e4
        self.update_counter('Weapons obtained')

    def high_score(self) -> int:                         # 0x100088d80
        return self.defaults.integer('highscore')

    def save_score(self, score: int) -> None:            # 0x100088df8
        if self.high_score() < score:
            self.defaults.set_integer(score, 'highscore')
            self.defaults.synchronize()


def game_time_to_string(seconds: float) -> str:          # 0x100088414
    s = int(math.floor(seconds))
    m = int(math.floor(seconds / 60))
    h = int(math.floor(float(m) / 60))
    return f'{h:02d}:{m % 60:02d}:{s % 60:02d}'
