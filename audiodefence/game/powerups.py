"""ADPowerUpManager (container pop cooldown) and the power-ups: ADPowerUp, Minigun, Fireworks, Tornado, Tesla.

ADAirStrikePowerUp and ADSlowMotionPowerUp exist in the binary but are never allocated
(ADWeaponManager only creates types 1..4), so they are not ported.
"""
from __future__ import annotations

import logging
import math

from ..platform import crand
from ..platform.defaults import ns_float_value, ns_int_value
from ..platform.runloop import RunLoop
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from .modifiers import GameModifiers

log = logging.getLogger('powerups')

PI_D = 3.14159265


def _level_dictionary(name: str) -> dict | None:
    """The level lookup shared by every preload/use:
    level = inventory level; with betterPowerUps, +1 only when "level_<level+1>" exists.

    A fifth level exists for four of the power-ups (`additions.fifth_power_up_level`), so a player who
    has bought every upgrade gets one from Powered Power Ups where the original gave nothing.  This
    method is the original's, untouched: the level is in the data it reads."""
    from .inventory import Inventory
    from .weapon_manager import WeaponManager
    d = WeaponManager.shared().dictionary_for_powerup_with_name(name) or {}
    level = Inventory.shared().level_for_power_up(name)
    bonus = 0
    if GameModifiers.shared().betterPowerUps:
        bonus = 1 if d.get(f'level_{level + 1}') is not None else 0
    return d.get(f'level_{bonus + level}')


def _get(d, key):
    return d.get(key) if isinstance(d, dict) else None


def felt_when_it_starts(power_up) -> None:
    """PORT ADDITION: the swell is felt from the moment the power-up's own sound starts (user request).

    A sound that is not on the card when `play:` is called starts a moment later (S3DSound.play_when_loaded
    -> activate -> the decode), and a launch sound is one of those: it is loaded by being played.  So this
    waits a pass at a time for the sound to be playing rather than shaking the pad while the arena is still
    quiet.  It gives up after a second of passes and is felt anyway, a swell late being better than none."""
    from ..platform.haptics import Haptics
    sound = power_up.felt_sound()
    seconds = power_up.felt_start()
    if sound is None:
        Haptics.shared().power_up_started(seconds)
        return
    passes = [60]

    def when_playing():
        if passes[0] <= 0 or sound.playing:
            Haptics.shared().power_up_started(seconds)
            return
        passes[0] -= 1
        RunLoop.main().call_soon(when_playing)

    when_playing()


def _explosion_sign(r: int) -> int:
    """(2 & ~(rand() << 1)) - 1: +1 for an even rand(), -1 for an odd one."""
    return (2 & ~(r << 1)) - 1


class PowerUpManager:
    def __init__(self):                                   # -[ADPowerUpManager init] 0x10004b524
        self.powerup_cool_down = 0.0
        self.reset_power_up_cooldown()

    def update(self, dt: float) -> None:                  # 0x10004b5a4
        from .brick_manager import BrickManager
        if not BrickManager.shared().player_is_dead:
            self.powerup_cool_down = self.powerup_cool_down - dt

    def reset_power_up_cooldown(self) -> None:            # 0x10004b640
        from .inventory import Inventory
        from .weapon_manager import WeaponManager
        d = WeaponManager.shared().dictionary_for_powerup_with_name('frequency')
        level = Inventory.shared().level_for_power_up('frequency')
        self.powerup_cool_down = float(ns_int_value(_get(_get(d, f'level_{level}'), 'cooldownTime')))
        if GameModifiers.shared().morePowerUps:
            self.powerup_cool_down = self.powerup_cool_down + -10.0

    def try_to_pop_power_up(self) -> None:                # 0x10004b868
        if self.powerup_cool_down > 0.0:
            log.info("Cooldown has %f seconds left, can't pop powerup", self.powerup_cool_down)
            return
        self.pop_power_up_with_type(0)

    def pop_power_up_with_type(self, kind: int) -> None:  # 0x10004b8c4
        from .brick_manager import BrickManager
        from .passerby import PowerUpContainer
        c = PowerUpContainer('PowerUpContainer')
        c.power_up_type = kind
        c.activate_playlist()
        c.set_random_position_at_distance(5)
        c.tag = BrickManager.shared().passers_by_count() + 200000
        c.set_state(0)
        c.spawn_time = 2.0
        BrickManager.shared().add_passer_by(c)
        self.reset_power_up_cooldown()


