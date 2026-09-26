"""Check that every phrase the game can show or speak is translated in every language file.

The port's text comes from its own code - labels, hints, screen titles, the rows of Settings - and from the
original game's data: the plists and `en.lproj` inside the bundle.  This walks both, puts each phrase
through the localization layer, and fails when one of them stays in English, so a language cannot quietly
become incomplete as the port grows.

Run it with `--language ru` for one language, or with nothing to check every file under `localization/`.
The bundle is looked for where the game looks for it (the `game/` folder, or `--game`/AUDIODEFENCE_GAME),
so data phrases are only checked when the game's own files are there.  Exits non-zero and names what did
not hold; a phrase that is deliberately left in English belongs in LEFT_ALONE, with the reason beside it.

    python tools/verify_localization.py
    python tools/verify_localization.py --language ru
"""
from __future__ import annotations

import argparse
import ast
import copy
import io
import os
import plistlib
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from audiodefence import localization, paths                       # noqa: E402
from audiodefence.game import additions, data                    # noqa: E402  (corrected(), and the port's own content)

#: the file a translator works in until they rename it (tools/make_language.py)
TEMPLATE = 'template'

#: Phrase fields of the original game's data that the player reads or hears.  Compared without case: the
#: same field is spelt differently from file to file (Tips and tip, Description and description, Bio).
FIELDS = {'title', 'subtitle', 'description', 'objective', 'tip', 'tips', 'displayname', 'upgradetext',
          'name', 'text', 'bio'}

#: Lines the port speaks that are not phrases from the table, and are meant to stay as they are: screen
#: reader names, key names, the two states of a switch.
LEFT_ALONE = {
    'ON', 'OFF', 'NVDA', 'SAPI 5', 'Narrator', 'ZoomText', 'Window-Eyes', 'System Access', 'PC-Talker',
    'Sense Reader', 'Boy PC Reader', 'Page Up', 'Page Down', 'Shift', 'Shift plus Enter', 'Enter',
    'Escape', 'Tab', 'Control', 'Cross', 'Circle', 'Square', 'Triangle', 'L1', 'R1', 'L2', 'R2', 'L3',
    'R3', 'LB', 'RB', 'LT', 'RT', 'ZL', 'ZR',
}

#: Calls and keywords the port carries text for the player through: a label, a hint, a screen title, a line
#: that is spoken.  Everything else in the code - log messages, identifiers, regular expressions - is not
#: text the player can read or hear.
TEXT_CALLS = {'View', 'Button', 'MenuItem', 'MenuScreen', 'AlertScreen', 'Cell', 'Header', 'Row', 'Item',
              'cell', 'view', 'button', 'label', 'item', 'speak', 'announce', 'set_title', 'setText',
              'say', 'localized', 'AlertScreen',
              #: a phrase the code hands to the layer by name is text for the player by definition.  It is
              #: also the way to give a translator a phrase that sits inside a line with a substitution in
              #: it, which PLUMBING drops whole: hand the phrase over on its own and build the line round it.
              'translate'}
TEXT_KEYWORDS = {'label', 'hint', 'text', 'title', 'message', 'subtitle', 'caption', 'page_title',
                 'copy_label', 'objective', 'description', 'tip'}
#: `name=` is left out on purpose: it names an element for the port's own lookups ("#39 UITableView"),
#: not text the player reads.

#: Identifiers, paths, formats and code: not text for the player.
PLUMBING = (
    re.compile(r'^[\w.\-/\\@:]+$'),                             # one word: an id, a key, a path
    re.compile(r'^\s*$'),
    re.compile(r'^%[-+ #0-9.*]*[a-zA-Z]$'),                     # a bare substitution
    re.compile(r'^(https?://|www\.)'),
    re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\s*=\s*'),
    re.compile(r'^[a-z][a-z0-9_]*$'),                           # sound_name, level_3
    re.compile(r'^\d'),
    re.compile(r'\\|\^|\{|\}|\[|\]|\|'),                        # a regular expression or a format
    re.compile(r'%[-+ #0-9.*]*[a-zA-Z]'),                       # a template, not a phrase of its own
    re.compile(r'[А-Яа-яЁё]'),                                  # already in the target language
)


def is_plumbing(text: str) -> bool:
    return any(pattern.search(text) for pattern in PLUMBING)


def _called_name(node) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ''


def _log_calls(tree) -> set:
    """The string literals that go to the log rather than to the player."""
    marked = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _called_name(node) in (
                'debug', 'info', 'warning', 'error', 'exception', 'critical'):
            for item in ast.walk(node):
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    marked.add(id(item))
    return marked


def _text_constants(node):
    """The string literals inside one call that the port carries text through."""
    name = _called_name(node)
    for keyword in node.keywords or ():
        if keyword.arg not in TEXT_KEYWORDS:
            continue
        for item in ast.walk(keyword.value):
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                yield item
    if name not in TEXT_CALLS:
        return
    for argument in node.args:
        for item in ast.walk(argument):
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                yield item
            elif isinstance(item, ast.JoinedStr):
                for piece in item.values:
                    if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                        yield piece


