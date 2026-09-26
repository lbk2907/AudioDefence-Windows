"""Non-hostile targets: ADPasserBy (cows...), ADCarAlarm, ADJukeBox, ADMachine, ADDiamondDropper, ADPowerUpContainer.

All are ADEnemy subclasses; each method is ported against its listing (address in the comment).
Private state numbers used by the subclasses: 201 passing by, 301/302 jukebox playing/paused,
401 car alarm, 501/502 machine loop/sleeping, 101/102 diamond glowing/fading, 601 power-up beeping.
"""
from __future__ import annotations

import logging
import math

from ..platform import crand
from ..platform.tracker import Tracker
from .enemy import PI_D, Enemy

log = logging.getLogger('passerby')


def _fdiv(a: float, b: float) -> float:
    """IEEE division (fdiv never traps): x/0 is +-inf, 0/0 is nan."""
    if b != 0.0:
        return a / b
    if a == 0.0 or math.isnan(a):
        return math.nan
    return math.copysign(math.inf, a) * math.copysign(1.0, b)


def _duration(sound) -> float:
    """[sound duration] - a message to nil returns 0."""
    return sound.duration if sound is not None else 0.0


class PasserBy(Enemy):
    def update(self, dt: float) -> None:                  # -[ADPasserBy update:] 0x10000b770
        st = self._state
        if st > 998:
            if st == 999 and self.time_in_state > 0.1 and self.time_in_state > _duration(self.sound):
                self.deactivate_playlist()
                self.set_state(-1)
        elif st == 0:
            if self.time_in_state > self.spawn_time:
                self.spawn()
        elif st == 1:
            if self.spawn_sound_duration == 0.0:
                self.spawn()
            elif self.time_in_state > self.spawn_sound_duration:
                self.pass_by()
        elif st == 201:
            ox, oy = self.orientation                     # getOrientation
            px, py = self.position
            self.set_position((px + dt * (ox * self.speed), py + dt * (oy * self.speed)))
            px, py = self.position
            n = math.sqrt(px * px + py * py)
            self.angle_from_player = math.atan2(_fdiv(py, n), _fdiv(px, n))
            if self.squared_distance > 225.0:
                self.deactivate_playlist()
                self.set_state(-1)
        if self.sound is not None:
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
        self.time_in_state = self.time_in_state + dt

    def set_position_from_dictionary(self, d: dict) -> None:   # 0x10000bb7c
        from ..platform.defaults import ns_float_value
        angle = ns_float_value(d.get('spawn_angle'))
        dist = ns_float_value(d.get('spawn_distance'))
        a = (angle * PI_D) / 180.0
        self.set_position((dist * math.sin(a), dist * math.cos(a)))
        orientation = d.get('orientation')
        if orientation is None:
            self.update_orientation()
            return
        text = str(orientation).upper()
        if 'N' in text:                                   # 0x10000bd9c
            y = 1.0
        else:
            y = -1.0 if 'S' in text else 0.0              # 0x10000bd7c
        if 'E' in text:                                   # 0x10000be74
            x = 1.0
        else:
            x = -1.0 if 'W' in text else 0.0              # 0x10000be6c
        self.set_orientation_with(x, y)

    def set_random_position_at_distance(self, distance: int) -> None:   # 0x10000bf30
        deg = crand.c_mod(crand.rand(), 360)
        a = (float(deg) * PI_D) / 180.0
        self.set_position((float(distance) * math.sin(a), float(distance) * math.cos(a)))
        self.update_orientation()

    def set_random_position(self) -> None:                # 0x10000bfdc
        sign = ((crand.rand() << 1) & 2) - 1              # first rand(): side
        y = (crand.c_mod(crand.rand(), 4) + 4) * sign     # second rand(): 4..7
        self.set_position((8.0, float(y)))
        self.set_orientation_with(-1.0, 0.0)

    def pass_by(self) -> None:                            # 0x10000c05c
        self.set_state(201)
        self.play_any_sound_containing('_moving_')

    def get_type(self) -> int:                            # 0x10000c0a4
        return 1


class CarAlarm(PasserBy):
    def __init__(self, name: str):                        # -[ADCarAlarm initWithName:] 0x1000ae8b8
        super().__init__(name)
        self.use_own_impact_sounds = True

    def update(self, dt: float) -> None:                  # 0x1000ae968 (does not call super)
        st = self._state
        if st == 5:
            if self.time_in_state > 3.0:
                self.set_state(-1)
        elif st == 1:
            if self.spawn_sound_duration == 0.0:
                self.spawn()
            elif self.time_in_state > self.spawn_sound_duration:
                self.start_alarm()
        elif st == 0:
            if self.time_in_state > self.spawn_time:
                self.spawn()
        self.time_in_state = self.time_in_state + dt

    def start_alarm(self) -> None:                        # 0x1000aeab8
        self.sound = self.playlist.any_sound_containing('alarm') if self.playlist is not None else None
        if self.sound is not None:
            self.sound.set_spatialized(True)
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
            self.sound.play(True)
            self.sound.set_gain(2.0)
        self.set_state(401)

    def die(self) -> None:                                # 0x1000aecac
        super().die()
        if self.sound is not None:
            self.sound.set_gain(4.0)