class PowerUp:
    NAMES = {1: 'MINIGUN', 2: 'FIREWORKS', 3: 'TORNADO', 4: 'TESLA'}

    def __init__(self, kind: int):                        # -[ADPowerUp initWithType:] 0x10001d8c0
        self.playlist = None
        self.name = None
        self.type = kind
        self.paused_sounds: list = []                     # what `pause` held, to be let go again
        self.held = False
        if kind in self.NAMES:
            self.name = self.NAMES[kind]

    def pause(self) -> None:
        """Hold whatever this power-up is playing while the game is paused.

        DIVERGENCE (user request): `pauseGame` 0x10005b5fc stops the timers and pauses the bricks and the
        ambience, and says nothing about a power-up in hand - as it says nothing about the weapon
        (`Weapon.pause`).  The Minigun's fire loops, so it went on firing through the pause menu and only
        stopped when the game came back and its time ran out.
        """
        if self.held:                                     # already held: a second pause must not forget
            return                                        # what the first one is holding
        self.held = True
        self.paused_sounds = []
        if self.playlist is None:
            return

        def hold(sound):
            if sound is not None and sound.playing:
                sound.pause()
                self.paused_sounds.append(sound)
            return False

        self.playlist.each(hold)

    def resume(self) -> None:
        self.held = False
        for sound in self.paused_sounds:
            sound.resume()
        self.paused_sounds = []

    def preload(self) -> None:                            # 0x10001da24
        pass

    def use(self) -> None:                                # 0x10001da28
        Tracker.shared().power_up_used()

    def update(self, dt: float) -> None:                  # 0x10001da8c
        pass

    def clean(self) -> None:                              # 0x10001da90
        Tracker.shared().set_value_for_dimension(0, 'PowerUp name', 0, 0)

    def activate(self) -> None:                           # 0x10001db08
        from .parameters import GameParameters
        announce = self.playlist.any_sound_containing('announce') if self.playlist is not None else None
        if announce is None:
            return                                        # messages to nil: use is never reached
        def started(_s):                                  # activate:_block_invoke 0x10001dc6c
            self.use()
            felt_when_it_starts(self)                     # PORT ADDITION: felt with the sound it starts

        announce.add_3d_sound_end_callback(started)
        if not GameParameters.shared().last_announcer_value():
            announce.set_gain(0.0)
        announce.play(False)

    #: PORT ADDITION: how long the power-up starting is felt for when it has nothing of its own to go by,
    #: and the most it is felt for however long its start sound runs.  The Tornado's launch is 5.7 seconds
    #: and the Fireworks' 5.6 - the whole thing coming in, not a start - and a rumble that long stops being
    #: something starting and becomes something wrong with the pad.  The Tesla's deploy is 2.74, so the cap
    #: leaves room for it: it, the Minigun's spin-up (1.5) and everything shorter are felt whole.
    FELT_START = 0.6
    FELT_START_MAX = 3.0

    def felt_start(self) -> float:
        """PORT ADDITION: the seconds the start is felt for - as long as the sound that starts it, so what
        is felt and what is heard end together (user request)."""
        return self.FELT_START

    def felt_sound(self):
        """PORT ADDITION: the sound the swell starts with - the deploy after the announcement.  None where
        the power-up has nothing of its own, and then it is felt as soon as it is used."""
        return None

    def _launch_seconds(self, key: str) -> float:
        """PORT ADDITION: how long a launch sound runs, or FELT_START if it cannot be known yet.

        A sound only has a duration once it is on the card, and a launch sound is loaded when it is played,
        which is a moment after this is asked.  Its file is decoded already, though - activating the
        playlist prewarms it - so the length comes from there when the sound itself has none.  A file that
        is somehow not decoded yet is left alone rather than decoded here, where the game would wait."""
        sound = self.playlist.sound(key) if self.playlist is not None else None
        if sound is None:
            return self.FELT_START
        seconds = sound.duration
        if seconds <= 0.0:
            from ..s3d import decoder
            if decoder.is_cached(sound.path):
                data, rate = decoder.decode(sound.path)
                seconds = len(data) / float(rate) if rate else 0.0
        return min(seconds, self.FELT_START_MAX) if seconds > 0.0 else self.FELT_START

    def stop_after_player_was_killed(self) -> None:
        """PORT ADDITION: the player is dead, so the power-up stops where it is (user request).

        The original leaves it running: the Minigun goes on firing into the death overlay, and the wind and
        the coil go on with it.  Its gun was heard for ten seconds either way, being played once through;
        now that the port loops it for as long as the gun fires, it would be heard until the run is cleaned
        up - which is a good while, with the revive screen in between.  The enemies, the diamonds and the
        passers-by are all stopped on death (`stopAllEnemiesAfterPlayerDeathByEnemyWithName:`); this is the
        power-up joining them.
        """
        if not getattr(self, 'active', False):
            return
        self.active = False
        self.clean()

    def _clean_with_kill_report(self) -> None:
        """Shared tail of the Minigun/Fireworks/Tesla clean: report and reset enemyKillsWithPowerup."""
        from .ingame_stats import InGameStats
        stats = InGameStats.singleton()
        Tracker.shared().number_of_enemy_kills_by_power_up(stats.enemy_kills_with_powerup, self.name)
        stats.enemy_kills_with_powerup = 0


