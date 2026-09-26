"""PORT ADDITION: an optional localization layer, so a player can read and hear the port's own text in
another language than English.

Where the text comes from.  The port's text is its own - labels, hints, screen titles, the settings rows -
and the original game's, read out of the bundle's plists and `en.lproj`.  Neither is rewritten: everything
the player sees or hears passes through `View.label`, `View.hint`, `View.text`, `MenuItem.label`,
`MenuItem.hint`, `MenuScreen.title`, `AccessibleScreen.page_title`, `data.localized` and, in the end,
`Speech.speak`, so the text is translated on the way out.

How it is stored.  One JSON file per language under `localization/`, a flat map of an English phrase to
the phrase in that language, for example `localization/ru.json`.  Translations are data, so a language is
added by writing a file, not by touching code.  Nothing is translated while the language is English, which
is the default: a player who does not choose one sees exactly what the port always showed.

Whole phrases are the keys rather than single words, so a translation does not depend on how the port
assembled a line.  A phrase with substitutions (`%i`, `%s`) becomes a rule: the number is substituted and,
in languages that need it, the counted word is inflected - Russian wants "1 монета", "2 монеты", "5 монет".
"""
from __future__ import annotations

import json
import logging
import os
import re

from . import paths

log = logging.getLogger('localization')

#: The language the port is written in, and the one used when nothing is chosen.
ENGLISH = 'en'

#: What a counted word looks like in the target language, after a number: one, few, many.
UNITS = {
    'coin': ('монета', 'монеты', 'монет'),
    'coins': ('монета', 'монеты', 'монет'),
    'diamond': ('алмаз', 'алмаза', 'алмазов'),
    'diamonds': ('алмаз', 'алмаза', 'алмазов'),
    'kill': ('убийство', 'убийства', 'убийств'),
    'kills': ('убийство', 'убийства', 'убийств'),
    'zombie': ('зомби', 'зомби', 'зомби'),
    'zombies': ('зомби', 'зомби', 'зомби'),
    'point': ('очко', 'очка', 'очков'),
    'points': ('очко', 'очка', 'очков'),
    'bullet': ('патрон', 'патрона', 'патронов'),
    'bullets': ('патрон', 'патрона', 'патронов'),
    'second': ('секунда', 'секунды', 'секунд'),
    'seconds': ('секунда', 'секунды', 'секунд'),
    'minute': ('минута', 'минуты', 'минут'),
    'minutes': ('минута', 'минуты', 'минут'),
    'line': ('строка', 'строки', 'строк'),
    'lines': ('строка', 'строки', 'строк'),
    'per cent': ('процент', 'процента', 'процентов'),
    'challenge': ('испытание', 'испытания', 'испытаний'),
    'challenges': ('испытание', 'испытания', 'испытаний'),
    'wave': ('волна', 'волны', 'волн'),
    'waves': ('волна', 'волны', 'волн'),
    'brick': ('кирпич', 'кирпича', 'кирпичей'),
    'bricks': ('кирпич', 'кирпича', 'кирпичей'),
    'star': ('звезда', 'звезды', 'звёзд'),
    'stars': ('звезда', 'звезды', 'звёзд'),
    'level': ('уровень', 'уровня', 'уровней'),
    'levels': ('уровень', 'уровня', 'уровней'),
}

#: A substitution in a template.  No space in the flags, so a bare percent sign in the game's own writing
#: ("10% damage") is not taken for one.
_SPEC = re.compile(r'%[-+#0]*[0-9]*(?:\.[0-9]+)?[a-zA-Z]')

#: How the port joins the pieces of one line: "Gyro, Turns slowest", "Aiming. Selected", "A and B".
_SEGMENT_COMMA = re.compile(r'(, |; |: | -- )')
_SEGMENT_SENTENCE = re.compile(r'(\. )')
_SEGMENT_JOIN = re.compile(r'( and | or )')
_SEPARATORS = ('. ', ', ', '; ', ': ', ' -- ')

