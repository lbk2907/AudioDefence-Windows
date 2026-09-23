"""ADWeapon and ADMeleeWeapon.

Weapon states, named by -[ADWeapon stateToString]: 0 Idle, 1 Switching, 2 Shooting, 3 Continuous,
4 Continuous to tail, 5 Continuous Empty, 6 Reload Down, 7 Reload Empty, 8 Reload Up.

QUIRK kept: -[ADWeapon update:] advances timeInState and lastAnnouncerSpeech by the wall-clock time
between calls (CACurrentMediaTime), not by the timer's dt; only fireRateTimer uses dt.
"""
from __future__ import annotations

import logging
import time

from ..platform import crand
from ..platform.defaults import ns_bool_value, ns_float_value, ns_int_value
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from .modifiers import GameModifiers

log = logging.getLogger('weapon')

STATE_NAMES = ('Idle', 'Switching', 'Shooting', 'Continuous', 'Continuous to tail', 'Continuous Empty',
               'Reload Down', 'Reload Empty', 'Reload Up')   # 0x1000152d4..0x100015334


def ca_current_media_time() -> float:
    return time.perf_counter()


def _get(d, key):
    return d.get(key) if isinstance(d, dict) else None


def _c_div(a: int, b: int) -> int:
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


#: PORT DIVERGENCE: a weapon's sounds start where the sound does (user request).  Some of the game's own
#: recordings open with a moment of nothing - the Machine Gun's shot has 133 milliseconds of it, its tail
#: 133 and its deploy 145, the Grenade Launcher's shot 109, the Tactical Rifle's deploy 104 - and the
#: original plays them from the top, so the press and the sound are that far apart.  Tapping the Machine
#: Gun, which is what it is for, that silence is the gap between the shots; letting go of it after a burst,
#: it is the gap before the gun winds down.  The files are left alone: each sound is started past its own
#: silence instead (S3DSound.skip_to), measured once from what the decoder already holds
#: (decoder.lead_in), and only up to a quarter of a second, in case the quiet is the sound itself.
_LEAD_IN: dict = {}


def _at_the_sound(sound):
    """Have this sound start where the recording does, not where the file does; returns it, to wrap the
    place it is taken from the playlist."""
    if sound is None or not sound.path:
        return sound
    lead = _LEAD_IN.get(sound.path)
    if lead is None:
        from ..s3d import decoder
        if not decoder.is_cached(sound.path):             # not decoded yet: ask again next time, rather
            return sound                                  # than remember that it has no silence in it
        lead = _LEAD_IN[sound.path] = decoder.lead_in(sound.path)
    sound.skip_to = lead
    return sound