class MinigunPowerUp(PowerUp):
    def __init__(self, kind: int):
        super().__init__(kind)
        self.time_since_activation = 0.0
        self.active = False
        self.next_bullet_time = 0.0
        self.minigun_weapon = None
        self.minigun_duration = 0.0
        self.loop_sound = None
        self.felt_next = 0.0                              # PORT ADDITION: when the gun is next felt

    #: PORT ADDITION: the Minigun has no launch sound; it spins up instead, and update: holds its fire
    #: for this long (the 1.5 there), which is what its starting sounds like.
    FELT_START = 1.5

    def preload(self) -> None:                            # 0x1000b242c
        from .weapon import Weapon
        from .weapon_manager import WeaponManager
        self.playlist = S3DEngine.engine().play_list_with_name('minigun')
        if self.playlist is not None:
            self.playlist.activate()
        d = WeaponManager.shared().dictionary_for_powerup_with_name('minigun') or {}
        self.minigun_weapon = Weapon(d.get('weaponDictionary'))
        self.name = d.get('name')
        self.minigun_duration = float(ns_int_value(_get(_level_dictionary('minigun'), 'duration')))

    def use(self) -> None:                                # 0x1000b2850 (no [super use])
        self.loop_sound = self.playlist.any_sound_containing('minigun_fire') if self.playlist is not None else None
        if self.loop_sound is not None:
            # DIVERGENCE: `play:0` - the gun is fired once through and not looped, and its recording is 10
            # seconds (minigun_fire_a 10.03, _b 9.98) against a duration of 5, 7.5, 10 or 12.5 by upgrade
            # (Weapons.plist, PowerUps, Minigun).  Fully upgraded the gun therefore falls silent two and a
            # half seconds before it stops firing - the bullets still land, the gun is not heard - and the
            # tail comes out of that silence.  It loops here (user request); `update:` stops it at the end
            # as it always did, so nothing else changes, and the recording is gunfire end to end, with no
            # silence at either edge to be heard as a seam.
            self.loop_sound.play(True)
            self.loop_sound.set_gain(0.4)
        self.time_since_activation = 0.0
        self.active = True

    def felt_sound(self):                                 # PORT ADDITION
        return self.loop_sound

    def update(self, dt: float) -> None:                  # 0x1000b2934
        from .brick_manager import BrickManager
        if not self.active:
            return
        self.time_since_activation = self.time_since_activation + dt
        if self.time_since_activation <= 1.5:
            return
        from ..platform.haptics import Haptics            # PORT ADDITION: the gun felt while it fires,
        self.felt_next = self.felt_next - dt              # with the hits it lands felt over it
        if self.felt_next <= 0.0:
            self.felt_next = Haptics.SUSTAIN
            Haptics.shared().minigun_firing()
        self.next_bullet_time = self.next_bullet_time - dt
        if self.next_bullet_time < 0.0:
            self.next_bullet_time = self.minigun_weapon.fire_rate
            BrickManager.shared().shot_with_special_weapon(self.minigun_weapon)
        if self.time_since_activation <= self.minigun_duration or not self.active:
            return
        self.active = False
        loop = self.loop_sound
        RunLoop.main().call_soon(lambda: loop.stop() if loop is not None else None)   # dispatch_after(0, main)
        tail = self.playlist.any_sound_containing('minigun_tail') if self.playlist is not None else None
        if tail is not None:
            tail.play(False)
            tail.set_gain(0.4)
            tail.add_3d_sound_end_callback(lambda _s: self.clean())

    def clean(self) -> None:                              # 0x1000b2ba4 (no [super clean])
        if self.playlist is not None:
            self.playlist.deactivate()
        self._clean_with_kill_report()