_table: dict = {}
_rules: list = []
_weak_rules: list = []
_lower: dict = {}
_scan: list = []
_language: str | None = None

# --- the phrase table --------------------------------------------------------------------------

def file_for(language: str) -> str:
    return os.path.join(paths.LOCALIZATION, '%s.json' % language)


def available() -> tuple:
    """The languages a build carries, the port's own first: ('en', 'ru') for a build with a Russian file."""
    codes = [ENGLISH]
    folder = paths.LOCALIZATION
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith('.json'):
                code = name[:-len('.json')]
                if code != ENGLISH and code not in codes:
                    codes.append(code)
    return tuple(codes)


def load(language: str, force: bool = False) -> bool:
    """Read that language's file, and build its rules.  English - or a file that is not there - clears
    everything, which leaves `translate` returning what it is given."""
    global _table, _language, _rules, _weak_rules, _lower, _scan
    if not force and language == _language:
        return bool(_table)
    _language = language
    _table, _rules, _weak_rules, _lower, _scan = {}, [], [], {}, []
    if language == ENGLISH:
        return False
    path = file_for(language)
    try:
        with open(path, encoding='utf-8') as fh:
            phrases = json.load(fh)
    except (OSError, ValueError) as exc:
        log.warning('localization: cannot read %s: %s', path, exc)
        return False
    if not isinstance(phrases, dict):
        log.warning('localization: %s is not a map of phrases', path)
        return False
    _table = {str(key): str(value) for key, value in phrases.items() if value}
    _rules, _weak_rules = _build_rules(_table)
    _lower = {key.lower(): value for key, value in _table.items()}
    _scan = _build_scan(_table)
    log.info('localization: %s, %d phrases', language, len(_table))
    return True


def language() -> str:
    """The language the player chose, or English.  Imported here rather than at the top: the settings
    singleton imports this module's callers."""
    try:
        from .game.parameters import GameParameters
        return GameParameters.shared().language()
    except Exception:                                    # noqa: BLE001 - before the settings exist
        return ENGLISH


def follow() -> None:
    """Load the chosen language if it is not the one already loaded.  Called by whoever translates."""
    chosen = language()
    if chosen != _language:
        load(chosen)


def phrases() -> dict:
    """The phrases loaded now: what the verifier walks through."""
    return _table


# --- numbers and plurals -----------------------------------------------------------------------

def _plural(number, one: str, few: str, many: str) -> str:
    """The form a counted word takes after a number: 1 монета, 2 монеты, 5 монет.  A fractional number
    takes the middle form, as 12.34 процента does."""
    value = abs(float(number))
    if value != int(value):
        return few
    n = int(value)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# --- rules built from the table ----------------------------------------------------------------

def _escape_literal(text: str) -> str:
    """Escape the fixed part of a key, letting a colon be spaced either way: "X : buy" and "X: buy" are
    the same line to the player."""
    out = []
    for piece in re.split(r'(\s*:\s*)', text):
        out.append(r'\s*:\s*' if re.fullmatch(r'\s*:\s*', piece) else re.escape(piece))
    return ''.join(out)


def _template_regex(key: str):
    """The rule for a phrase with substitutions.

    Returns the pattern, how many substitutions there are, the counted word after each of them (when the
    English phrase has one) and whether each substitution is a number.
    """
    key = key.replace('%%', '%')                        # %% prints one percent sign in the source
    parts = []
    units = {}
    numeric = []
    position = 0
    index = 0
    for match in _SPEC.finditer(key):
        parts.append(_escape_literal(key[position:match.start()]))
        spec = match.group(0)
        is_number = spec[-1] in 'diu'
        numeric.append(is_number)
        parts.append(r'(-?\d[\d\s\u00a0]*)' if is_number else r'(.+?)')
        word = re.match(r'\s+([A-Za-z ]+)', key[match.end():])
        if word:
            unit = word.group(1).strip()
            if unit in UNITS:
                units[index] = UNITS[unit]
        index += 1
        position = match.end()
    parts.append(_escape_literal(key[position:]))
    return re.compile('^' + ''.join(parts) + '$'), index, units, numeric


