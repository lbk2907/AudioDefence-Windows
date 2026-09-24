"""ADWeaponManager.

Two kinds of instances exist in the original:
* ``WeaponManager.shared()`` (+sharedWeaponManager) is a plain -init object with no weapons. It answers the
  Weapons.plist lookups and owns the current power-up (initPowerUp:/usePowerUp always go through it).
* The gameplay controllers allocate their own manager (initWithWeaponsFromArmory /
  initWithChallengeWeaponArray:) which owns the guns, the melee weapon and the projectiles, and whose
  update: also ticks the shared manager's power-up.
"""
from __future__ import annotations

import logging
import math

from ..platform import crand
from ..platform.defaults import ns_bool_value, ns_int_value
from ..platform.tracker import Tracker
from ..s3d.engine import S3DEngine
from . import data

log = logging.getLogger('weapons')


def _integer_value(v) -> int:
    """-[NSNumber/NSString integerValue] stored through setBulletsTotal:(int)."""
    return ns_int_value(v)


class WeaponManager:
    _shared: 'WeaponManager | None' = None

    @classmethod
    def shared(cls) -> 'WeaponManager':                   # +[ADWeaponManager sharedWeaponManager] 0x1000a6ee0
        if cls._shared is None:
            cls._shared = WeaponManager()
        return cls._shared

    def __init__(self):                                   # -[NSObject init]
        self.all_weapons = None
        self.all_power_ups = None
        self.weapons_array = None
        self.projectile_array = None
        self.melee_weapon = None
        self.current_weapon_index = 0
        self.current_weapon = None
        self._power_up = None

    # --- plist lookups ---------------------------------------------------------------------------
    def get_all_weapons_array(self) -> list:              # 0x1000a6f78
        if self.all_weapons is None:
            self.all_weapons = (data.plist_ro('Weapons') or {}).get('Weapons')
        return self.all_weapons

    def dictionary_for_weapon_with_name(self, name):      # 0x1000a70b8
        for d in self.get_all_weapons_array() or []:
            if d.get('name') == name:
                return d
        return None

    def is_melee_for_weapon_with_name(self, name) -> bool:   # 0x1000a72a4
        d = self.dictionary_for_weapon_with_name(name)
        return ns_bool_value(d.get('melee') if d is not None else None)

    def get_all_melee_weapons(self) -> list:              # 0x1000a735c
        return [d for d in self.get_all_weapons_array() or []
                if self.is_melee_for_weapon_with_name(d.get('name'))]

    def display_name_for_item_with_name(self, name):      # 0x1000a7568
        d = self.dictionary_for_weapon_with_name(name)
        if d is not None:
            return d.get('displayName')
        d = self.dictionary_for_powerup_with_name(name)
        if d is not None:
            return d.get('displayName')
        return None

    def get_all_power_ups_array(self) -> list:            # 0x1000a9500
        if self.all_power_ups is None:
            self.all_power_ups = (data.plist_ro('Weapons') or {}).get('PowerUps')
        return self.all_power_ups

    def dictionary_for_powerup_with_name(self, name):     # 0x1000a9640
        for d in self.get_all_power_ups_array() or []:
            if d.get('name') == name:
                return d
        return None

    def number_of_weapons_available_for_sale(self) -> int:   # 0x1000a8e44
        from .inventory import Inventory
        inv = Inventory.shared()
        n = 0
        for d in self.get_all_weapons_array() or []:
            if ns_int_value(d.get('price')) < inv.coins and not inv.has_unlocked_weapon(d.get('name')):
                n += 1
        return n

    def number_of_weapons_upgradable(self) -> int:        # 0x1000a90ec
        from .inventory import Inventory
        inv = Inventory.shared()
        n = 0
        for d in self.get_all_weapons_array() or []:
            name = d.get('name')
            if not inv.has_unlocked_weapon(name):
                continue
            nxt = d.get(f'level_{inv.level_for_weapon(name) + 1}')
            if nxt is None:
                continue
            if ns_int_value(nxt.get('cost')) < inv.coins:
                n += 1
        return n

    # --- construction (gameplay instances) -------------------------------------------------------
    @classmethod
    def with_weapons_from_armory(cls) -> 'WeaponManager':    # -initWithWeaponsFromArmory 0x1000a76c4
        from .inventory import Inventory
        from .weapon import MeleeWeapon, Weapon
        self = cls()
        self.weapons_array = []
        self.projectile_array = []
        inv = Inventory.shared()
        w1 = Weapon(self.dictionary_for_weapon_with_name(inv.weapon_slot1))
        w1.weapon_manager = self
        self.weapons_array.append(w1)
        w2 = Weapon(self.dictionary_for_weapon_with_name(inv.weapon_slot2))
        w2.weapon_manager = self
        self.weapons_array.append(w2)
        melee = MeleeWeapon(self.dictionary_for_weapon_with_name(inv.weapon_slot_melee))
        melee.weapon_manager = self
        self.melee_weapon = melee
        self.set_current_weapon(self.weapons_array[0])
        Tracker.shared().set_value_for_dimension(self.current_weapon.name, 'Weapon name', 0, 0)
        Tracker.shared().send_load_out_event(w1, w2, self.melee_weapon)
        return self

    def get_equipped_weapons_list(self) -> list:          # 0x1000a7c84
        out = list(self.weapons_array or [])
        out.append(self.melee_weapon)
        return list(out)

    @classmethod
    def with_weapon_list(cls, _names) -> 'WeaponManager':    # -initWithWeaponList: 0x1000a7d44 (argument unused)
        from .weapon import MeleeWeapon, Weapon
        self = cls()
        self.weapons_array = []
        self.projectile_array = []
        for d in self.get_all_weapons_array() or []:
            if ns_bool_value(d.get('melee')):
                self.melee_weapon = MeleeWeapon(d)
                self.melee_weapon.weapon_manager = self
            else:
                w = Weapon(d)
                w.weapon_manager = self
                self.weapons_array.append(w)
        self.set_current_weapon(self.weapons_array[0])
        return self

    @classmethod
    def with_challenge_weapon_array(cls, entries: list) -> 'WeaponManager':   # 0x1000a80f4
        from .weapon import MeleeWeapon, Weapon
        self = cls()
        self.weapons_array = []
        self.projectile_array = []
        for entry in entries or []:
            for d in self.get_all_weapons_array() or []:
                if d.get('name') != entry.get('name'):
                    continue
                if ns_bool_value(d.get('melee')):
                    self.melee_weapon = MeleeWeapon(d)
                    self.melee_weapon.weapon_manager = self
                    continue
                w = Weapon(d)
                if entry.get('ammo') is not None:
                    w.bullets_total = _integer_value(entry.get('ammo'))
                w.weapon_manager = self
                self.weapons_array.append(w)
        self.set_current_weapon(self.weapons_array[0])    # an empty list raises, as objectAtIndex:0 would
        return self

    @classmethod
    def with_weapon_dictionary(cls, entries: list) -> 'WeaponManager':   # -initWithWeaponDictionary: 0x1000a86cc
        from .weapon import Weapon
        self = cls()
        self.weapons_array = []
        self.projectile_array = []
        for entry in entries or []:
            for d in self.get_all_weapons_array() or []:
                if d.get('name') != entry.get('name'):
                    continue
                w = Weapon(d)
                w.weapon_manager = self
                if ns_int_value(entry.get('ammo')) != 0:
                    w.bullets_total = ns_int_value(entry.get('ammo'))
                self.weapons_array.append(w)
        self.set_current_weapon(self.weapons_array[0])
        return self

    # --- tick ------------------------------------------------------------------------------------
    def update(self, dt: float) -> None:                  # 0x1000a8c38
        if self.current_weapon is not None:
            self.current_weapon.update(dt)
        for p in list(self.projectile_array or []):
            p.update(dt)
        pu = WeaponManager.shared().power_up
        if pu is not None:
            pu.update(dt)
        if self.melee_weapon is not None:
            self.melee_weapon.update(dt)

    # --- pausing (PORT ADDITION) ------------------------------------------------------------------
    def pause(self) -> None:
        """Freeze the weapons and the power-up in hand with the rest of the game: see Weapon.pause and
        PowerUp.pause."""
        for weapon in (self.current_weapon, self.melee_weapon):
            if weapon is not None:
                weapon.pause()
        if self._power_up is not None:
            self._power_up.pause()

    def resume(self) -> None:
        for weapon in (self.current_weapon, self.melee_weapon):
            if weapon is not None:
                weapon.resume()
        if self._power_up is not None:
            self._power_up.resume()

    # --- power-ups (always through the shared instance) ------------------------------------------
    @property
    def power_up(self):
        return self._power_up

    def set_power_up(self, pu) -> None:                   # 0x1000aae80
        old = self._power_up
        self._power_up = pu
        if old is not None and old is not pu:
            weapon = getattr(old, 'minigun_weapon', None)   # ADMinigunPowerUp .cxx_destruct releases it
            if weapon is not None:
                weapon.dealloc()

    def init_random_power_up(self) -> None:               # 0x1000a982c
        self.init_power_up(crand.c_mod(crand.rand(), 4) + 1)

    def init_power_up(self, kind: int) -> None:           # 0x1000a9874
        from .powerups import FireworksPowerUp, MinigunPowerUp, TeslaPowerUp, TornadoPowerUp
        shared = WeaponManager.shared()
        created = {1: (MinigunPowerUp, 'minigun'), 2: (FireworksPowerUp, 'fireworks'),
                   3: (TornadoPowerUp, 'tornado'), 4: (TeslaPowerUp, 'tesla')}.get(kind)
        if created is not None:
            cls, label = created
            shared.set_power_up(cls(kind))
            Tracker.shared().set_value_for_dimension(label, 'PowerUp name', 0, 0)
        if shared.power_up is not None:
            shared.power_up.preload()

    def use_power_up(self) -> None:                       # 0x1000a9cd8
        pu = WeaponManager.shared().power_up
        if pu is not None:
            pu.activate()

    # --- input -----------------------------------------------------------------------------------
    def weapon_touched_down(self) -> None:                # 0x1000a9d78
        pass

    def weapon_touched_up(self) -> None:                  # 0x1000a9d7c
        pass

    def weapon_single_shot(self) -> None:                 # 0x1000a9d80
        if self.is_weapon_ready_to_shoot():
            self.current_weapon.single_shot()

    def select_next_weapon(self) -> None:                 # 0x1000a9e04
        cw = self.current_weapon
        if cw is not None:
            cw.stop_firing_now()                          # PORT ADDITION: it is not the gun in hand now
        if cw is not None and (cw.state == 6 or cw.state == 8):
            cw.interrupt_reload()
        self.current_weapon_index = self.current_weapon_index + 1
        if not (self.current_weapon_index < len(self.weapons_array or [])):
            self.current_weapon_index = 0
        old_name = cw.name if cw is not None else None
        old_bullets = cw.bullets_in_clip if cw is not None else 0
        self.set_current_weapon(self.weapons_array[self.current_weapon_index])
        Tracker.shared().switch_from_weapon(old_name, self.current_weapon.name, old_bullets)
        self.current_weapon.deploy()

    def set_current_weapon(self, weapon) -> None:         # 0x1000aa124
        self.current_weapon = weapon

    def shot(self) -> None:                               # 0x1000aa15c
        from .brick_manager import BrickManager
        if self.current_weapon is not None and self.current_weapon.explosive:
            self.create_projectile_for_current_weapon()
            return
        BrickManager.shared().shot_with_weapon(self.current_weapon)

    def continuous_start(self) -> None:                   # 0x1000aa26c
        if self.is_weapon_ready_to_shoot():
            self.current_weapon.continuous_start()

    def continuous_stop(self) -> None:                    # 0x1000aa2f0
        if self.current_weapon is not None:
            self.current_weapon.continuous_stop()

    def stop_firing_after_player_was_killed(self) -> None:
        """PORT ADDITION: the player is dead with the trigger still down (user request).  Nothing else
        would stop the gun: the key is still held, so no release comes, and the weapon goes on firing into
        the death overlay."""
        for weapon in (self.current_weapon, self.melee_weapon):
            if weapon is not None:
                weapon.stop_firing_now()

    def weapon_did_finish_reloading(self) -> None:        # 0x1000aa34c
        pass

    def is_weapon_ready_to_shoot(self) -> bool:           # 0x1000aa350
        melee_state = self.melee_weapon.state if self.melee_weapon is not None else 0
        if melee_state == 2:
            return False
        return bool(self.current_weapon is not None and self.current_weapon.ready_to_shoot())

    def create_projectile_for_current_weapon(self) -> None:   # 0x1000aa3ec
        from .brick_manager import BrickManager
        from .projectile import Projectile
        w = self.current_weapon
        target = BrickManager.shared().target_enemi_for_explosive_weapon(w)
        h = S3DEngine.engine().head_orientation
        ox, oy = math.cos(h), math.sin(h)
        time_before_explode = w.time_before_explode
        if target is not None:
            s13 = math.sqrt(target.squared_distance)
            if not target.next_shot_will_be_critical:
                s13 = s13 - time_before_explode * target.speed
            s13 = s13 / (target.speed + w.projectile_speed)   # time to reach the target
            ttl = s13
            if not target.next_shot_will_be_critical:
                ttl = s13 + w.time_before_explode
            d = s13 * w.projectile_speed
            p = Projectile(w.projectile_speed, d * d, ttl, w.name, (ox, oy))
        else:
            p = Projectile(w.projectile_speed, w.range * w.range, w.time_before_explode, w.name, (ox, oy))
        p.weapon = w
        self.projectile_array.append(p)
        p.tag = len(self.projectile_array)

    def projectiles(self) -> list:                        # 0x1000aaa88
        return self.projectile_array

    def shoot_with_melee(self) -> None:                   # 0x1000aaa98
        # KEPT (user request): melee cancels a reload, as the original does.  The interrupt at 0x1000aab3c
        # puts the weapon back in Idle, and `isWeaponReadyToShoot` 0x1000aa350 - asked straight after -
        # therefore answers yes: melee does not override the check, it clears the state the check reads.
        # Taking the interrupt out would make melee wait for a reload the way firing does, which is
        # tidier and is not the game: swinging a machete while the pistol is reloading is something the
        # original lets you do, and the reload you gave up is the price.
        cw = self.current_weapon
        if cw is not None and (cw.state == 6 or cw.state == 8):
            cw.interrupt_reload()
        if self.is_weapon_ready_to_shoot():
            self.melee_weapon.single_shot()

    def did_shot_with_melee(self) -> None:                # 0x1000aabec
        from .brick_manager import BrickManager
        BrickManager.shared().shot_with_weapon(self.melee_weapon)

    def melee_weapon_name(self):                          # 0x1000aac60
        return self.melee_weapon.name if self.melee_weapon is not None else None

    def reload_gesture_down(self) -> None:                # 0x1000aac7c
        if self.current_weapon is not None:
            self.current_weapon.reload()

    def reload_gesture_up(self) -> None:                  # 0x1000aacd8
        if self.current_weapon is not None:
            self.current_weapon.reload()

    def shut_down(self) -> None:                          # 0x1000aad34
        released = list(self.weapons_array or [])
        if self.weapons_array is not None:
            self.weapons_array.clear()
        for w in released:
            if w is not self.current_weapon:              # currentWeapon still retains its weapon
                w.dealloc()

    def clean(self) -> None:                              # 0x1000aad50
        self.set_current_weapon(None)
        self.continuous_stop()                            # currentWeapon is already nil: no-op
        for w in list(self.weapons_array or []):
            w.clean()
        if self.projectile_array is not None:
            self.projectile_array.clear()
        released = list(self.weapons_array or [])
        if self.weapons_array is not None:
            self.weapons_array.clear()
        for w in released:
            w.dealloc()
        if self._power_up is not None:                    # this instance's own power-up (nil for gameplay
            self._power_up.clean()                        # managers: the shared one keeps its power-up)
        self.set_power_up(None)
        if self.melee_weapon is not None:
            self.melee_weapon.dealloc()
        self.melee_weapon = None
