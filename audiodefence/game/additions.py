"""PORT ADDITION: the port's own content, added to the original's data as that data is read.

The rule this file exists to keep: **the plists are the original, and everything the port adds is here.**
`game/` holds Somethin' Else's files and stays exactly as they shipped it - not re-encoded, not appended
to, not corrected - and anything the port invents is declared in this module instead.  `data._load` hands
each plist through whatever is registered for it, so a new card, a new level, a new weapon or a new wave
is seen by every one of the twenty-two places that read the original's data, without any of them knowing.

**Additions only, never replacements.**  `new_key` refuses to overwrite a key the original already has,
so an addition cannot quietly shadow the game.  That keeps the line legible: if a value is in `game/` it
is theirs, and if it is here it is ours.  Changing something the original has is a different kind of
change - it belongs in the code that reads the value, where a divergence can be seen and written down in
`docs/PORTING_NOTES.md`.

What this cannot do is sound.  A new enemy or weapon that makes a noise needs recordings, and the engine
finds those by name under `game/sounds/`, which is their folder.  Audible content needs a folder of the
port's own and an engine that looks in both; this module is for data.
"""
from __future__ import annotations

import logging

log = logging.getLogger('game.additions')

#: plist name -> the functions that add to it, in the order they were written
ADDITIONS: dict = {}


def adds_to(plist_name: str):
    """Register a function that is given a freshly loaded plist and adds the port's own content to it."""
    def keep(fn):
        ADDITIONS.setdefault(plist_name, []).append(fn)
        return fn
    return keep


def apply_to(plist_name: str, data):
    """Every addition registered for that plist, applied in order.  Returns the data it was given."""
    if data is None:
        return data
    for fn in ADDITIONS.get(plist_name.replace('.plist', ''), ()):
        try:
            fn(data)
        except Exception:                                 # an addition must never stop the game loading
            log.exception('the port addition %s could not be applied to %s', fn.__name__, plist_name)
    return data


def new_key(where: dict, key: str, value) -> None:
    """Add a key the original does not have.  Raises if it does: see the module docstring."""
    if key in where:
        raise KeyError('%r is the original\'s own; an addition may not replace it' % key)
    where[key] = value


def new_entry(entries: list, entry: dict) -> None:
    """Add one entry to a list the original ships.  Raises if it already holds one by that title.

    `new_key`'s counterpart: several of their plists are lists of dictionaries - the tarot decks, the
    weapons, the power-ups - and adding to one is how the port gives the game new content.  The title is
    what a player hears, so two entries sharing one would be two cards nobody could tell apart.
    """
    for existing in entries:
        if isinstance(existing, dict) and existing.get('title') == entry.get('title'):
            raise KeyError('%r is already in this list; an addition may not replace it' % entry.get('title'))
    entries.append(dict(entry))


def named(entries, name: str):
    """The entry called `name` in one of the original's lists of dictionaries, or None.

    Several of its plists are lists rather than maps - the weapons, the power-ups - each entry carrying
    its own `name`."""
    for entry in entries or ():
        if isinstance(entry, dict) and entry.get('name') == name:
            return entry
    return None


# ================================================================================ the additions themselves

#: A fifth power-up level, which the Powered Power Ups tarot card is the only way to reach.
#:
#: The card says "All Power Ups are fully levelled up for this game" and gives one level, and only when
#: the data has a next one - so a player who has bought every upgrade gets nothing at all from it, while
#: being told it is one of the best cards in the deck.  They keep it and play a run with one of their two
#: tarot slots empty.  This is the level that player gets instead (user request).
#:
#: The numbers carry each power-up's own progression one step: the Minigun's duration goes up by 2.5 a
#: level, the Tesla's kills by one, and the Fireworks' damage and the Tornado's reach both take the +2
#: their own last step took.  It cannot be bought: the armory stops at four in three places of its own
#: (`upgrade_button_pressed` tests `level > 3`, two more test `level >= 4`), which read the inventory.
#:
#: `frequency` is deliberately absent.  `resetPowerUpCooldown` 0x10004b640 reads its level straight from
#: the inventory rather than through `_level_dictionary`, so the card has never reached the cooldown, in
#: the original or here; giving it a fifth level would add a tier nothing reads.
FIFTH_POWER_UP_LEVEL = {
    'minigun': {'duration': 15},                          # 5, 7.5, 10, 12.5
    'fireworks': {'damages': 9},                          # 3, 4, 5, 7
    'tesla': {'kills': 5},                                # 1, 2, 3, 4
    'tornado': {'blowDistance': 7},                       # 1, 2, 3, 5
}