def _make_rule(value: str, count: int, units: dict, numeric: list):
    """The rule itself: substitute the numbers, inflect the counted words, and translate whatever the port
    put into the template, since that is text too - a key name, a weapon, a card."""
    value = value.replace('%%', '%')

    def rule(match):
        numbers = {}
        for index in range(count):
            raw = match.group(index + 1)
            if not raw:
                continue
            digits = re.sub(r'[^\d]', '', raw)
            if digits and (numeric[index] or digits == raw.strip()):
                numbers[index] = digits
        out = ''
        position = 0
        index = 0
        for spec in _SPEC.finditer(value):
            out += value[position:spec.start()]
            if index in numbers:
                out += numbers[index]
            else:
                group = match.group(index + 1)
                if group and re.search(r'[A-Za-z]{3,}', group) and not re.search(r'[А-Яа-яЁё]', group):
                    group = translate(group)
                out += group
            position = spec.end()
            forms = units.get(index)
            if forms and index in numbers:
                word = re.match(r'(\s*)([А-Яа-яЁё]+)', value[position:])
                if word:
                    out += word.group(1)
                    out += _plural(numbers[index], *forms)
                    position += word.end()
            index += 1
        out += value[position:]
        return out
    return rule


def _build_rules(table: dict):
    """Rules from the table: the exact ones first, then the general ones.

    Order matters: a general rule for "%s diamonds" would otherwise catch "Buy for 100 diamonds" and
    translate only its last word.
    """
    rules = []
    for key, value in table.items():
        if not value or '%' not in key:
            continue
        regex, count, units, numeric = _template_regex(key)
        literal = len(_SPEC.sub('', key))
        specs = len(_SPEC.findall(key))
        rules.append((specs, -literal, regex, _make_rule(value, count, units, numeric)))
    rules.sort(key=lambda item: (item[0], item[1]))
    strong, weak = [], []
    for specs, neg_literal, regex, rule in rules:
        (strong if specs >= 2 or -neg_literal >= 12 else weak).append((regex, rule))
    return strong, weak


def _build_scan(table: dict):
    """Phrases to look for inside a long line the port glued together, longest first.

    Only phrases of several words: single words are caught by an exact match, and searching for them
    rewrites the case of a word in the middle of a sentence.
    """
    items = []
    for key, value in table.items():
        if not value or '%' in key or len(key) < 8 or ' ' not in key:
            continue
        pattern = re.compile(r'(?<![\w])%s(?![\w])' % re.escape(key))
        items.append((len(key), pattern, value))
    items.sort(key=lambda item: -item[0])
    return [(pattern, value) for _length, pattern, value in items]


# --- phrases the port assembles -----------------------------------------------------------------

#: Lines the port builds by substitution rather than taking whole from the table.  These are Russian
#: rules; a third language would put its own beside them, which is why they are here and not in the data.
def _ru(text: str) -> str:
    """Translate what the port substituted into a template: a key's name, a weapon, the word "or"."""
    text = translate(text)
    for english, target in ((' or ', ' или '), (' and ', ' и ')):
        if english in text:
            text = target.join(translate(part) for part in text.split(english))
    return text