class JukeBox(PasserBy):
    def __init__(self, name: str):                        # -[ADJukeBox initWithName:] 0x100065f4c
        from ..platform.defaults import ns_float_value
        from .brick_manager import BrickManager
        super().__init__(name)
        d = BrickManager.dictionary_for_enemy_name(name.split(' ')[0])
        self.pause_time = ns_float_value(d.get('pauseTime') if d is not None else None)

    def update(self, dt: float) -> None:                  # 0x100066148 (does not call super)
        st = self._state
        if st == 302:
            if self.time_in_state > self.pause_time:
                self.end_of_pause_state()
        elif st == 0:
            if self.time_in_state > self.spawn_time:
                self.spawn()
        self.time_in_state = self.time_in_state + dt

    def spawn(self) -> None:                              # 0x10006623c (does not call super)
        self.play_random_music()
        self.set_state(301)

    def play_random_music(self) -> None:                  # 0x10006627c
        pl = self.playlist
        self.sound = pl.any_sound_containing('jukebox_music_') if pl is not None else None
        if self.sound is not None:
            self.sound.set_spatialized(True)
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
            self.sound.play(True)
            self.sound.set_gain(6.0)
        resume = pl.any_sound_containing('jukebox_resume_') if pl is not None else None
        if resume is not None:
            resume.set_spatialized(True)
            resume.set_planar((self.position[0], self.position[1], 0.0))
            resume.play(False)
            resume.set_gain(6.0)

    def hit_by_weapon(self, weapon) -> None:              # 0x100066550 (no damage, no super)
        if self.sound is not None:
            self.sound.stop()
        self.sound = self.playlist.any_sound_containing('jukebox_hit_') if self.playlist is not None else None
        if self.sound is not None:
            self.sound.set_spatialized(True)
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
            self.sound.play(False)
            self.sound.set_gain(6.0)
        self.set_state(302)

    def hit_by_explosion(self, epicentre, damages: float, dispersal: float, radius: float,
                         powerup_name) -> None:
        """DIVERGENCE: the jukebox overrides the *four*-argument explosion selector at 0x100066784 and
        pauses its music there, but every sender - solveExplosionWithDictionary: 0x1000c5c40 and
        hitByProjectile: 0x100061098 - uses the five-argument ...powerupname: form, so the override is
        never reached and ADEnemy's implementation runs instead.  Blowing up a jukebox damaged it and left
        it playing.  The five-argument form is overridden here, so the code that was written for it runs."""
        self.hit_by_explosion_without_powerup_name(epicentre, damages, dispersal, radius)

    def hit_by_explosion_without_powerup_name(self, epicentre, damages: float, dispersal: float,
                                              radius: float) -> None:
        """-[ADJukeBox hitByExplosionAtPosition:withDamages:dispersal:radius:] 0x100066784."""
        super().hit_by_explosion(epicentre, damages, dispersal, radius, None)
        if self.sound is not None:
            self.sound.pause()
        self.set_state(302)

    def can_be_shot_at(self) -> bool:                     # 0x100066834 (ignores life)
        st = self._state
        if st == 302 or st == 0 or st == 999:
            return False
        return st != -1

    def end_of_pause_state(self) -> None:                 # 0x1000668ac
        self.play_random_music()
        self.set_state(301)

    def set_random_position(self) -> None:                # 0x1000668ec
        self.set_position_from_dictionary({'spawn_angle': crand.c_mod(crand.rand(), 360),
                                           'spawn_distance': 7})


class Machine(PasserBy):
    def __init__(self, name: str):                        # -[ADMachine initWithName:] 0x10004f74c
        super().__init__(name)
        self.use_own_impact_sounds = True
        self.sleep_time = 0.0

    def update(self, dt: float) -> None:                  # 0x10004f7fc (does not call super)
        st = self._state
        if st > 501:
            if st == 502 and self.time_in_state > self.sleep_time:
                self.set_life(self.max_life)
                self.set_state(1)
        elif st == 0:
            if self.time_in_state > self.spawn_time:
                self.spawn()
        elif st == 1:
            if self.spawn_sound_duration == 0.0:
                self.spawn()
            elif self.time_in_state > self.spawn_sound_duration:
                self.start_loop()
        elif st == 5:
            if self.time_in_state > 3.0:
                self.sleep_time = float(crand.c_mod(crand.rand(), 20) + 35)
                self.set_state(502)
        self.time_in_state = self.time_in_state + dt

    def start_loop(self) -> None:                         # 0x10004f9fc
        self.play_any_sound_containing('loop')
        self.set_state(501)

    def die(self) -> None:                                # 0x10004fa44
        super().die()
        if self.sound is not None:
            self.sound.set_gain(2.0)