class FireworksPowerUp(PowerUp):
    def __init__(self, kind: int):
        super().__init__(kind)
        self.time_since_activation = 0.0
        self.active = False
        self.next_explosion_time = 0.0
        self.dispersal = 0.0
        self.radius = 0.0
        self.damages = 0.0

    def preload(self) -> None:                            # 0x100091770
        self.playlist = S3DEngine.engine().play_list_with_name('fireworks')
        if self.playlist is not None:
            self.playlist.activate()

    def felt_start(self) -> float:                        # PORT ADDITION
        return self._launch_seconds('fireworks_launch')

    def felt_sound(self):                                 # PORT ADDITION
        return self.playlist.sound('fireworks_launch') if self.playlist is not None else None

    def use(self) -> None:                                # 0x100091860
        from .brick_manager import BrickManager
        from .weapon_manager import WeaponManager
        launch = self.playlist.sound('fireworks_launch') if self.playlist is not None else None
        if launch is not None:
            launch.play(False)
        self.radius = 10.0
        d = WeaponManager.shared().dictionary_for_powerup_with_name('fireworks') or {}
        self.name = d.get('name')
        self.damages = float(ns_int_value(_get(_level_dictionary('fireworks'), 'damages')))
        self.dispersal = 50.0
        self.time_since_activation = 0.0
        self.active = True
        self.randomize_next_explosion_time()
        blast = {'radius': self.radius, 'damages': self.damages + self.damages, 'dispersal': self.dispersal}
        BrickManager.shared().solve_explosion_with_dictionary(blast, (0.0, 0.0), 'fireworks', True)
        super().use()

    def update(self, dt: float) -> None:                  # 0x100091e18
        if not self.active:
            return
        self.time_since_activation = self.time_since_activation + dt
        if self.time_since_activation <= 1.0:
            return
        self.next_explosion_time = self.next_explosion_time - dt
        if self.next_explosion_time < 0.0:
            self.randomize_next_explosion_time()
            self.play_random_explosion()
        if self.time_since_activation <= 8.0:
            return
        self.active = False
        self.clean()

    def randomize_next_explosion_time(self) -> None:      # 0x100091ee4
        t1 = float(crand.c_mod(crand.rand(), 100)) / 200.0
        sign = _explosion_sign(crand.rand())
        self.next_explosion_time = t1 * float(sign) + 0.571428571

    def play_random_explosion(self) -> None:              # 0x100091f7c
        from .brick_manager import BrickManager
        snd = self.playlist.any_sound_containing('explode') if self.playlist is not None else None
        if snd is not None:
            snd.set_spatialized(True)
        r_angle = crand.rand()
        r_dist = crand.rand()
        a = (float(crand.c_mod(r_angle, 360)) * PI_D) / 180.0
        dist = float(crand.c_mod(r_dist, 3) + 2)
        if snd is not None:
            snd.set_planar((math.sin(a) * dist, math.cos(a) * dist, 0.0))
            snd.play(False)
        blast = {'radius': self.radius, 'damages': self.damages, 'dispersal': self.dispersal}
        BrickManager.shared().solve_explosion_with_dictionary(blast, (0.0, 0.0), 'fireworks', True)

    def clean(self) -> None:                              # 0x1000922c4
        if self.playlist is not None:
            self.playlist.deactivate()
        self._clean_with_kill_report()