def code_phrases():
    """The string literals in the port's own code that reach the player."""
    for folder, dirs, files in os.walk(os.path.join(ROOT, 'audiodefence')):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(folder, name)
            if name == 'localization.py':                       # the layer itself: its rules, not phrases
                continue
            with io.open(path, encoding='utf-8') as fh:
                try:
                    tree = ast.parse(fh.read())
                except SyntaxError as exc:                      # a broken file is the other verifier's job
                    print('  cannot read %s: %s' % (path, exc))
                    continue
            docstrings = set()
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                body = getattr(node, 'body', [])
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
            logged = _log_calls(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for item in _text_constants(node):
                    if id(item) in docstrings or id(item) in logged:
                        continue
                    text = ' '.join(item.value.split())
                    if len(text) < 3 or not re.search('[A-Za-z]', text) or is_plumbing(text):
                        continue
                    yield text, '%s:%d' % (os.path.relpath(path, ROOT), item.lineno)


def _as_read(text: str):
    """The phrase as their file writes it, and as the game reads it in, when those differ."""
    written = ' '.join(text.split())
    read = ' '.join(data.corrected(text).split())
    return (written,) if read == written else (written, read)


def data_phrases():
    """The phrases of the original game's data, as the game reads them in.

    Each one is offered both as it is written in their file and as `data.corrected` hands it to the
    screens, when those differ.  The corrected form is what the player is actually told, so it is the form
    a translator needs; the written one stays in the list because the language files already carry it and
    a phrase is never taken away from them.

    The port's own content is walked as well (`game/additions.py`), because a card or a level the port
    adds is text a player reads and is in no file here.  A phrase is offered once however many ways it
    is reached."""
    bundle = paths.BUNDLE
    if not os.path.isdir(bundle):
        print('the game folder is not there (%s): the data phrases are not checked' % bundle)
        return
    seen = set()
    for folder, dirs, files in os.walk(bundle):
        dirs[:] = [d for d in dirs if d not in ('sounds', '__pycache__')]
        for name in files:
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, bundle)
            if name.endswith('.plist'):
                try:
                    with open(path, 'rb') as fh:
                        loaded = plistlib.load(fh)
                except Exception:                               # noqa: BLE001 - not ours to report here
                    continue
                # what the game reads: their file, plus whatever the port adds to it
                trees = [(loaded, rel)]
                added = additions.apply_to(os.path.splitext(name)[0], copy.deepcopy(loaded))
                if added is not None:
                    trees.append((added, '%s [port addition]' % rel))
                for tree, where in trees:
                    for field, text in _walk_plist(tree):
                        if field.lower() in FIELDS and len(text) > 2 and not is_plumbing(text):
                            for phrase in _as_read(text):
                                if phrase in seen:
                                    continue
                                seen.add(phrase)
                                yield phrase, '%s [%s]' % (where, field)
            elif name.endswith('.strings'):
                for text in _strings_file(path):
                    if not is_plumbing(text):
                        for phrase in _as_read(text):
                            yield phrase, rel


def _walk_plist(value, field: str = ''):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                yield str(key), item
            else:
                yield from _walk_plist(item, str(key))
    elif isinstance(value, list):
        for item in value:
            yield from _walk_plist(item, field)
    elif isinstance(value, str):
        yield field, value


def _strings_file(path: str):
    with io.open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            match = re.match(r'\s*"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', line)
            if match:
                yield match.group(2)


def check(language: str) -> list:
    if not localization.load(language, force=True):
        return ['localization/%s.json cannot be read' % language]
    table = localization.phrases()
    misses = []
    examined = 0
    covered = 0
    print('  %s: %d phrases' % (language, len(table)))
    for source in (code_phrases(), data_phrases()):
        for text, where in source:
            if text in LEFT_ALONE:
                continue
            examined += 1
            if text in table or localization.translate(text) != text:
                covered += 1
                continue
            # A short piece the port glues into a longer line ("rate boost" into "SAPI 5 rate boost") is
            # covered when a phrase in the table holds it.
            if len(text) < 30 and any(text in key for key in table):
                covered += 1
                continue
            misses.append((text, where))
    print('  %d phrases the player can read or hear, %d of them translated' % (examined, covered))
    return ['%s   (%s)' % (text[:110], where) for text, where in misses]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--language', action='append', default=[],
                        help='a language to check; the default is every file under localization/')
    args = parser.parse_args()

    # The template is a language being written (tools/make_language.py), so it is unfinished by
    # definition and would fail every run it was swept into.  Named on the command line it is checked
    # like any other, which is how its author sees how far they have got.
    languages = args.language or [code for code in localization.available()
                                  if code not in (localization.ENGLISH, TEMPLATE)]
    if not languages:
        print('no language files under localization/: nothing to check')
        return 0

    failed = False
    for language in languages:
        print('checking %s' % language)
        problems = check(language)
        if problems:
            failed = True
            print('  %d phrases are still English:' % len(problems))
            for line in problems[:40]:
                print('    ' + line)
            if len(problems) > 40:
                print('    ... and %d more' % (len(problems) - 40))
    if failed:
        print('FAILED: a phrase the player can read or hear has no translation')
        return 1
    print('all phrases are translated')
    return 0


if __name__ == '__main__':
    sys.exit(main())