#: The port's own tarot cards, by the deck they are dealt from (user request).
#:
#: Each deck has a subject the original kept to, and these keep to it as well: level 1 is the arena and
#: what you brought to it, level 2 is the zombies, and level 3 - the card that is dealt and kept - is your
#: guns.  Each deck also gains as many good cards as bad ones, so the even split that makes the third card
#: a coin flip stays even.
#:
#: Every `selector` here is a flag something reads.  Two are the original's own and were never dealt:
#: `fasterReloadTime` and `slowerReloadTime` are set by nothing in the original, and `reloadTimeModifier`
#: 0x1000de77c computes 1.2 and 0.8 from them and only writes the number to the log.  The other four are
#: the port's (`modifiers.PORT_FLAGS`).  The icons are chosen from the set the original already ships, so
#: nothing here needs art that is not in `game/`.
NEW_CARDS = {
    'level_1': (
        {'title': 'Air Drop Inbound', 'goodbad': 'good', 'selector': 'earlyPowerUp',
         'icon': 'Roulette_icon_increase',
         'description': 'Your first Power Up is already on its way.'},
        {'title': 'Lucky Night', 'goodbad': 'good', 'selector': 'luckyNight',
         'icon': 'Roulette_icon_luck',
         'description': 'Diamond Droppers are feeling generous. Two Diamonds each!'},
        {'title': 'Supply Delay', 'goodbad': 'bad', 'selector': 'lessPowerUps',
         'icon': 'Roulette_icon_cogs',
         'description': 'Dr. Bastard held up the delivery. Power Ups take 10 seconds longer to arrive.'},
        {'title': 'Holes In Your Pockets', 'goodbad': 'bad', 'selector': 'lessCoins',
         'icon': 'Roulette_icon_sonar',
         'description': 'Something is torn. You earn 15% fewer Coins this game.'},
    ),
    'level_3': (
        {'title': 'Quick Hands', 'goodbad': 'good', 'selector': 'fasterReloadTime',
         'icon': 'Roulette_icon_tripleshot',
         'description': 'Your hands fly! Reloading takes far less time.'},
        {'title': 'Heavy Hands', 'goodbad': 'bad', 'selector': 'slowerReloadTime',
         'icon': 'Roulette_icon_cogs',
         'description': 'Your hands are like lead. Reloading takes far longer.'},
    ),
}


@adds_to('Tarot')
def new_tarot_cards(tarot: dict) -> None:
    """Deal the port's own cards from the original's decks."""
    for level, cards in NEW_CARDS.items():
        deck = tarot.get(level)
        if not isinstance(deck, list):
            continue
        for card in cards:
            new_entry(deck, card)


@adds_to('Weapons')
def fifth_power_up_level(weapons: dict) -> None:
    """Give four of the power-ups a `level_5`, which only Powered Power Ups can reach.

    With the level in the data, `_level_dictionary`'s own rule - one level up when `level_<level+1>`
    exists - does the rest, so the port needs no special case of its own.
    """
    for name, level in FIFTH_POWER_UP_LEVEL.items():
        entry = named(weapons.get('PowerUps'), name)
        if entry is not None:
            new_key(entry, 'level_5', dict(level))