class Weapon:
    # -[ADWeapon initWithDictionary:] 0x100013f94
    def __init__(self, d: dict | None):
        from .inventory import Inventory
        self.time_in_continous = 0.0
        self.time_since_last_shot = 0.0
        self.shot_once = False
        self.fire_rate_timer = 0.0
        self.continuous_sound = None
        self.continuous_warning = None
        self.reload_sound = None                          # PORT ADDITION: the one reload actually started
        self.last_announcer_speech = 0.0
        self.previous_tick_time = 0.0
        self.dropped_magasine = False
        self.switching_time = 0.0
        self._state = 0
        self.time_in_state = 0.0
        self.playlist = None
        self.weapon_manager = None
        self.num_shots_fired = 0

        self.name = _get(d, 'name')
        self.range = ns_float_value(_get(d, 'range'))
        self.multihit = ns_bool_value(_get(d, 'multihit'))
        self.continuous_fire = ns_bool_value(_get(d, 'continuousFire'))
        self.explosive = ns_bool_value(_get(d, 'explosive'))
        level = _get(d, f'level_{Inventory.shared().level_for_weapon(self.name)}')
        self.fire_rate = ns_float_value(_get(level, 'fireRate'))
        self.damages = ns_float_value(_get(level, 'damages'))
        self._spread = ns_float_value(_get(level, 'spread'))
        self.critical_spread = ns_float_value(_get(level, 'criticalSpread'))
        self.critical_chance = ns_float_value(_get(level, 'criticalChance'))
        self.critical_multiplier = ns_float_value(_get(level, 'criticalMultiplier'))
        self.continuous_spread = ns_float_value(_get(level, 'continuous_spread'))
        if _get(level, 'dispersal') is not None:
            self.dispersal = ns_float_value(_get(level, 'dispersal'))
        else:
            self.dispersal = 100.0
        self.explosion_radius = ns_float_value(_get(level, 'explosionRadius'))
        self.projectile_speed = ns_float_value(_get(level, 'projectileSpeed'))
        self.reload_time = ns_float_value(_get(level, 'reloadTime'))
        self.time_before_explode = ns_float_value(_get(level, 'timeBeforeExplode'))
        self.capacity = ns_int_value(_get(level, 'capacity'))
        self.switching_time = 1.0
        self.bullets_in_clip = self.capacity
        self.bullets_total = 0x7fffffff
        self.time_since_last_shot = 0.0
        self.fire_sound_prefix = f'weapon_gun_{self.name}_fire'
        self.click_sound_prefix = f'weapon_gun_{self.name}_empty'
        self.playlist = S3DEngine.engine().play_list_with_name(self.name) if self.name is not None else None
        if self.playlist is not None:
            self.playlist.activate()
        self.set_state(0)
        mods = GameModifiers.shared()
        if mods.goldenBullet:
            bonus = max(_c_div(self.capacity, 10), 1)
            self.capacity = self.capacity + bonus
            self.bullets_in_clip = self.capacity
        elif mods.lessBullets:
            malus = max(_c_div(self.capacity, 10), 1)
            self.capacity = self.capacity - malus
            if self.capacity == 0:
                self.capacity = 1
            self.bullets_in_clip = self.capacity
        if mods.spread_modifier() != 0.0:
            self.continuous_spread = mods.spread_modifier() + self.continuous_spread
            self._spread = mods.spread_modifier() + self._spread
        self.last_announcer_speech = 5.0                  # 0x40a00000
        self.critical_chance = mods.head_shot_modifier() * self.critical_chance
        self.previous_tick_time = ca_current_media_time()

    def __repr__(self) -> str:
        return f'<{type(self).__name__} {self.name} state={self._state}>'

    # --- properties ------------------------------------------------------------------------------
    @property
    def state(self) -> int:
        return self._state

    @property
    def spread(self) -> float:                            # 0x100016180
        return self.continuous_spread if self._state == 3 else self._spread

    @spread.setter
    def spread(self, value: float) -> None:               # setSpread: 0x100016bdc
        self._spread = float(value)

    def set_state(self, state: int) -> None:              # 0x100015210
        if self._state == state:
            return
        self._state = state
        self.time_in_state = 0.0

    def state_to_string(self) -> str:                     # 0x100015240
        if 0 <= self._state <= 8:
            return STATE_NAMES[self._state]
        return f'Default : {self._state}'

    def change_state(self, state: int) -> bool:           # 0x100015148
        if self._state == state:
            return False
        old = self._state
        if state == 2:
            if self.ready_to_shoot():
                self.set_state(2)
        else:
            self.set_state(state)
        return (1 if old != 0 else 0) != self._state      # QUIRK: compares a bool with the new state

    def ready_to_shoot(self) -> bool:                     # 0x10001537c
        st = self._state
        if st in (6, 8, 1, 2):
            return False
        return st != 3

    def is_reloading(self) -> bool:                       # 0x10001667c
        st = self._state
        return st == 8 or st == 7 or st == 6

    # --- update ----------------------------------------------------------------------------------
    def update(self, dt: float) -> None:                  # 0x100014c8c
        now = ca_current_media_time()
        previous = self.previous_tick_time
        self.previous_tick_time = ca_current_media_time()
        st = self._state
        if st == 0:
            if self.continuous_sound is not None and self.continuous_sound.playing:
                self.continuous_sound.stop()
        elif st == 1:
            if self.time_in_state > self.switching_time:
                self.set_state(0)
        elif st == 2:
            if self.time_in_state > self.fire_rate:
                self.set_state(0)
        elif st == 3:
            if self.fire_rate_timer > self.fire_rate:
                self.fire_rate_timer = 0.0
                if not self.resolve_shoot():
                    self.play_click_sound()
                    if self.continuous_sound is not None:
                        self.continuous_sound.stop()
                    if self.continuous_warning is not None:
                        self.continuous_warning.stop()
                    self.set_state(5)
            self.fire_rate_timer = self.fire_rate_timer + dt
            self.time_in_continous = self.time_in_state
        elif st == 4:
            if self.time_in_state + self.time_in_continous > 0.2:
                if self.continuous_sound is not None:
                    self.continuous_sound.stop()
                if self.continuous_warning is not None:
                    self.continuous_warning.stop()
                self.change_state(0)
                self.play_continuous_tail()
        elif st == 5:
            if self.time_in_state > self.fire_rate:
                self.time_in_state = 0.0
                self.play_click_sound()
        elif st == 6:
            if self.time_in_state > 0.1:
                self.set_state(7)
                self.bullets_in_clip = 0
        elif st == 8:
            if self.time_in_state > self.reload_time:
                self.set_state(0)
                self.reload_sound = None                  # PORT ADDITION: it has played itself out
                if self.bullets_total >= self.capacity:
                    self.bullets_in_clip = self.capacity
                else:
                    self.bullets_in_clip = self.bullets_total
                if self.weapon_manager is not None:
                    self.weapon_manager.weapon_did_finish_reloading()
        elapsed = now - previous
        self.last_announcer_speech = elapsed + self.last_announcer_speech
        self.time_in_state = elapsed + self.time_in_state

    # --- firing ----------------------------------------------------------------------------------
    def single_shot(self) -> None:                        # 0x10001540c
        if not self.ready_to_shoot():
            return
        if self.resolve_shoot():
            self.play_single_shoot_sound()
            self.change_state(2)
        else:
            self.play_click_sound()

    def continuous_start(self) -> None:                   # 0x1000154a4
        if not self.continuous_fire:
            self.single_shot()
            return
        if not self.ready_to_shoot():
            return
        if not self.resolve_shoot():
            self.change_state(5)
            return
        self.change_state(3)
        pl = self.playlist
        self.continuous_sound = _at_the_sound(pl.any_sound_with_prefix(f'weapon_gun_{self.name}_conti')) \
            if pl else None
        if self.continuous_sound is not None:
            self.continuous_sound.set_spatialized(False)
            self.continuous_sound.set_gain(0.6)
            self.continuous_sound.play(True)
        self.continuous_warning = _at_the_sound(
            pl.any_sound_with_prefix(f'weapon_gun_{self.name}_warningloop')) if pl else None
        if self.continuous_warning is not None:
            self.continuous_warning.set_spatialized(False)
            self.continuous_warning.set_gain(0.0)
            self.continuous_warning.play(True)

    def continuous_stop(self) -> None:                    # 0x1000157f8
        if self.continuous_sound is not None:
            self.continuous_sound.stop()
        if self.continuous_warning is not None:
            self.continuous_warning.stop()
        if self._state == 3:
            self.change_state(4)
        elif self._state == 5:
            self.change_state(0)

    def stop_firing_now(self) -> None:
        """PORT ADDITION: stop this weapon where it stands - the loop, the warning loop, the state.

        `continuous_stop` hands state 3 over to state 4, which stops the sound and plays the tail on the
        next `update:`.  That is right while the weapon is in hand, and wrong the moment it is not: only
        the current weapon is updated (`ADWeaponManager update:`), so a gun switched away from mid-burst
        was left in state 3 with its "_conti" loop playing and nobody to stop it - and since the gun the
        player then held had never been started, it never ran dry, so no reload was called out either.
        The same holds when the player dies with the trigger down.
        """
        if self.continuous_sound is not None:
            self.continuous_sound.stop()
        if self.continuous_warning is not None:
            self.continuous_warning.stop()
        if self._state in (3, 4, 5):
            self.play_continuous_tail()                   # the gun spins down, as it would have
        self.set_state(0)
        self.fire_rate_timer = 0.0
        self.time_in_continous = 0.0

    def play_continuous_tail(self) -> None:               # 0x1000158b0
        tail = _at_the_sound(
            self.playlist.any_sound_with_prefix(f'weapon_gun_{self.name}_tail')) if self.playlist else None
        if tail is not None:
            tail.set_spatialized(False)
            tail.set_gain(0.6)
            tail.play(False)

    def resolve_shoot(self) -> bool:                      # 0x100015a1c
        if self.bullets_in_clip < 1 or self.bullets_total < 1:
            return False
        self.num_shots_fired = self.num_shots_fired + 1
        self.bullets_in_clip = self.bullets_in_clip - 1
        self.bullets_total = self.bullets_total - 1
        if GameModifiers.shared().rustyWeapons:
            if crand.c_mod(crand.rand(), 100) == 1:
                self.bullets_in_clip = 0
        low = float(self.bullets_in_clip) <= float(self.capacity) * 0.2
        if self.continuous_sound is not None:
            self.continuous_sound.set_gain(0.6)
        if self.continuous_warning is not None:
            self.continuous_warning.set_gain(0.6 if low else 0.0)
        if self.weapon_manager is not None:
            self.weapon_manager.shot()
        return True

    def play_single_shoot_sound(self) -> None:            # 0x100015c80
        """Picks random "_fire_" sounds until one is not playing (busy loop in the original);
        below 20% of the clip a random "_warning" sound is layered on top.

        DIVERGENCE: the original waits on the main thread (100015d38..100015dc4) for as long as every
        "_fire_" sound of the weapon is still playing - `-[S3DSound playing]` stays YES until the file has
        played to its end (csl::Abst_SoundFile::vfunc_7 0x1000e4be4: current frame < stop frame).  The fire
        sounds last 1 to 1.7 s while the Tactical Rifle fires every 0.25 s and the Micro SMG every 0.2 s,
        so quick shots froze the whole game for up to a second after the hit sounds (played by
        resolveShoot) had started.  When every fire sound is still playing the port gives the shot a source
        of its own (S3DEngine.play_copy_of), so the shots overlap; only if that fails does it fall back to
        restarting the sound closest to its end, which is heard as a cut."""
        pl = self.playlist
        fire = None
        warning = None
        while fire is None or fire.playing:
            if fire is not None:
                candidates = pl.sounds_matching(lambda k: '_fire_' in k)
                if all(c.playing for c in candidates):
                    fire = _at_the_sound(min(candidates, key=lambda c: c.duration - c.elapsed_time()))
                    if S3DEngine.engine().play_copy_of(fire):     # let this shot overlap the last one
                        if warning is not None:
                            warning.set_spatialized(False)
                            warning.set_gain(0.6)
                            warning.play(False)
                        return
                    break
            fire = _at_the_sound(pl.any_sound_containing('_fire_')) if pl is not None else None
            if fire is None:
                # DIVERGENCE: the original spins forever here when no "_fire_" sound exists.
                log.warning('%s has no _fire_ sound', self.name)
                return
            if float(self.bullets_in_clip) > float(self.capacity) * 0.2:
                continue
            warning = _at_the_sound(pl.any_sound_with_suffix('_warning'))
        fire.set_spatialized(False)
        fire.set_gain(0.6)
        fire.play(False)
        if warning is not None:
            warning.set_spatialized(False)
            warning.set_gain(0.6)
            warning.play(False)

    def play_click_sound(self) -> None:                   # 0x100015f0c
        from .parameters import GameParameters
        click = _at_the_sound(
            self.playlist.any_sound_with_prefix(self.click_sound_prefix)) if self.playlist else None
        if click is not None:
            click.set_spatialized(False)
            click.play(False)
        if not GameParameters.shared().last_announcer_value():
            return
        if self.last_announcer_speech <= 5.0:
            return
        self.last_announcer_speech = 0.0
        announcer = S3DEngine.engine().play_list_with_name('announcer')
        if self.bullets_total >= 1:
            snd = announcer.any_sound_containing('reload') if announcer else None
        else:
            snd = announcer.any_sound_containing('outofammo') if announcer else None
        if snd is not None:
            snd.play()

    # --- reload / deploy -------------------------------------------------------------------------
    def reload(self) -> None:                             # 0x1000161cc
        from .parameters import GameParameters
        if self.bullets_total == 0:
            if not GameParameters.shared().last_announcer_value():
                return
            if self.last_announcer_speech <= 5.0:
                return
            self.last_announcer_speech = 0.0
            announcer = S3DEngine.engine().play_list_with_name('announcer')
            snd = announcer.any_sound_containing('outofammo') if announcer else None
            if snd is not None:
                snd.play()
            return
        if self.is_reloading():
            return
        Tracker.shared().reload_weapon_with_remaining_bullets(self.bullets_in_clip, self.name)
        snd = _at_the_sound(
            self.playlist.any_sound_with_prefix(f'weapon_gun_{self.name}_reloadfull')) if self.playlist else None
        self.reload_sound = snd                           # PORT ADDITION: so pause and interrupt find this one
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.6)
            snd.play(False)
        self.change_state(8)

    def interrupt_reload(self) -> None:                   # 0x10001652c
        # DIVERGENCE: the original asks the playlist for a sound with the reload prefix and stops that,
        # and `anySoundWithPrefix:` returns a random one of them - not necessarily the one playing.  A
        # weapon with more than one reload sound could therefore be interrupted and go on reloading
        # aloud.  The sound `reload` started is remembered now, and that is the one stopped.
        snd = self.reload_sound
        if snd is None and self.playlist is not None:
            snd = self.playlist.any_sound_with_prefix(f'weapon_gun_{self.name}_reloadfull')
        if snd is not None:
            snd.stop()
        self.reload_sound = None
        self.set_state(0)

    def deploy(self) -> None:                             # 0x1000166e4
        from .parameters import GameParameters
        self.change_state(1)
        self.time_since_last_shot = self.fire_rate
        pl = self.playlist
        snd = _at_the_sound(pl.any_sound_with_prefix(f'weapon_gun_{self.name}_deploy')) if pl else None
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.6)
            snd.play(False)
        if GameParameters.shared().last_announcer_value():
            voice = _at_the_sound(pl.any_sound_with_prefix(f'weapon_gun_{self.name}_voice')) if pl else None
            if voice is not None:
                voice.set_spatialized(False)
                voice.set_gain(0.6)
                voice.play(False)

    # --- pausing (PORT ADDITION) ------------------------------------------------------------------
    def pause(self) -> None:
        """Hold the weapon exactly where it is while the game is paused.

        DIVERGENCE: `pauseGame` 0x10005b5fc stops the timers and pauses the bricks and the ambience, and
        says nothing about the weapon.  Two things followed.  The reload sound is not a brick's, so it
        played on through the pause.  And `update:` 0x100014c8c advances `timeInState` by the wall clock
        between calls rather than by the timer's dt (the quirk at the top of this file), so the whole
        length of the pause was credited to the reload on the first pass after resuming: pausing during a
        reload finished it, however long the reload was.  Pausing mid-reload was a way to reload for
        free, which is what this stops."""
        for sound in (self.reload_sound, self.continuous_sound, self.continuous_warning):
            if sound is not None:
                sound.pause()

    def resume(self) -> None:
        for sound in (self.reload_sound, self.continuous_sound, self.continuous_warning):
            if sound is not None:
                sound.resume()
        # The pause must not count towards the state this weapon is in: start the wall clock again here.
        self.previous_tick_time = ca_current_media_time()

    def clean(self) -> None:                              # 0x100016a2c
        if self.continuous_sound is not None:
            self.continuous_sound.stop()
        if self.continuous_warning is not None:
            self.continuous_warning.stop()

    def dealloc(self) -> None:                            # 0x100016a78 (called where ARC would release it)
        log.info('Dealloc weapon')
        if self.playlist is not None:
            self.playlist.deactivate()