_MANUAL = (
    # "the R2 button or the L2 button": an action with two buttons, which the port glues with a
    # conjunction.  The general "the %s button" rule would take too much ("L2 button or the R2").
    (re.compile(r'^the (.+?) button or the (.+?) button$'),
     lambda m: 'кнопка %s или кнопка %s' % (_ru(m.group(1)), _ru(m.group(2)))),
    (re.compile(r'^(\d+)\s+stars?\s+unlocked$'), lambda m: 'Открыто звёзд: %d' % int(m.group(1))),
    (re.compile(r'^(\d+)\s+of\s+(\d+)$'), lambda m: '%s из %s' % (m.group(1), m.group(2))),
    (re.compile(r'^Kills (\d+)$'), lambda m: 'Убийств: %d' % int(m.group(1))),
    (re.compile(r'^kills$'), lambda m: 'убийств'),
    (re.compile(r'^Accuracy ([\d.,]+)\s*%$'),
     lambda m: 'Точность: %s %s' % (m.group(1), _plural(m.group(1).replace(',', '.'), 'процент',
                                                        'процента', 'процентов'))),
    (re.compile(r'^accuracy$'), lambda m: 'точность'),
    (re.compile(r'^Survival time (.+)$'), lambda m: 'Время выживания: %s' % m.group(1)),
    (re.compile(r'^owned\s*:\s*level\s+(\d+)$'), lambda m: 'куплено, уровень %d' % int(m.group(1))),
    (re.compile(r'^owned$'), lambda m: 'куплено'),
    (re.compile(r'^level\s+(\d+)$'), lambda m: 'уровень %d' % int(m.group(1))),
    # The tutorial's own lines: the port substitutes the name of a key or a button.
    (re.compile(r'^Use your (.+?) or (.+?) key to aim\.$'),
     lambda m: 'Поворачивайся клавишами %s или %s, чтобы целиться.' % (_ru(m.group(1)), _ru(m.group(2)))),
    (re.compile(r'^Listen carefully and turn until you feel the zombie is right in front of you, '
                r'then use the (.+?) key to fire your weapon\.$'),
     lambda m: 'Слушай внимательно и поворачивайся, пока не почувствуешь, что зомби прямо перед тобой, '
               'затем нажми %s, чтобы выстрелить.' % _ru(m.group(1))),
    (re.compile(r'^Use the (.+?) key to reload your weapon\.$'),
     lambda m: 'Нажми %s, чтобы перезарядить оружие.' % _ru(m.group(1))),
    (re.compile(r'^You can change your aim control at any time in the pause menu, '
                r'which can be accessed using the (.+?) key\.$'),
     lambda m: 'Сменить способ прицеливания можно в любой момент в меню паузы, '
               'оно открывается клавишей %s.' % _ru(m.group(1))),
    (re.compile(r'^Use the (.+?) key to switch between weapons\.$'),
     lambda m: 'Нажми %s, чтобы сменить оружие.' % _ru(m.group(1))),
    (re.compile(r'^You can use the (.+?) key to skip dialogs\.$'),
     lambda m: 'Пропустить диалог можно клавишей %s.' % _ru(m.group(1))),
    (re.compile(r'^To use the melee weapon, turn to face the zombies first\. '
                r'Then, press the (.+?) key\.$'),
     lambda m: 'Чтобы ударить в ближнем бою, сначала повернись к зомби. Затем нажми %s.' % _ru(m.group(1))),
    # The aiming hint appears in three spellings in the game's data (hear the Zombie, feel a Zombie,
    # feel a zombie); one rule covers them.
    (re.compile(r'^Aim with your ears\.\s*Shoot when you (?:hear|feel) (?:the |a )?'
                r'[Zz]ombies? right in front of you\.$'),
     lambda m: 'Целься на слух. Стреляй, когда чувствуешь, что зомби прямо перед тобой.'),
    (re.compile(r'^Revive for (\d+) diamonds?$'),
     lambda m: 'Возродиться за %s %s' % (m.group(1), _plural(int(m.group(1)), 'алмаз', 'алмаза', 'алмазов'))),
    (re.compile(r'^Respawn for (\d+) diamonds?$'),
     lambda m: 'Возродиться за %s %s' % (m.group(1), _plural(int(m.group(1)), 'алмаз', 'алмаза', 'алмазов'))),
)