class TornadoPowerUp(PowerUp):
    def __init__(self, kind: int):
        super().__init__(kind)
        self.time_since_activation = 0.0
        self.active = False
        self.blow_distance = 0.0
        self.next_wind_time = 0.0
        self.nb_wind = 0

    def preload(self) -> None:                            # 0x100097624
        self.playlist = S3DEngine.engine().play_list_with_name('tornado')
        if self.playlist is not None:
            self.playlist.activate()

    def felt_start(self) -> float:                        # PORT ADDITION
        return self._launch_seconds('tornado_launch')

    def felt_sound(self):                                 # PORT ADDITION
        return self.playlist.sound('tornado_launch') if self.playlist is not None else None

    def use(self) -> None:                                # 0x100097714
        from .weapon_manager import WeaponManager
        launch = self.playlist.sound('tornado_launch') if self.playlist is not None else None
        if launch is not None:
            launch.set_gain(0.5)
            launch.play(False)
        d = WeaponManager.shared().dictionary_for_powerup_with_name('tornado') or {}
        self.name = d.get('name')
        self.blow_distance = float(ns_int_value(_get(_level_dictionary('tornado'), 'blowDistance')))
        self.time_since_activation = 0.0
        self.active = True
        self.next_wind_time = 0.5                         # 0x3f000000
        super().use()

    def update(self, dt: float) -> None:                  # 0x100097af0
        if not self.active:
            return
        self.next_wind_time = self.next_wind_time - dt
        if self.next_wind_time >= 0.0:
            return
        if self.nb_wind > 3:
            # DIVERGENCE: update: 0x100097af0 cleans the tornado once its four gusts are done but never
            # clears `active`, so every later tick fell through the guard above and cleaned it again for
            # the rest of the game.  The flag is cleared, so the clean-up happens once.
            self.active = False
            self.clean()
            return
        self.randomize_next_wind_time()
        self.play_random_wind()
        self.nb_wind = self.nb_wind + 1

    def randomize_next_wind_time(self) -> None:           # 0x100097b9c
        t1 = float(crand.c_mod(crand.rand(), 100)) / 200.0
        sign = _explosion_sign(crand.rand())
        self.next_wind_time = t1 * float(sign) + 3.0

    def play_random_wind(self) -> None:                   # 0x100097c28
        from .brick_manager import BrickManager
        snd = self.playlist.any_sound_containing('wind') if self.playlist is not None else None
        if snd is not None:
            snd.set_spatialized(True)
        r_angle = crand.rand()
        r_dist = crand.rand()
        if snd is not None:
            snd.set_gain(4.0)
        a = (float(crand.c_mod(r_angle, 360)) * PI_D) / 180.0
        dist = float(crand.c_mod(r_dist, 2) + 1)
        if snd is not None:
            snd.set_planar((dist * math.sin(a), dist * math.cos(a), 0.0))
        BrickManager.shared().blow_enemies_away(self.blow_distance * 0.25)
        if snd is not None:
            snd.play(False)

    def clean(self) -> None:                              # 0x100097e08 (no kill report)
        if self.playlist is not None:
            self.playlist.deactivate()


class TeslaPowerUp(PowerUp):
    def __init__(self, kind: int):
        super().__init__(kind)
        self.max_number_of_kills = 0
        self.active = False
        self.current_kill_count = 0
        self.time_since_last_kill = 0.0
        self.time_between_kills = 0.0

    def preload(self) -> None:                            # 0x1000d7380
        from .weapon_manager import WeaponManager
        self.playlist = S3DEngine.engine().play_list_with_name('tesla_powerup')
        if self.playlist is not None:
            self.playlist.activate()
        d = WeaponManager.shared().dictionary_for_powerup_with_name('tesla') or {}
        self.name = d.get('name')
        self.max_number_of_kills = ns_int_value(_get(_level_dictionary('tesla'), 'kills'))
        self.time_between_kills = ns_float_value(d.get('timeBetweenKills'))   # stored, never read

    def felt_start(self) -> float:                        # PORT ADDITION
        return self._launch_seconds('tesla_launch')

    def felt_sound(self):                                 # PORT ADDITION
        return self.playlist.sound('tesla_launch') if self.playlist is not None else None

    def use(self) -> None:                                # 0x1000d7774
        super().use()
        launch = self.playlist.sound('tesla_launch') if self.playlist is not None else None
        if launch is not None:
            launch.play(False)
        self.active = True
        self.time_since_last_kill = 0.0

    def update(self, dt: float) -> None:                  # 0x1000d786c
        from .brick_manager import BrickManager
        if not self.active:
            return
        self.time_since_last_kill = self.time_since_last_kill + dt
        if self.time_since_last_kill <= 2.0:              # constant 2, not timeBetweenKills
            return
        if self.current_kill_count >= self.max_number_of_kills:
            return
        self.current_kill_count = self.current_kill_count + 1
        enemy = BrickManager.shared().closest_enemy()
        if enemy is not None:
            enemy.set_life(0.0)
            from ..platform.haptics import Haptics        # PORT ADDITION: the coil's own crack, over
            Haptics.shared().zap()                        # the kill set_life: has just made
            zap = self.playlist.any_sound_containing('zap') if self.playlist is not None else None
            if zap is not None:
                zap.set_spatialized(True)
                zap.set_planar(enemy.sound.planar if enemy.sound is not None else (0.0, 0.0, 0.0))
                zap.set_gain(3.5)
                zap.play(False)

                def on_end(_s):                           # update:_block_invoke 0x1000d7b2c
                    if self.current_kill_count >= self.max_number_of_kills:
                        self.clean()
                zap.add_3d_sound_end_callback(on_end)
        elif self.current_kill_count >= self.max_number_of_kills:
            self.clean()
        self.time_since_last_kill = 0.0

    def clean(self) -> None:                              # 0x1000d7b84
        self.active = False
        if self.playlist is not None:
            self.playlist.deactivate()
        self._clean_with_kill_report()