class MeleeWeapon(Weapon):
    def update(self, dt: float) -> None:                  # -[ADMeleeWeapon update:] 0x10000740c
        if self._state == 2 and self.time_in_state > self.fire_rate:
            self.set_state(0)
        self.time_in_state = self.time_in_state + dt

    def single_shot(self) -> None:                        # 0x1000074c0
        self.set_state(2)
        if self.weapon_manager is not None:
            self.weapon_manager.did_shot_with_melee()

    def play_hit_sound(self) -> None:                     # 0x100007538
        """Not spatialised, as the original has it.

        REVERTED (user request): a version of this port placed the hit on the enemy that was struck and
        played `_miss_` at the player for the swing, on the reasoning that a blow you can hear the
        direction of is what an audio game is for.  Players did not want it.  `_hit_` is the swing and
        the impact in one recording, so splitting the two across two positions cut across the sound
        rather than opening it up, and it was a deliberate change to a game that was not asking for one:
        a melee weapon sounding from the hand is what the original does, on purpose, and this port's
        business is that game rather than a better idea of it."""
        snd = _at_the_sound(self.playlist.any_sound_containing('_hit_')) if self.playlist else None
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.8)
            snd.play(False)

    def play_miss_sound(self) -> None:                    # 0x100007610
        """Not spatialised, and right not to be: a miss is your own swing, and it hit nothing."""
        snd = _at_the_sound(self.playlist.any_sound_containing('_miss_')) if self.playlist else None
        if snd is not None:
            snd.set_spatialized(False)
            snd.set_gain(0.8)
            snd.play(False)
