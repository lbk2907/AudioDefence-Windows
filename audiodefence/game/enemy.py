"""ADEnemy - one enemy (also the base class of passers-by, diamonds and power-up containers).

Ported method by method from the arm64 binary; addresses in the comments.
Geometry: the player is the origin, positions are game units, ``orientation`` is the unit vector towards
the player and ``angleFromPlayer`` is atan2 of the position.
"""
from __future__ import annotations

import logging
import math

from ..platform import crand
from ..platform.runloop import RunLoop
from ..s3d.engine import S3DEngine
from .modifiers import GameModifiers

log = logging.getLogger('enemy')

NORMAL_ANGLES = (-1.5707963705062866, 1.5707963705062866)   # tconst_100181c28
PI_D = 3.14159265


def _f(d, key, default=0.0) -> float:
    from ..platform.defaults import ns_float_value
    if d is None:
        return default
    v = d.get(key)
    return default if v is None else ns_float_value(v)


class Enemy:
    # -[ADEnemy initWithName:] 0x10005ddd4
    def __init__(self, name: str):
        from .brick_manager import BrickManager
        from ..platform.defaults import ns_float_value, ns_int_value
        self.name = name
        self.sounds_prefix = name.split(' ')[0]
        d = BrickManager.dictionary_for_enemy_name(self.sounds_prefix) or {}
        self.attack_distance = 0.3
        self._life = ns_float_value(d.get('life'))
        self.max_life = self._life
        self.speed = ns_float_value(d.get('speed'))
        self.ambiant_name = d.get('ambiant')
        self.score = ns_int_value(d.get('score'))
        self.combo_bonus = ns_int_value(d.get('comboBonus'))
        self.coins_reward = ns_int_value(d.get('coinsReward'))
        self.explosion_dictionary = d.get('explosion')
        self.shield_dictionary = d.get('shield')
        self.dodge_dictionary = d.get('dodge')
        self.circling_dictionary = d.get('circling')
        self.berserk_dictionary = d.get('berserk')
        self._state = 0
        self.time_in_state = 0.0
        self.set_state(-1)
        self.spawn_sound_duration = 1.0
        if d.get('agressiveSpeed') is not None:
            self.agressive_speed = ns_float_value(d.get('agressiveSpeed'))
        else:
            self.agressive_speed = self.speed
        mods = GameModifiers.shared()
        self._life = mods.enemi_life_modifier() * self._life
        self.speed = mods.enemi_speed_modifier() * self.speed
        self.playlist = S3DEngine.engine().play_list_with_name(self.sounds_prefix)
        self.display_name = self.display_name_for_name()
        # remaining ivars
        self.position = (0.0, 0.0)
        self.orientation = (0.0, 0.0)
        self.normal_orientation = (0.0, 0.0)
        self.normal_angle = 0.0
        self.squared_distance = 0.0
        self.angle_from_player = 0.0
        self.random_additional_spawn_angle = 0.0
        self.spawn_time = 0.0
        self.spawn_after = None
        self.tag = 0
        self.sound = None
        self.pain_sound = None
        self.explosion_sound = None
        self.dead_sound_has_played = False
        self.shield_damages_taken = 0.0
        self.shield_duration = 0.0
        self.next_shot_will_be_critical = False
        self.next_shot_will_be_precise = False
        self.multi_hit_factor = 0
        self.use_own_impact_sounds = False
        self.destroyed = False
        self._revive_done = False                          # PORT ADDITION: see attack()
        self._voices = {}                                  # PORT ADDITION: see voice_of()
        self._overlapping = {}                             # and overlapping_voice_of()
        self.parent_brick = None
        self.required_playlist_activation = False
        self.playlist_activated = False
        self.spawned = False
        self.sound_was_playing = False

    def __repr__(self) -> str:
        return f'<{type(self).__name__} {self.name} state={self._state}>'

    # --- simple accessors ------------------------------------------------------------------------
    @property
    def life(self) -> float:
        return self._life

    @property
    def state(self) -> int:
        return self._state

    def get_type(self) -> int:                            # 0x100063dbc
        return 0

    def display_name_for_name(self):                      # 0x10006207c
        from . import data
        return (data.plist_ro('enemies').get(self.name) or {}).get('displayName')

    def set_state(self, state: int) -> None:              # 0x10005fb04
        if self._state == state:
            return
        log.debug('[%s] Change state to : %i', self.name, state)
        self._state = state
        self.time_in_state = 0.0

    # --- geometry --------------------------------------------------------------------------------
    def set_position_from_dictionary(self, d: dict) -> None:   # 0x10005e624
        t1 = (_f(d, 'spawn_angle') + self.random_additional_spawn_angle) * PI_D
        dist = _f(d, 'spawn_distance')
        a = t1 / 180.0
        self.set_position((dist * math.sin(a), dist * math.cos(a)))
        self.update_orientation()
        if self.dodge_dictionary is not None or self.circling_dictionary is not None:
            self.randomize_normal_angle()
            self.update_normal_orientation()

    def set_orientation_with(self, x: float, y: float) -> None:    # 0x10005e828
        n = math.sqrt(x * x + y * y)
        self.orientation = (x / n, y / n)
        px, py = self.position
        self.angle_from_player = math.atan2(py / n, px / n)

    def update_orientation(self) -> None:                 # 0x10005e8e4
        px, py = self.position
        n = math.sqrt(px * px + py * py)
        if n == 0.0:
            return
        self.orientation = (-px / n, -py / n)
        self.angle_from_player = math.atan2(py / n, px / n)

    def randomize_normal_angle(self) -> None:             # 0x10005e9b0
        self.normal_angle = NORMAL_ANGLES[crand.rand() & 1]

    def update_normal_orientation(self) -> None:          # 0x10005e9ec
        ox, oy = self.orientation
        s, c = math.sin(self.normal_angle), math.cos(self.normal_angle)
        self.normal_orientation = (ox * c - oy * s, c * oy + ox * s)
        self.update_orientation()

    def set_position(self, pos) -> None:                  # 0x10005ea80
        self.position = (float(pos[0]), float(pos[1]))
        if self.sound is not None:
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
        self.squared_distance = self.position[0] ** 2 + self.position[1] ** 2

    def _move(self, dt: float, dx: float, dy: float) -> None:
        px, py = self.position
        self.set_position((px + dt * (dx * self.speed), py + dt * (dy * self.speed)))

    # --- update ----------------------------------------------------------------------------------
    def update(self, dt: float) -> None:                  # 0x10005eb94
        from .brick_manager import BrickManager
        st = self._state
        action = None
        if st == 999:
            if self.time_in_state > 0.1 and self.pain_sound is not None and self.pain_sound.playing:
                self.dead_sound_has_played = True
            if self.time_in_state > 0.1 and self.time_in_state > self._duration(self.pain_sound) \
                    and self.dead_sound_has_played:
                BrickManager.shared().check_playlist_deactivation()
                self.set_state(-1)
                action = self.destroy_enemy
        elif st == 0:
            if self.time_in_state > self.spawn_time - 2 and not self.required_playlist_activation:
                self.required_playlist_activation = True
                self.parent_brick.load_playlist_with_name(self.sounds_prefix)
            if self.time_in_state > self.spawn_time:
                if self.playlist_activated:
                    action = self.spawn
                else:
                    log.info('%s wants to spawn but has no playlist', self.name)
                    self.playlist_activated = True
        elif st == 1:
            if self.spawn_sound_duration == 0.0:
                action = self.spawn
            elif self.time_in_state > self.spawn_sound_duration:
                action = self.walk if self.squared_distance >= 9 else self.aggressive
        elif st == 2:
            if self.circling_dictionary is not None:
                f = _f(self.circling_dictionary, 'circlingFactor')
                dx = (1 - f) * self.orientation[0] + f * self.normal_orientation[0]
                dy = (1 - f) * self.orientation[1] + f * self.normal_orientation[1]
            else:
                dx, dy = self.orientation
            if self.berserk_dictionary is not None:
                dx, dy = -self.orientation[0], -self.orientation[1]
            self._move(dt, dx, dy)
            if self.squared_distance < 9:
                (self.transition_to_berserk if self.berserk_dictionary is not None else self.aggressive)()
            if self.circling_dictionary is not None:
                self.update_orientation()
                self.update_normal_orientation()
            if self.berserk_dictionary is not None:
                if self.time_in_state > _f(self.berserk_dictionary, 'disappearAfter'):
                    action = self.berserk_go_away
                elif self.squared_distance > 144:
                    action = self.berserk_go_away
        elif st == 3:
            self.speed = self.agressive_speed
            self._move(dt, *self.orientation)
            if self.squared_distance < self.attack_distance * self.attack_distance:
                RunLoop.main().post('PLAYER_DIED', None, {'PARAM_ARRAY': [self.name]})
                self.attack()
        elif st == 4:
            self.speed = 0.0
        elif st == 5:
            if self.time_in_state > 0.1:
                self.set_state(999)
        elif st == 6:
            shield_time = _f(self.shield_dictionary, 'shieldTime')
            if self.time_in_state >= shield_time:
                if self.shield_duration != 0.0:
                    if self.time_in_state > shield_time + self.shield_duration:
                        action = self.walk
                else:
                    self.shield_duration = self.play_any_sound_containing('_shieldup', False, True)
        elif st == 7:
            if self.time_in_state <= _f(self.dodge_dictionary, 'dodgeTime'):
                ds = _f(self.dodge_dictionary, 'dodgeSpeed')
                px, py = self.position
                self.set_position((px + dt * (ds * self.normal_orientation[0]),
                                   py + dt * (ds * self.normal_orientation[1])))
                action = self.update_orientation
            else:
                self.walk()
                self.randomize_normal_angle()
                action = self.update_normal_orientation
        elif st == 8:
            self._move(dt, *self.orientation)
            if self.squared_distance < 0.09:
                # DIVERGENCE (user request): a berserk enemy that reaches the player goes straight to
                # `attack` in the original - case 8 at 0x10005f398 has no notification, where case 3 posts
                # one at 0x10005f16c - so nothing told ADInGameStats that the player had died.  The
                # Berserk's own "killed you" count stayed 0 however many times it killed you
                # (`death_by_enemy_with_name` is only reached through this notification), and the Deaths
                # total missed it as well, `save_stats` asking `update_deaths` only when the same
                # notification has set its flag.  It is the one enemy that kills from this state.
                RunLoop.main().post('PLAYER_DIED', None, {'PARAM_ARRAY': [self.name]})
                action = self.attack
        elif st == 9:
            if self.time_in_state > 0.1 and self.time_in_state > self._duration(self.sound):
                action = self.berserk
        if action is not None:
            action()
        if self.sound is not None:
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
        self.time_in_state = self.time_in_state + dt

    @staticmethod
    def _duration(sound) -> float:
        return sound.duration if sound is not None else 0.0

    # --- state entries ---------------------------------------------------------------------------
    def spawn(self) -> None:                              # 0x10005fbc0
        from .ambient import AmbientManager
        from .brick_manager import BrickManager
        self.set_state(1)
        self.spawn_sound_duration = self.play_any_sound_containing('_spawn', False, True)
        self.spawned = True
        if self.ambiant_name:
            AmbientManager.shared().enemy_with_ambiant_name_appeared(self.ambiant_name)
        BrickManager.shared().check_spawn_on_start(self.name)

    def walk(self) -> None:                               # 0x10005fe0c
        self.set_state(2)
        self.play_any_sound_containing('_approach_')

    def walk_or_agressive(self) -> None:                  # 0x10005fe54
        if self._life <= 0.0 or self.destroyed:
            return
        if self._state == 3:
            self.aggressive()
        elif self._state == 2:
            self.walk()
        elif self._state == 8:
            # DIVERGENCE: 0x10005fe54 answers for states 2 and 3 only (user request).  A hit stops the
            # enemy's own loop so the pain sound can be heard and asks for it back when that sound ends
            # (`play_hit_sound_for_damages`), but a Berserk charging the player is in state 8, which this
            # does not answer - so the growl stopped at the first hit and never came back, and the thing
            # running at you ran at you in silence.  `berserk` cannot be called to bring it back: it
            # returns at once when the state is already 8, being the method that sets it.
            self.play_any_sound_containing('_aggressive', True, True)

    def dodge(self) -> None:                              # 0x10005fefc
        self.set_state(7)
        self.play_any_sound_containing('_dodge_', False, True)

    def protect(self) -> None:                            # 0x10005ff4c
        if self._state == 2:
            self.shield_damages_taken = 0.0
            self.shield_duration = 0.0
            self.set_state(6)
            self.play_any_sound_containing('_invincible')

    def aggressive(self) -> None:                         # 0x10005ffd4
        self.update_orientation()
        mods = GameModifiers.shared()
        if mods.tesla:
            pl = S3DEngine.engine().play_list_with_name('roulette_tesla')
            snd = pl.sound('roulette_tesla_SPA') if pl else None
            if snd is not None:
                snd.set_spatialized(True)
                if self.sound is not None:
                    snd.set_planar(self.sound.planar)
                snd.play()
                snd.add_3d_sound_end_callback(lambda s: pl.deactivate())
            mods.set_tesla(False)
            self._life = 0.0
            self.die()
            return
        self.set_state(3)
        self.play_any_sound_containing('_aggressive')

    def attack(self) -> None:                             # 0x100060304
        from .brick_manager import BrickManager
        self.speed = 0.0
        bm = BrickManager.shared()
        if bm.player_is_dead:
            return
        from ..platform.haptics import Haptics            # PORT ADDITION: the zombie has you
        Haptics.shared().player_killed()
        self.set_state(4)
        self.play_any_sound_containing('_attack', False, False)
        if self.sound is not None:
            self.sound.set_gain(1.3)
        bm.stop_all_enemies_after_player_death_by_enemy_with_name(str(self.name))
        if self.sound is not None:
            self.sound.add_3d_sound_end_callback(lambda s: self.after_attack_sound())
        # DIVERGENCE: the original shows the revive screen only when this sound ends, and the attack sounds
        # run from about a second to 8.7 s (WeakZombieC, WeakZombieD) - Jim_attack is 71 s - so a death can
        # sit in silence long enough to look like a hang.  The port waits for the sound as the original
        # does, but no longer than REVIVE_AFTER; the sound itself is left to finish.
        RunLoop.main().call_later(self.REVIVE_AFTER, self.after_attack_sound)

    #: PORT ADDITION: the longest a death scene is allowed to hold the revive screen back
    REVIVE_AFTER = 5.0

    def after_attack_sound(self) -> None:                 # 0x1000605f4
        from .brick_manager import BrickManager
        if self._revive_done:                             # the sound ended and the cap fired, or the other way
            return
        self._revive_done = True
        self.set_state(-1)
        bm = BrickManager.shared()
        if bm.mode == 2:
            bm.game_over()
        if bm.mode == 1:
            bm.show_revive_view()

    def transition_to_berserk(self) -> None:              # 0x10006077c
        if self._state in (8, 9):
            return
        self.speed = 0.0
        self.play_any_sound_containing('_transition', False, True)
        self.set_state(9)

    def berserk(self) -> None:                            # 0x100060824
        if self._state == 8:
            return
        self.speed = _f(self.berserk_dictionary, 'berserkSpeed')
        self.set_state(8)
        self.play_any_sound_containing('_aggressive', True, True)

    def berserk_go_away(self) -> None:                    # 0x100060944
        from .brick_manager import BrickManager
        self.set_state(-1)
        self._life = 0.0
        if self.sound is not None:
            self.sound.stop()
        BrickManager.shared().sound_or_enemy_with_name_was_deactivated(self.name)

    def stop_after_player_was_killed(self) -> None:       # 0x100060a58
        if self._state == 4:
            log.info('%s Already attacking', self.name)
            return
        self.stop_all_sounds()
        self.set_state(-1)
        self.speed = 0.0

    # --- damage ----------------------------------------------------------------------------------
    def hit_by_weapon(self, weapon) -> None:              # 0x100060b30
        from .brick_manager import BrickManager
        from .weapon import MeleeWeapon
        from .weapon_manager import WeaponManager
        if BrickManager.shared().player_is_dead:
            return
        if self._state == 6:
            from ..platform.haptics import Haptics        # PORT ADDITION: the shield takes it: a knock
            Haptics.shared().blocked()
            snd = self.voice_of(self.playlist.any_sound_containing('shieldimpact')) if self.playlist else None
            if snd is not None:
                snd.set_planar((self.position[0], self.position[1], 0.0))
                snd.set_spatialized(True)
                snd.set_gain(17.5)
                snd.play(False)
            return
        dmg = weapon.damages
        if weapon.dispersal < 99:
            fixed = dmg * (weapon.dispersal / 100.0)
            dmg = fixed + (1 - self.squared_distance / (weapon.range * weapon.range)) * (dmg - fixed)
        if self.next_shot_will_be_critical:
            dmg = dmg * weapon.critical_multiplier
        elif self.next_shot_will_be_precise:
            dmg = dmg * 1.3
        mods = GameModifiers.shared()
        if WeaponManager.shared().is_melee_for_weapon_with_name(weapon.name):
            mod = mods.melee_damages_modifier()
        else:
            mod = mods.gun_damages_modifier()
        lost = dmg * mod
        self.set_life(self._life - lost)
        from ..platform.haptics import Haptics            # PORT ADDITION: felt as hard as it hurt
        Haptics.shared().hit(lost, isinstance(weapon, MeleeWeapon))
        log.debug('[%s] life : %f (lost %f)', self.name, self._life, lost)
        self.play_impact_and_hit_sound_for_damages(lost, isinstance(weapon, MeleeWeapon))
        if self.dodge_dictionary is not None and self._life > 0.0:
            self.dodge()
            return
        if self.berserk_dictionary is not None and self._life > 0.0:
            self.transition_to_berserk()

    def hit_by_projectile(self, projectile) -> None:      # 0x100061098
        from .brick_manager import BrickManager
        if BrickManager.shared().player_is_dead:
            return
        w = projectile.weapon
        self.hit_by_explosion(projectile.position, w.damages * GameModifiers.shared().gun_damages_modifier(),
                              w.dispersal, projectile.explosion_radius, None)

    def hit_by_explosion(self, epicentre, damages: float, dispersal: float, radius: float,
                         powerup_name) -> None:           # 0x100061284
        from .brick_manager import BrickManager
        if BrickManager.shared().player_is_dead:
            return
        dmg = damages
        if dispersal < 99:
            ex = epicentre[0] - self.position[0]
            ey = epicentre[1] - self.position[1]
            d2 = ex * ex + ey * ey
            falloff = 1 - (d2 / radius) * radius           # QUIRK: radius cancels out
            if falloff < 0.0:
                falloff = 0.0
            fixed = (dispersal / 100.0) * damages
            dmg = fixed + (damages - fixed) * falloff        # 0x1000613a0..0x1000613b0
        self.set_life(self._life - dmg)
        from ..platform.haptics import Haptics            # PORT ADDITION: felt as hard as it hurt
        Haptics.shared().hit(dmg)
        r = crand.random()
        delay = float(r % 50) / 200.0 + 0.2
        RunLoop.main().call_later(delay, lambda d=dmg: self.play_hit_sound_for_damages(d))

    def set_life(self, value: float) -> None:            # 0x100061a00
        value = float(value)
        if self._life > value and self.shield_dictionary is not None:
            self.shield_damages_taken = (self._life - value) + self.shield_damages_taken
        self._life = value
        if value <= 0.0:
            self.die()

    def set_life_to_zero(self) -> None:
        self._life = 0.0

    def felt_death(self) -> None:
        """PORT ADDITION: what this dying is felt as on a controller.  A zombie is a kill; a diamond and a
        power-up container have their own (passerby.py), being a reward rather than a killing."""
        from ..platform.haptics import Haptics
        Haptics.shared().kill()

    def die(self) -> None:                                # 0x100061ac8
        from .ambient import AmbientManager
        from .brick_manager import BrickManager
        from .ingame_stats import InGameStats, notify_stats
        log.debug('[%s] died', self.name)
        bm = BrickManager.shared()
        if bm.player_is_dead:
            return
        self.felt_death()                                # PORT ADDITION: a kill, by whatever did it
        if self.explosion_dictionary is not None:
            self.explode()
            self.set_state(5)
        else:
            self.set_state(999)
        self.speed = 0.0
        if self.sound is not None:
            self.sound.stop()
        if self.ambiant_name:
            AmbientManager.shared().enemy_with_ambiant_name_killed(self.ambiant_name)
            self.ambiant_name = None
        bm.sound_or_enemy_with_name_was_deactivated(self.name)
        if self.name == 'Diamond' and InGameStats.singleton().game_mode == 'CHALLENGE':
            notify_stats('UPDATE_DIAMONDS', 1)

    def explode(self) -> None:                            # 0x100061e6c
        from .brick_manager import BrickManager
        BrickManager.shared().solve_explosion_with_dictionary(self.explosion_dictionary, self.position,
                                                              self.name, False)

    def can_be_shot_at(self) -> bool:                     # 0x100061f68
        if self._life <= 0.0:
            return False
        if self._state == 0 or self._state == 999:
            return False
        return self._state != -1

    def blow_away(self, distance: float) -> None:         # 0x100061fe8
        px, py = self.position
        self.set_position((px - distance * self.orientation[0], py - distance * self.orientation[1]))

    # --- sounds ----------------------------------------------------------------------------------
    def init_sounds(self) -> None:                        # 0x10006223c
        self.playlist_activated = True
        self.playlist = S3DEngine.engine().play_list_with_name(self.sounds_prefix)

    def deactivate(self) -> None:                         # 0x100062320
        self.set_state(-1)
        self._life = 0.0

    def activate_playlist(self) -> None:                  # 0x10006235c
        if self.playlist is not None:
            self.playlist.activate(lambda pl: None)

    def deactivate_playlist(self) -> None:
        if self.playlist is not None:
            self.playlist.deactivate()

    def voice_of(self, shared):
        """DIVERGENCE: this enemy's own copy of a sound its playlist picked (S3DSound.copy).

        The playlist is shared by every enemy of a type and holds one sound per file (-[S3DPlayList each:]
        0x1000ffeb8), so the original's zombies of one type share their sounds, and one zombie silences
        another.  Two walking zombies that pick the same approach loop share it: playing a sound that is
        already playing restarts it without its loop (-[S3DSound play:fadein:] 0x100105eb8), a sound keeps
        one end callback, the last one given (0x100109c7c), and the first zombie to be hit or change step
        stops the sound under the other - which walks on in silence.  And the waves of a run all stay in
        the brick manager's list, so the zombie that killed you before a revive still holds the attack
        sound; the next zombie of its type to kill you plays that same sound, and
        stopAllEnemiesAfterPlayerDeathByEnemyWithName: 0x1000c71b4 sends the old one stopAfterPlayerWasKilled
        0x100060a58, which stops it at once.  A Shield zombie has one attack sound, so its second kill in a
        run was always silent.  Here each enemy plays its own copy of each file, and the choice of file is
        the playlist's, as before."""
        if shared is None:
            return None
        twin = self._voices.get(shared.key)
        if twin is None:
            twin = self._voices[shared.key] = shared.copy()
        elif shared.loaded and not twin.loaded:           # the playlist was unloaded and loaded again
            twin.activate()
        return twin

    #: how many voices one enemy keeps for a sound that can be asked for again before it has finished
    OVERLAPPING_VOICES = 3

    def overlapping_voice_of(self, shared):
        """DIVERGENCE: a voice for a sound that comes again before the last one has finished - the impact
        of one bullet after another, and the impacts of two zombies hit together.

        The impacts come from one playlist for the whole game ('impact', loaded by the brick manager), so in
        the original every zombie plays them through the same S3DSound: the second hit restarts the first,
        wherever it was - a burst from the Micro SMG is one thud, and a zombie hit while another is being
        hit silences it.  Here each enemy keeps a few voices of its own for such a sound and takes one that
        is not playing, so the hits lie over each other and each is heard from its own zombie.  With all of
        them busy the oldest gives way, which is what the original did every time."""
        if shared is None:
            return None
        voices = self._overlapping.setdefault(shared.key, [])
        for voice in voices:
            if shared.loaded and not voice.loaded:        # the playlist was unloaded and loaded again
                voice.activate()
            if not voice.playing:
                return voice
        if len(voices) < self.OVERLAPPING_VOICES:
            voices.append(shared.copy())
            return voices[-1]
        return voices[0]

    def play_any_sound_containing(self, text: str, looping: bool = True, spatialized: bool = True) -> float:
        """-[ADEnemy playAnySoundContaining:looping:spatialized:] 0x100062420 (1-arg form 0x100062d90)."""
        if self.sound is not None:
            self.sound.stop()
        if self.destroyed:
            return 0.0
        pl = self.playlist
        if pl is None:
            self.sound = None
            return 0.0
        count = len(pl.sounds_matching(lambda k: text in k))
        old_key = self.sound.key if self.sound is not None else None
        if count == 1 or not looping:
            self.sound = self.voice_of(pl.any_sound_containing(text))
        else:
            self.sound = self.voice_of(pl.any_sound_containing(text))
            if self.sound is not None:
                while self.sound.key == old_key:
                    self.sound = self.voice_of(pl.any_sound_containing(text))
                log.debug('Loop from %s to %s', old_key, self.sound.key)

                def on_end(_s, text=text, spatialized=spatialized):
                    if not self.destroyed:
                        RunLoop.main().call_soon(
                            lambda: self.play_any_sound_containing(text, True, spatialized))
                self.sound.add_3d_sound_end_callback(on_end)
            else:
                log.info('NO SOUND in %s CONTAINS %s', pl.name, text)
        if self.sound is None:
            log.info('NO SOUND in %s CONTAINS %s', pl.name, text)
            return 0.0
        if spatialized:
            self.sound.set_spatialized(True)
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
            self.sound.set_gain(3.5)
            self.set_reverb_and_wet_balance_on_sound(self.sound)
        else:
            self.sound.set_spatialized(False)
            self.sound.set_gain(0.5)
        self.sound.play(looping)
        return self.sound.duration

    def play_impact_and_hit_sound_for_damages(self, damages: float, melee: bool) -> None:   # 0x10006150c
        if not melee:
            snd = None
            if self.use_own_impact_sounds:
                snd = (self.overlapping_voice_of(self.playlist.any_sound_containing('impact_'))
                       if self.playlist else None)
            else:
                impact = S3DEngine.engine().play_list_with_name('impact')
                if impact is not None:
                    # this playlist is the whole game's, so these are per-enemy voices (see there)
                    if self.multi_hit_factor >= 2:
                        snd = self.overlapping_voice_of(
                            impact.any_sound_containing(f'impactmulti_{self.multi_hit_factor}'))
                    elif self.multi_hit_factor in (0, 1):
                        if self._life > 0.0:
                            snd = self.overlapping_voice_of(impact.any_sound_containing('impact_'))
                        else:
                            snd = self.overlapping_voice_of(impact.any_sound_containing('KillConfirm_'))
            if snd is not None:
                snd.set_planar((self.position[0], self.position[1], 0.0))
                snd.set_spatialized(True)
                snd.set_gain(math.sqrt(self.position[0] ** 2 + self.position[1] ** 2) / 10 * 5)
                snd.play(False)
        delay = 0.05 if melee else 0.3
        if self.multi_hit_factor == -1:
            delay = float(crand.rand() % 100) / 500.0
        RunLoop.main().call_later(delay, lambda: self.play_hit_sound_for_damages(damages))

    def play_hit_sound_for_damages(self, damages: float) -> None:   # 0x100062db8
        if self.destroyed:
            return
        if self._life <= 0.0:
            if self.explosion_dictionary is not None:
                if not (self.explosion_sound is not None and self.explosion_sound.playing):
                    self.explosion_sound = (self.voice_of(self.playlist.any_sound_containing('explosion'))
                                            if self.playlist else None)
                    if self.explosion_sound is not None:
                        self.explosion_sound.set_planar((self.position[0], self.position[1], 0.0))
                        self.explosion_sound.set_spatialized(True)
                        self.explosion_sound.set_gain(15.0)
                        self.explosion_sound.play(False)
            self.play_death_sound()
            return
        if self.pain_sound is not None and self.pain_sound.playing:
            return
        shield_down = False
        if self._state == 2 and self.shield_dictionary is not None and \
                self.shield_damages_taken > _f(self.shield_dictionary, 'damagesBeforeShield'):
            name = '_shielddown_'
            shield_down = True
        elif self._state == 6:
            return
        else:
            name = '_hit_'
        pl = self.playlist
        self.pain_sound = self.voice_of(pl.any_sound_containing(name)) if pl else None
        if self.pain_sound is None and pl is not None:
            self.pain_sound = self.voice_of(pl.any_sound_containing('_hit_'))
        if self.pain_sound is None:
            return
        self.pain_sound.set_gain(5.0)
        stopped_loop = False
        if self.sound is not None and ('_approach' in self.sound.key or '_aggressive' in self.sound.key):
            self.sound.stop()
            self.sound = None
            stopped_loop = True

        def on_end(_s, shield_down=shield_down):
            if shield_down:
                self.protect()
            if stopped_loop:
                self.walk_or_agressive()
        self.pain_sound.add_3d_sound_end_callback(on_end)
        self.pain_sound.set_planar((self.position[0], self.position[1], 0.0))
        self.pain_sound.set_spatialized(True)
        self.pain_sound.play(False)

    def play_death_sound(self) -> None:                   # 0x100063688
        ps = self.pain_sound
        if ps is not None and ps.playing:
            if '_death' in ps.key or '_die' in ps.key:
                log.debug('Already playing death sound : %s', ps.key)
                return
            ps.stop()
        pl = self.playlist
        if pl is None:
            self.pain_sound = None
            return
        self.pain_sound = None                            # both of the original's branches set it anew
        if self.next_shot_will_be_critical:
            self.pain_sound = self.voice_of(pl.any_sound_containing('death_crit'))
            if self.pain_sound is None:
                self.pain_sound = self.voice_of(pl.any_sound_containing('_diecrit_'))
        # DIVERGENCE: the original (0x1000637f0) looks for the critical death only on a critical kill, and a
        # type without one - Shield, WeakZombieD, ZombieC, the cars, cows, the diamond, the machine and the
        # power-up container - dies in silence, having just stopped its own hit sound above: a melee kill
        # on a Shield (melee weapons are critical 5-25% of the time) cut the hit off and played nothing.
        # A critical kill with no critical sound of its own falls back on the ordinary death.
        if self.pain_sound is None:
            self.pain_sound = self.voice_of(pl.any_sound_containing('_death_'))
            if self.pain_sound is None:
                self.pain_sound = self.voice_of(pl.any_sound_containing('_die_'))
        if self.pain_sound is None:
            return
        self.pain_sound.set_gain(4.0)
        self.pain_sound.set_planar((self.position[0], self.position[1], 0.0))
        self.pain_sound.set_spatialized(True)
        self.pain_sound.play(False)

    @staticmethod
    def set_reverb_and_wet_balance_on_sound(sound) -> None:   # 0x100063a48
        sound.set_send_to_reverb(True)
        sound.set_wet_gain(1.0)

    def stop_all_sounds(self) -> None:                    # 0x100063ab0
        if self.sound is not None:
            self.sound.stop()
        if self.pain_sound is not None:
            self.pain_sound.stop()

    def destroy_enemy(self) -> None:                      # 0x100063b74
        from .ambient import AmbientManager
        self.stop_all_sounds()
        self.speed = 0.0
        self.destroyed = True
        if self.ambiant_name:
            AmbientManager.shared().enemy_with_ambiant_name_killed(self.ambiant_name)
            self.ambiant_name = None

    def pause(self) -> None:                              # 0x100063c64
        self.sound_was_playing = bool(self.sound is not None and self.sound.playing)
        if self.sound is not None:
            self.sound.pause()
        if self.pain_sound is not None:
            self.pain_sound.stop()

    def resume(self) -> None:                             # 0x100063d34
        if self.sound_was_playing and self.sound is not None:
            self.sound.play()
