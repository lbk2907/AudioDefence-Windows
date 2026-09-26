"""ADGameModifiers - Tarot / Roulette effects and the Endless difficulty ramp."""
from __future__ import annotations

import datetime
import time

FLAGS = ('slowerEnemies', 'weakerEnemies', 'moreDamages', 'moreMeleeDamages', 'moreBullets', 'freeRevive',
         'luckyShots', 'metalDetector', 'tesla', 'goldenBullet', 'widerSpread', 'moreHeadshots',
         'baseComboBonus', 'morePowerUps', 'betterPowerUps', 'jukebox', 'strongerEnemies', 'cows', 'storm',
         'lessMeleeDamages', 'lessHeadshots', 'rustyWeapons', 'cars', 'enragedHorde', 'narrowedSpread',
         'machine', 'lessDamages', 'lessBullets', 'noCritical', 'fasterReloadTime', 'slowerReloadTime',
         'fasterEnemies')
# setters that exist on the class besides the flags reset by resetModifiers
EXTRA_SETTERS = ('fullMoon', 'bullshit', 'difficultyModifier')

#: PORT ADDITION: flags the port's own tarot cards set (user request).  They are kept apart from FLAGS so
#: that list stays what the original's class has - thirty-two of them, in its own order - and a glance says
#: which effects are Somethin' Else's and which are ours.  Everything that reads FLAGS reads these too:
#: they are cleared by `reset_modifiers` at the start of every game and accepted by `has_setter`, so a card
#: carrying one is applied by `applyModifier:` 0x100035da4 exactly as the original's cards are.
PORT_FLAGS = ('earlyPowerUp', 'luckyNight', 'lessPowerUps', 'lessCoins')


class GameModifiers:
    _shared: 'GameModifiers | None' = None

    @classmethod
    def shared(cls) -> 'GameModifiers':      # +[ADGameModifiers sharedModifiers] 0x1000de10c
        if cls._shared is None:
            m = GameModifiers()
            m.fullMoon = m.check_full_moon()
            m.reset_modifiers()
            cls._shared = m
        return cls._shared

    def __init__(self):
        for f in FLAGS + PORT_FLAGS:
            setattr(self, f, False)
        self.fullMoon = False
        self.bullshit = False
        self.difficultyModifier = 0.0

    def reset_modifiers(self) -> None:      # 0x1000de1f0
        for f in FLAGS + PORT_FLAGS:
            if f == 'tesla':
                self.set_tesla(False)
            else:
                setattr(self, f, False)
        self.difficultyModifier = 1.0

    def has_setter(self, selector: str) -> bool:
        return selector in FLAGS or selector in EXTRA_SETTERS or selector in PORT_FLAGS

    def apply_setter(self, selector: str, value) -> bool:
        """[ADGameModifiers set<Selector>:YES] when respondsToSelector: says so."""
        if not self.has_setter(selector):
            return False
        if selector == 'tesla':
            self.set_tesla(bool(value))
        else:
            setattr(self, selector, value)
        return True

    # --- derived values --------------------------------------------------------------------------
    def head_shot_modifier(self) -> float:          # 0x1000de51c
        v = 1.5 if self.moreHeadshots else 1.0
        return v - 0.5 if self.lessHeadshots else v

    def enemi_life_modifier(self) -> float:         # 0x1000de584
        v = 0.9 if self.weakerEnemies else 1.0
        if self.strongerEnemies:
            v += 0.2
        return v * self.difficultyModifier

    def enemi_speed_modifier(self) -> float:        # 0x1000de610
        v = 1.2 if self.fasterEnemies else 1.0
        if self.slowerEnemies:
            v -= 0.1
        return v * self.difficultyModifier

    def gun_damages_modifier(self) -> float:        # 0x1000de69c
        v = 1.1 if self.moreDamages else 1.0
        return v - 0.1 if self.lessDamages else v

    def melee_damages_modifier(self) -> float:      # 0x1000de714
        v = 1.25 if self.moreMeleeDamages else 1.0
        return v - 0.25 if self.lessMeleeDamages else v

    def reload_time_modifier(self) -> float:        # 0x1000de77c (only logged by the game)
        v = 1.2 if self.fasterReloadTime else 1.0
        return v - 0.2 if self.slowerReloadTime else v

    def spread_modifier(self) -> float:             # 0x1000de7f4
        v = -5.0 if self.narrowedSpread else 0.0
        return v + 5.0 if self.widerSpread else v

    def set_tesla(self, value: bool) -> None:       # 0x1000de904
        if self.tesla == value:
            return
        self.tesla = value
        try:
            from ..s3d.engine import S3DEngine
            pl = S3DEngine.engine().play_list_with_name('tesla')
        except Exception:
            return
        if pl is None:
            return
        if value:                                   # no deactivate when cleared (0x1000de9ac)
            pl.activate()

    @staticmethod
    def check_full_moon() -> bool:                  # 0x1000de9e8
        now = datetime.datetime.now()
        ref = datetime.datetime(1970, 1, 7, now.hour, now.minute)
        t = int((now - ref).total_seconds())
        m = t - int(t / 0x26ee93) * 0x26ee93        # C '%' (truncating)
        phase = int(m / 86400) + 1
        return phase == 15