class DiamondDropper(Enemy):
    def spawn(self) -> None:                              # -[ADDiamondDropper spawn] 0x10007e2bc
        super().spawn()
        Tracker.shared().diamond_appeared()

    def update(self, dt: float) -> None:                  # 0x10007e350 (does not call super)
        from .brick_manager import BrickManager
        st = self._state
        if st > 998:
            if st == 999 and self.time_in_state > 0.1 and self.time_in_state > _duration(self.sound):
                self.set_state(-1)                        # loc_10007e65c
        elif st > 100:
            if st == 101:
                if self.time_in_state > 0.1 and self.time_in_state > 7.5:
                    self.set_state(102)
            elif st == 102:
                snd = self.sound
                if self.time_in_state < 2.0:
                    if snd is not None:
                        snd.set_gain((self.time_in_state * 3.5) * 0.5)
                else:
                    if snd is not None:
                        snd.stop()
                    self.set_life_to_zero()
                    Tracker.shared().diamond_disappered()
                    BrickManager.shared().sound_or_enemy_with_name_was_deactivated(self.name)
                    self.set_state(-1)
        elif st == 0:
            if self.time_in_state > self.spawn_time:
                self.spawn()
        elif st == 1:
            if self.spawn_sound_duration == 0.0:
                self.spawn()
            elif self.time_in_state > self.spawn_sound_duration:
                self.glow()
        if self.sound is not None:
            self.sound.set_planar((self.position[0], self.position[1], 0.0))
        self.time_in_state = self.time_in_state + dt

    def felt_death(self) -> None:
        """PORT ADDITION: two bright ticks, not a kill's thump: a diamond is money, not a zombie."""
        from ..platform.haptics import Haptics
        Haptics.shared().diamond()

    def glow(self) -> None:                               # 0x10007e7b8
        self.set_state(101)
        self.play_any_sound_containing('_glow_')

    def die(self) -> None:                                # 0x10007e800
        from .ingame_stats import notify_stats
        from .modifiers import GameModifiers
        super().die()
        # PORT ADDITION: Lucky Night pays what a full moon pays, on any night of the month
        mods = GameModifiers.shared()
        notify_stats('UPDATE_DIAMONDS', 2 if (mods.fullMoon or mods.luckyNight) else 1)
        Tracker.shared().diamond_acquired()
        # QUIRK: the original then dispatch_after(5 s) a block whose captured receiver is nil
        # (str xzr at 0x10007e950), i.e. [nil deactivatePlaylist] - nothing happens, so nothing is scheduled.

    def init_sounds(self) -> None:                        # 0x10007e9a8
        super().init_sounds()
        super().activate_playlist()


class PowerUpContainer(PasserBy):
    def __init__(self, name: str):
        super().__init__(name)
        self.power_up_type = 0

    def update(self, dt: float) -> None:                  # 0x100069880 (does not call super)
        st = self._state
        if st > 600:
            if st == 601:
                if self.time_in_state > 15.0:
                    self.remove_power_up()
            elif st == 999:
                if self.time_in_state > 0.1 and self.time_in_state > _duration(self.sound):
                    self.set_state(-1)
        elif st == 0:
            if self.time_in_state > self.spawn_time:
                self.spawn()
        elif st == 1:
            if self.spawn_sound_duration == 0.0:
                self.spawn()
            elif self.time_in_state > self.spawn_sound_duration:
                self.start_beeping()
        self.time_in_state = self.time_in_state + dt

    def spawn(self) -> None:                              # 0x100069a90
        from .weapon_manager import WeaponManager
        super().spawn()
        kind = self.power_up_type
        wm = WeaponManager.shared()
        if kind != 0:
            wm.init_power_up(self.power_up_type)
        else:
            wm.init_random_power_up()

    def felt_death(self) -> None:
        """PORT ADDITION: the crate cracking open, with the announcement and the power-up itself to come
        (powerups.py, ADPowerUp activate)."""
        from ..platform.haptics import Haptics
        Haptics.shared().power_up_container()

    def die(self) -> None:                                # 0x100069b80
        from .weapon_manager import WeaponManager
        super().die()
        WeaponManager.shared().use_power_up()

    def can_be_shot_at(self) -> bool:                     # 0x100069c14
        if self._state == 1:
            return False
        return super().can_be_shot_at()

    def start_beeping(self) -> None:                      # 0x100069c7c
        self.set_state(601)
        self.play_any_sound_containing('_alerting_')

    def remove_power_up(self) -> None:                    # 0x100069cc4
        self.set_state(-1)
        self.set_life_to_zero()
        if self.sound is not None:
            self.sound.stop()
        Tracker.shared().power_up_missed()

    def get_type(self) -> int:                            # 0x100069d90 -> [super getType] (ADPasserBy: 1)
        return super().get_type()