def _apply_rules(text: str, rules):
    for regex, rule in rules:
        match = regex.match(text)
        if match:
            return rule(match)
    return None


def _parts(text: str, splitter):
    """Translate piece by piece.  None when not one piece was found."""
    parts = splitter.split(text)
    if len(parts) == 1:
        return None                                      # nothing to split, and no recursion
    changed = False
    out = []
    for part in parts:
        if part in _SEPARATORS:
            out.append(part)
            continue
        stripped = part.strip()
        found = _table.get(stripped) or _table.get(part)
        if found:
            changed = True
            out.append(found)
            continue
        replaced = _apply_rules(stripped, _MANUAL) or _apply_rules(stripped, _rules) \
            or _apply_rules(stripped, _weak_rules)
        if replaced is not None:
            changed = True
            out.append(replaced)
            continue
        # A piece may hold more than one sentence ("Main Menu. Play"), and its parts may be joined by a
        # conjunction ("More Power Ups! and Glue Barrels"); the port assembles lines both ways.
        nested = None
        if splitter is not _SEGMENT_SENTENCE:
            nested = _parts(part, _SEGMENT_SENTENCE)
        if nested is None and splitter is not _SEGMENT_JOIN:
            nested = _parts(part, _SEGMENT_JOIN)
        if nested is not None:
            changed = True
            out.append(nested)
        else:
            out.append(part)
    return ''.join(out) if changed else None


def _translate_segments(text: str):
    """Translate by pieces: first a head that is itself a phrase, then by commas, then by sentences, then
    by the conjunctions the port joins with.

    The head is tried first because a weapon's description is full of commas of its own: the whole line is
    in the table while its pieces are not.
    """
    for match in _SEGMENT_COMMA.finditer(text):
        head = text[:match.start()].strip()
        if not head:
            continue
        translated = (_table.get(head) or _apply_rules(head, _MANUAL) or _apply_rules(head, _rules))
        if translated:
            return translated + match.group(0) + translate(text[match.end():])
    by_comma = _parts(text, _SEGMENT_COMMA)
    if by_comma is not None:
        return by_comma
    by_sentence = _parts(text, _SEGMENT_SENTENCE)
    if by_sentence is not None:
        return by_sentence
    return _parts(text, _SEGMENT_JOIN)


def translate(text):
    """The line in the chosen language, or the line itself when there is no translation for it."""
    if not isinstance(text, str) or not text:
        return text
    if _language is None:
        follow()
    if not _table:
        return text                                      # English, or no language file
    exact = _table.get(text)
    if exact:
        return exact
    if '\n' in text:
        # Multi-line text: the whole thing first (the port glues paragraphs and captions), then line by
        # line, which is how the credits - a role or a name on each line - are translated.
        flat_lines = ' '.join(text.split())
        found = _table.get(flat_lines)
        if found:
            return found
        lines = text.split('\n')
        translated = [translate(line) for line in lines]
        if translated != lines:
            return '\n'.join(translated)
    flat = ' '.join(text.split())                        # line breaks are for the label, not for speech
    if flat != text:
        found = _table.get(flat)
        if found:
            return found
    for rules in (_MANUAL, _rules):
        replaced = _apply_rules(flat, rules)
        if replaced is not None:
            return replaced
    by_parts = _translate_segments(flat)
    if by_parts is not None:
        return by_parts
    replaced = _apply_rules(flat, _weak_rules)
    if replaced is not None:
        return replaced
    # Last pass: a long line with an English phrase somewhere inside text that is already translated.
    if re.search(r'[A-Za-z]{4,}', flat):
        scanned = flat
        for pattern, value in _scan:
            scanned = pattern.sub(value.replace('\\', '\\\\'), scanned)
        if scanned != flat:
            return scanned
    # Labels the port writes in capitals, which the table holds in the ordinary case.
    upper = _lower.get(flat.lower())
    if upper:
        return upper
    return text
