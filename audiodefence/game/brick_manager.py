"""ADBrickManager - wave selection, the target list, hit resolution, explosions, diamonds, power-up pops."""
from __future__ import annotations

import logging
import math

from ..platform import crand
from ..platform.defaults import ns_float_value
from ..s3d.engine import S3DEngine
from . import data
from .ingame_stats import InGameStats, notify_stats
from .modifiers import GameModifiers

log = logging.getLogger('bricks')

PI_D = 3.14159265


def _deg360(angle_rad: float) -> int:
    """((int)((a + pi) * 180 / pi)) % 360, then +360 when negative."""
    v = int(((angle_rad + PI_D) * 180.0) / PI_D)
    r = crand.c_mod(v, 360)
    return r + 360 if r < 0 else r


class BrickManager:
    _shared: 'BrickManager | None' = None
    _enemy_dictionary: dict | None = None

    @classmethod
    def shared(cls) -> 'BrickManager':                 # +[ADBrickManager sharedBrickManager] 0x1000c0fac
        if cls._shared is None:
            cls._shared = BrickManager()
        return cls._shared

    @classmethod
    def dictionary_for_enemy_name(cls, name: str):    # 0x1000c3458 (enemies.plist loaded in init)
        if cls._enemy_dictionary is None:
            cls._enemy_dictionary = data.plist_ro('enemies')
        return cls._enemy_dictionary.get(name)

    def display_name_for_enemy_with_name(self, name: str):
        return (self.dictionary_for_enemy_name(name) or {}).get('displayName')

    def __init__(self):                                # -[ADBrickManager init] 0x1000c1044
        from .passerby_manager import PasserByManager
        from .powerups import PowerUpManager
        self.bricks: list = []
        self.diamonds: list = []
        self.passer_by_manager = PasserByManager()
        self.power_up_manager = PowerUpManager()
        self.current_wave = 0
        self.deactivation_list: set = set()
        self.powerup_list = [p.get('name') for p in (data.plist_ro('Weapons').get('PowerUps') or [])
                             if isinstance(p, dict)]
        self.brick_dictionary = None
        self.brick_chance_dictionary = None
        self.brick_scenario = None
        self.loop_brick_scenario = False
        self._mode = 0
        self.player_is_dead = False
        self.current_random_angle = 0
        self.time_elapsed = 0.0
        self.next_diamond_time = 0.0
        self.minimum_squared_distance = float('inf')
        self.challenge_is_over = False
        self.started_main_menu_music = False
        self.gameplay_view_controller = None

    # --- configuration ---------------------------------------------------------------------------
    def load_brick_chance_plist(self, name: str) -> None:       # 0x1000c15d4
        self.brick_scenario = None
        self.brick_dictionary = data.plist_ro(name)
        self.brick_chance_dictionary = (self.brick_dictionary or {}).get('brick_chance')
        self.randomize_next_diamond_time()
        self.passer_by_manager.start_timers()
        self.load_impact_playlist()

    def load_brick_scenario_plist(self, name: str) -> None:     # 0x1000c176c
        self.brick_scenario = data.plist(name)
        self.loop_brick_scenario = True
        self.load_impact_playlist()

    def load_brick_challenge_array(self, bricks: list) -> None:  # 0x1000c1894
        self.brick_chance_dictionary = None
        self.brick_scenario = list(bricks)
        self.loop_brick_scenario = False
        self.load_impact_playlist()
        self.current_random_angle = crand.c_mod(crand.rand(), 360)

    def load_impact_playlist(self) -> None:                     # 0x1000c1990
        pl = S3DEngine.engine().play_list_with_name('impact')
        if pl is not None:
            pl.activate()

    def reset(self) -> None:                                    # 0x1000c1a38
        self.bricks.clear()
        self.current_wave = 0
        self.time_elapsed = 0.0
        self.started_main_menu_music = False

    @property
    def mode(self) -> int:                                      # 0x1000c301c
        if self.brick_scenario is not None:
            return 3 if self.loop_brick_scenario else 2
        return self._mode

    def set_mode(self, mode: int) -> None:
        self._mode = mode

    # --- bricks ----------------------------------------------------------------------------------
    def current_brick(self):
        return self.bricks[-1] if self.bricks else None

    def current_brick_name(self):
        b = self.current_brick()
        return b.name if b is not None else None

    def random_item_in_brick_dictionary(self, key: str):       # 0x1000c20f4
        items = (self.brick_dictionary or {}).get(key) or []
        return items[crand.rand() % len(items)] if items else None

    def brick_name_for_wave_number(self, wave: int):           # 0x1000c21a4
        row = self.brick_chance_dictionary.get(str(11 if wave > 11 else wave)) or {}
        p1 = ns_float_value(row.get('level_1'))
        t1 = p1 + ns_float_value(row.get('level_2'))
        t2 = t1 + ns_float_value(row.get('level_3'))
        t3 = t2 + ns_float_value(row.get('level_4'))
        t4 = t3 + ns_float_value(row.get('level_5'))
        if t4 != 100:
            log.info('SUM OF BRICK %i != 100', 11 if wave > 11 else wave)
        r = float(crand.c_mod(crand.rand(), 100))
        name = None
        attempts = 0
        while True:
            tried = attempts
            if name is not None and self.can_use_brick_with_name(name):
                return name
            if r < p1:
                name = self.random_item_in_brick_dictionary('level_1_bricks')
            elif r < t1:
                name = self.random_item_in_brick_dictionary('level_2_bricks')
            elif r < t2:
                name = self.random_item_in_brick_dictionary('level_3_bricks')
            elif r < t3:
                name = self.random_item_in_brick_dictionary('level_4_bricks')
            elif r < t4:
                name = self.random_item_in_brick_dictionary('level_5_bricks')
            attempts = tried + 1
            if tried < 10:
                continue
            name = self.random_item_in_brick_dictionary('level_1_bricks')

    def can_use_brick_with_name(self, name: str) -> bool:      # 0x1000c259c
        from .persistent_stats import PersistentStats
        d = data.plist_ro(name) or {}
        for key in (d.get('Enemies') or {}):
            # DIVERGENCE: canUseBrickWithName: 0x1000c259c looks each Enemies key up verbatim, but a brick
            # that wants two of the same enemy labels the slots "Chainsaw - 2", "Runner - 3", "WeakZombieB "
            # with a trailing space.  Those match nothing in enemies.plist, so the requirement came back 0
            # and the slot walked through the gate.  No gated enemy is written that way today, so nothing
            # actually escaped - but one added in a repeat slot would have.  The slot label is reduced to
            # the enemy's own name first.
            key = str(key).split(' - ')[0].strip()
            if PersistentStats.shared().kill_requirement_for_enemy(key) >= 1:
                log.info('Cannot use brick %s because it contains %s', name, key)
                return False
        return True

    def scenario_brick_name_for_wave_number(self, wave: int):  # 0x1000c28d8
        return self.brick_scenario[crand.c_mod(wave - 1, len(self.brick_scenario))]

    def load_brick_with_name(self, name: str) -> None:          # 0x1000c2930
        from .ambient import AmbientManager
        from .brick import Brick
        prev = self.current_brick()
        if prev is not None:
            prev.stop_all_sounds()
        brick = Brick(name)
        brick.set_tag(self.current_wave + 1)
        self.bricks.append(brick)
        if len(self.bricks) == 1:
            brick.activate_all_playlists()
        elif len(self.bricks) >= 2:
            before = self.bricks[-2]
            self.deactivation_list |= self.bricks[-1].activate_playlists_not_in_set(before.playlists or set())
        notify_stats('RESET_BRICK_TIME', None)
        if prev is not None and prev.ambiant_name is not None:
            prev.stop_brick_ambiant()
        if brick.ambiant_name is not None:
            AmbientManager.shared().brick_with_ambiant_started(brick.ambiant_name)

    def check_playlist_deactivation(self) -> None:              # 0x1000c2da8
        """A dying enemy's last sound has ended (-[ADEnemy update:] 0x10005eb94): unload the playlists the
        waves since have stopped using, one after another - each deactivate: completion calls this again
        (_block_invoke 0x1000c2f24), so one call empties the list.  The port had dropped that chain and
        unloaded one playlist per death."""
        if self.deactivation_list:
            # DIVERGENCE: the original takes any name from the list ([deactivationList anyObject]).  A wave
            # is cleared, and the next one's unused playlists listed, the moment its last enemy starts to
            # die, so when two die close together the first to fall silent unloaded the other's playlist -
            # and stopped its death sound half way (the chain unloads everything listed).  A playlist whose
            # enemy is still being heard is left for a later call; that enemy's own end makes it.
            name = next((n for n in self.deactivation_list if not self._playlist_still_heard(n)), None)
            if name is None:
                return
            self.deactivation_list.discard(name)
            pl = S3DEngine.engine().play_list_with_name(name)
            if pl is not None:                            # nil receives nothing, so the chain ends there
                pl.deactivate(lambda _pl: self.check_playlist_deactivation())

    def _playlist_still_heard(self, name: str) -> bool:          # PORT ADDITION: see above
        for b in self.bricks:
            for e in b.enemies:
                if e.sounds_prefix != name:
                    continue
                for s in (e.sound, e.pain_sound, e.explosion_sound):
                    if s is not None and s.playing:
                        return True
        return False

    def load_next_brick(self) -> None:                          # 0x1000c3058
        self.player_is_dead = False
        self.current_wave += 1
        if self.mode == 1:
            self.current_random_angle = crand.c_mod(crand.rand(), 360)
        name = None
        if self.brick_chance_dictionary is not None:
            name = self.brick_name_for_wave_number(self.current_wave)
            mods = GameModifiers.shared()
            if self.current_wave > 11 or mods.enragedHorde:
                mods.difficultyModifier = mods.difficultyModifier + 0.14
                log.info('Difficulty ramped to %f', mods.difficultyModifier)
        elif self.brick_scenario is not None:
            name = self.scenario_brick_name_for_wave_number(self.current_wave)
        notify_stats('SET_BRICK_NAME', name)
        self.load_brick_with_name(name)

    def clear_current_brick(self) -> None:                      # 0x1000c3364
        b = self.current_brick()
        if b is not None:
            b.clear_enemies()

    def all_potential_targets(self) -> list:                    # 0x1000c348c
        b = self.current_brick()
        out = list(b.enemies) if b is not None else []
        out.extend(self.diamonds)
        out.extend(self.passer_by_manager.all_passer_by())
        return out

    def number_of_active_objects_on_scene(self) -> int:         # 0x1000c35e4
        return sum(1 for t in self.all_potential_targets() if t.can_be_shot_at())

    def enemies_from_current_brick(self) -> list:          # 0x1000c3734
        b = self.current_brick()
        return b.enemies if b is not None else []

    # --- update ----------------------------------------------------------------------------------
    def update(self, dt: float) -> None:                        # 0x1000c37b0
        if self.player_is_dead:
            return
        self.time_elapsed += dt
        for b in list(self.bricks):
            b.update(dt)
        for d in list(self.diamonds):
            d.update(dt)
        self.passer_by_manager.update(dt)
        if self.mode == 1:
            self.power_up_manager.update(dt)
            if self.next_diamond_time < 0.0:
                self.randomize_next_diamond_time()
                self.add_diamond()
            elif not self.player_is_dead:
                self.next_diamond_time -= dt
        self.minimum_squared_distance = float('inf')
        b = self.current_brick()
        for e in (b.enemies if b is not None else []):
            if e.can_be_shot_at() and e.squared_distance < self.minimum_squared_distance:
                self.minimum_squared_distance = e.squared_distance
        if self.challenge_is_over:
            # 0x1000c3b94..0x1000c3c84: the flag starts YES and any target still exploding (5) or dying (999)
            # clears it; the score screen comes once none is left
            if not any(t.state == 5 or t.state == 999 for t in self.all_potential_targets()):
                if self.gameplay_view_controller is not None:
                    self.gameplay_view_controller.go_to_score_screen()
                self.challenge_is_over = False
        if self.mode == 4 and self.time_elapsed > 52 and not self.started_main_menu_music:
            self.start_main_menu_music()

    def start_main_menu_music(self) -> None:                    # 0x1000c3dc0
        from ..app import App
        self.started_main_menu_music = True
        App.delegate().start_menu_music('main_menu_theme')

    def blow_enemies_away(self, distance: float) -> None:      # 0x1000c3e88
        pushed = False
        for t in self.all_potential_targets():
            if t.can_be_shot_at():
                t.blow_away(distance)
                pushed = True
        if pushed:                                        # PORT ADDITION: the tornado's gust, felt
            from ..platform.haptics import Haptics
            Haptics.shared().gust()

    def closest_enemy(self):                                    # 0x1000c3ffc
        best = None
        d2 = float('inf')
        for t in self.all_potential_targets():
            if t.can_be_shot_at() and t.squared_distance < d2:
                best = t
                d2 = t.squared_distance
        return best

    # --- shooting --------------------------------------------------------------------------------
    def calculate_hit_enemies(self, weapon, angle: float) -> list:   # 0x1000c41c4
        hits: list = []
        best = float('inf')
        head = _deg360(angle)
        mods = GameModifiers.shared()
        for t in self.all_potential_targets():
            if not t.can_be_shot_at():
                continue
            t.multi_hit_factor = 0
            t.next_shot_will_be_critical = False
            t.next_shot_will_be_precise = False
            a = _deg360(t.angle_from_player)
            diff = abs(float(head - a))
            if not (diff < weapon.spread) and abs(float(a - head)) <= 360 - weapon.spread:
                continue
            if t.squared_distance > weapon.range * weapon.range:
                continue
            if diff < weapon.critical_spread or abs(float(a - head)) > 360 - weapon.critical_spread:
                if float(crand.c_mod(crand.random(), 100)) < weapon.critical_chance and not mods.noCritical:
                    t.next_shot_will_be_critical = True
                    if self.gameplay_view_controller is not None:
                        self.gameplay_view_controller.player_did_a_critical_hit()
                    notify_stats('UPDATE_WEAPON_DATA', weapon.name, False, False, False, True, -1.0)
                    notify_stats('UPDATE_CRITICAL_HITS', 1)
                else:
                    t.next_shot_will_be_precise = True
            if mods.luckyShots and crand.c_mod(crand.random(), 100) == 1:
                t.next_shot_will_be_critical = True
            if t.next_shot_will_be_critical and self.gameplay_view_controller is not None:
                self.gameplay_view_controller.player_did_a_critical_hit()
            if weapon.multihit:
                hits.append(t)
            elif diff < best:
                hits.clear()
                hits.append(t)
                best = diff
            elif diff == best and t.squared_distance < hits[0].squared_distance:
                hits.clear()
                hits.append(t)
        return hits

    def shot_with_special_weapon(self, weapon) -> None:         # 0x1000c4b38
        from .weapon import MeleeWeapon
        hits = self.calculate_hit_enemies(weapon, S3DEngine.engine().head_orientation)
        for t in hits:
            t.hit_by_weapon(weapon)
        if isinstance(weapon, MeleeWeapon):
            if not hits:
                weapon.play_miss_sound()
                return
            weapon.play_hit_sound()
        elif not hits:
            return
        self.check_deaths_for_hit_enemies(hits, weapon.name)

    def shot_with_weapon(self, weapon) -> None:                 # 0x1000c4dfc
        from .weapon import MeleeWeapon
        hits = self.calculate_hit_enemies(weapon, S3DEngine.engine().head_orientation)
        count = len(hits)
        factor = count if weapon.multihit else 0
        melee = isinstance(weapon, MeleeWeapon)
        for t in hits:
            if weapon.multihit:
                t.multi_hit_factor = factor
                factor = -1
            t.hit_by_weapon(weapon)
            if melee:
                notify_stats('UPDATE_MELEE_WEAPON_DATA', weapon.name, True)
            else:
                notify_stats('UPDATE_WEAPON_DATA', weapon.name, True, True, False, False, -1.0)
        if count == 0:
            notify_stats('DECREMENT_COMBO', None)
            if melee:
                notify_stats('UPDATE_MELEE_WEAPON_DATA', weapon.name, False)
            else:
                notify_stats('UPDATE_WEAPON_DATA', weapon.name, True, False, False, False, -1.0)
        if melee:
            if count == 0:
                weapon.play_miss_sound()
                return
            weapon.play_hit_sound()
        elif count == 0:
            return
        self.check_deaths_for_hit_enemies(hits, weapon.name)

    def target_enemi_for_explosive_weapon(self, weapon):       # 0x1000c57b8
        head = _deg360(S3DEngine.engine().head_orientation)
        best = None
        best_d2 = float('inf')
        direct = False
        for t in self.all_potential_targets():
            if not t.can_be_shot_at():
                continue
            a = _deg360(t.angle_from_player)
            diff = abs(float(head - a))
            if diff >= weapon.spread:
                continue
            if t.squared_distance >= weapon.range * weapon.range:
                continue
            if diff < weapon.critical_spread:
                if t.squared_distance < best_d2:
                    best, best_d2, direct = t, t.squared_distance, True
            else:
                if t.squared_distance >= best_d2 or direct:
                    continue
                best, best_d2, direct = t, t.squared_distance, False
        if direct and best is not None:
            best.next_shot_will_be_critical = True
        return best

    def solve_explosion_with_dictionary(self, d: dict, position, weapon_name, ignore_tinnitus: bool) -> None:
        """0x1000c5c40"""
        from ..platform.haptics import Haptics            # PORT ADDITION: every explosion felt, by distance
        Haptics.shared().explosion((position[0] ** 2 + position[1] ** 2) ** 0.5)
        hits = []
        radius = ns_float_value(d.get('radius'))
        for t in self.all_potential_targets():
            if not t.can_be_shot_at():
                continue
            dx = position[0] - t.position[0]
            dy = position[1] - t.position[1]
            if dx * dx + dy * dy >= radius * radius:
                continue
            t.hit_by_explosion(position, ns_float_value(d.get('damages')), ns_float_value(d.get('dispersal')),
                               radius, weapon_name)
            hits.append(t)
        p2 = position[0] * position[0] + position[1] * position[1]
        if not ignore_tinnitus and p2 < 25:
            gvc = self.gameplay_view_controller
            if gvc is not None and gvc.player is not None:
                gvc.player.start_tinitus_with_intensity(p2 / -25 + 1)
        notify_stats('UPDATE_WEAPON_DATA', weapon_name, True, len(hits) != 0, False, False, -1.0)
        self.check_deaths_for_hit_enemies(hits, weapon_name)

    def solve_explosion_of_projectile(self, projectile) -> None:   # 0x1000c6360
        w = projectile.weapon
        d = {'radius': projectile.explosion_radius, 'damages': w.damages, 'dispersal': w.dispersal}
        self.solve_explosion_with_dictionary(d, projectile.position, w.name, False)

    def check_deaths_for_hit_enemies(self, hits: list, weapon_name) -> None:   # 0x1000c66a4
        from .missions import MissionManager
        for t in hits:
            if t.life > 0.0:
                continue
            gvc = self.gameplay_view_controller
            if gvc is not None:
                gvc.player_killed_enemy(t, InGameStats.singleton().combo)
            MissionManager.shared().enemi_killed(t.display_name, weapon_name)
            if weapon_name in self.powerup_list:
                notify_stats('UPDATE_KILLED_ENEMY_POWERUP', t, weapon_name)
            else:
                notify_stats('UPDATE_KILLED_ENEMY_WITH_WEAPON', weapon_name, t)
        MissionManager.shared().player_shot_with_weapon(weapon_name, len(hits) != 0)

    # --- triggers --------------------------------------------------------------------------------
    def sound_or_enemy_with_name_was_deactivated(self, name, skipped: bool = False) -> None:   # 0x1000c6bb0
        b = self.current_brick()
        if b is None:
            return
        if b.brick_is_cleared():
            self.current_brick_is_cleared()
        else:
            self.check_enemies_spawn_after_kill(name, skipped)

    def current_brick_is_cleared(self) -> None:                 # 0x1000c6ca0
        notify_stats('DEFEATED_BRICK', None)
        m = self.mode
        if m in (1, 3):
            self.load_next_brick()
        elif m == 2:
            if self.current_wave == len(self.brick_scenario):
                self.challenge_is_over = True
            else:
                self.load_next_brick()
        elif m == 4:
            if self.gameplay_view_controller is not None:
                self.gameplay_view_controller.go_to_score_screen()

    def check_spawn_on_start(self, name) -> None:              # 0x1000c7084
        b = self.current_brick()
        if b is not None:
            b.check_spawn_on_start(name)

    def check_enemies_spawn_after_kill(self, name, skipped: bool) -> None:   # 0x1000c7118
        b = self.current_brick()
        if b is not None:
            b.check_spawn_after_kill(name, skipped)

    def stop_all_enemies_after_player_death_by_enemy_with_name(self, name: str) -> None:   # 0x1000c71b4
        self.clean_passers_by()
        gvc = self.gameplay_view_controller
        if gvc is not None:
            gvc.show_death_overlay()
        self.player_is_dead = True
        for b in list(self.bricks):
            b.stop_all_enemies_after_player_death()
        for d in list(self.diamonds):
            d.stop_after_player_was_killed()
        for p in list(self.passer_by_manager.all_passer_by()):
            p.stop_after_player_was_killed()
        from .weapon_manager import WeaponManager                # PORT ADDITION: and the gun and the
        WeaponManager.shared().stop_firing_after_player_was_killed()   # power-up in hand
        power_up = WeaponManager.shared().power_up
        if power_up is not None:
            power_up.stop_after_player_was_killed()

    def show_revive_view(self) -> None:                         # 0x1000c74fc
        if self.gameplay_view_controller is not None:
            self.gameplay_view_controller.show_revive_view()

    def revive(self) -> None:                                   # 0x1000c7558
        self.clear_current_brick()
        self.load_next_brick()
        self.next_diamond_time += 10

    def game_over(self) -> None:                                # 0x1000c75b0
        from .missions import MissionManager
        MissionManager.shared().player_died()
        MissionManager.shared().end_gameplay()
        gvc = self.gameplay_view_controller
        m = self.mode
        if gvc is None:
            return
        if m == 1:
            gvc.quit_gameplay_with_fail()
        elif m == 2:
            gvc.go_to_challenge_failed_screen()
        elif m == 3:
            gvc.quit_gameplay_with_fail()

    # --- diamonds / passers-by / power-ups -------------------------------------------------------
    def add_diamond(self) -> None:                              # 0x1000c7748
        from .passerby import DiamondDropper
        d = DiamondDropper('Diamond')
        a = float(crand.c_mod(crand.rand(), 360)) * PI_D / 180.0
        d.set_position((math.cos(a) * 9, math.sin(a) * 9))
        d.tag = len(self.diamonds) + 300000
        d.init_sounds()
        d.set_state(0)
        d.spawn_time = 2.0
        d.update_orientation()
        self.diamonds.append(d)

    def randomize_next_diamond_time(self) -> None:              # 0x1000c78ec
        self.next_diamond_time = float(crand.c_mod(crand.rand(), 30) + 40)

    def clean_diamonds(self) -> None:
        for d in self.diamonds:
            d.deactivate_playlist()

    def stop_all_sounds_in_current_brick(self) -> None:
        b = self.current_brick()
        if b is not None:
            b.stop_all_sounds()

    def has_skippable_sounds_playing(self) -> bool:
        b = self.current_brick()
        return bool(b is not None and b.has_skippable_sounds_playing())

    def skip_skippable_sounds(self) -> None:
        b = self.current_brick()
        if b is not None:
            b.skip_all_skippable_sounds()

    def add_passer_by(self, p) -> None:
        self.passer_by_manager.add_passer_by(p)

    def passers_by_count(self) -> int:
        return len(self.passer_by_manager.all_passer_by())

    def clean_passers_by(self) -> None:
        self.passer_by_manager.clean()

    def try_to_pop_power_up_container(self) -> None:           # 0x1000c7b4c
        self.power_up_manager.try_to_pop_power_up()

    def force_to_pop_power_up_container_with_type(self, kind) -> None:   # 0x1000c7b68
        k = str(kind).upper() if kind is not None else ''
        if k == 'FIREWORKS':
            self.power_up_manager.pop_power_up_with_type(2)
        elif k == 'MINIGUN':
            self.power_up_manager.pop_power_up_with_type(1)
        elif k == 'TESLA':
            self.power_up_manager.pop_power_up_with_type(4)
        elif k == 'TORNADO':
            self.power_up_manager.pop_power_up_with_type(3)
        else:
            self.power_up_manager.pop_power_up_with_type(0)

    def pause_all_bricks(self) -> None:                         # 0x1000c7d6c
        for b in self.bricks:
            b.pause()
        self.passer_by_manager.pause()
        for d in self.diamonds:
            d.pause()

    def resume_all_bricks(self) -> None:                        # 0x1000c7de8
        for b in self.bricks:
            b.resume()
        for d in self.diamonds:
            d.resume()
        self.passer_by_manager.resume()

    def clean(self) -> None:                                    # 0x1000c7e64
        self.clean_passers_by()
        self.passer_by_manager.remove_all_passers_by()
        self.clean_diamonds()
        self.diamonds.clear()
        for b in self.bricks:
            b.clean()
        self.bricks.clear()
        pl = S3DEngine.engine().play_list_with_name('impact')
        if pl is not None:
            pl.deactivate()
