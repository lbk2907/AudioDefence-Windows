"""Write localization/template.json: every phrase the port can show or speak, ready to be filled in.

    py tools/make_language.py                double-click it, or run it with nothing after it

Run it and it writes `localization/template.json`, a flat map from each English phrase to an empty one.
Those phrases are everything the port can put in front of a player - the text-carrying calls in its own
code, and the phrases of the game's own data - so a translator has the list rather than having to find it.

Fill the empty ones in, in any order.  An empty phrase is left alone by the game, so the file works from
the first line: what is translated is translated, and the rest stays English.  While it is there the game
offers it in Settings as a language of its own, so it can be heard while it is being written, without a
code being chosen or anything being renamed.

When it is ready, rename it to the language's code - `de.json`, `fr.json`, `ja.json` - and add that code
and the language's own name to `LANGUAGES` (audiodefence/game/parameters.py).  `template.json` is not
committed: it belongs to whoever is writing it.

Run this again whenever the port gains text.  A file that is already there keeps every phrase translated
and only the new ones arrive empty; nothing is ever removed.  Pass a language code to do the same for one
that has been renamed already (`py tools/make_language.py ru`).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import verify_localization as verifier                             # noqa: E402  (its collectors are the point)
from audiodefence import paths                                     # noqa: E402

#: what a translator works in until they choose a code for it (GameParameters.TEMPLATE_LANGUAGE)
TEMPLATE = 'template'


def every_phrase(besides: str = '') -> list:
    """Every phrase a translator should be given.

    Two sources, because neither is enough on its own.  The first is what `verify_localization.py` walks -
    the text-carrying calls in the port's own code, and the phrases of the game's data.  The second is the
    phrases the languages already written know, because the first has a blind spot: a phrase of one word
    ("Play", "Settings", "Quit", "Armory") looks exactly like an identifier, and `is_plumbing` has to treat
    it as one or the list would fill with sound names and keys.  Those words are some of the first a player
    meets, and a language that had only the first source would leave the main menu in English.

    So a new file starts with everything the languages before it found, and anyone writing the first
    language for a project still gets the walked list.  `besides` is the file being written, whose own
    phrases are already in hand.
    """
    seen = {}
    for source in (verifier.code_phrases(), verifier.data_phrases()):
        for text, _where in source:
            if text in verifier.LEFT_ALONE:
                continue
            seen.setdefault(text, None)
    folder = paths.LOCALIZATION
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.json') or name == besides:
                continue
            try:
                with io.open(os.path.join(folder, name), encoding='utf-8') as fh:
                    known = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(known, dict):
                for text in known:
                    seen.setdefault(text, None)
    return sorted(seen)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('language', nargs='?', default=TEMPLATE,
                        help="a language already renamed from the template (ru, de); the default writes "
                             'localization/%s.json' % TEMPLATE)
    parser.add_argument('--into', help='write somewhere else than localization/<code>.json')
    args = parser.parse_args(argv)

    path = args.into or os.path.join(paths.LOCALIZATION, '%s.json' % args.language)
    had = {}
    if os.path.isfile(path):
        try:
            with io.open(path, encoding='utf-8') as fh:
                had = json.load(fh)
        except ValueError as exc:
            print('%s is there but is not readable as JSON: %s' % (path, exc))
            return 1
        if not isinstance(had, dict):
            print('%s is not a map of phrases' % path)
            return 1

    phrases = every_phrase(besides=os.path.basename(path))
    table = dict(had)
    added = 0
    for text in phrases:
        if text not in table:
            table[text] = ''
            added += 1

    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + '\n')

    done = sum(1 for value in table.values() if value)
    where = os.path.relpath(path, ROOT)
    if had:
        print('%s: %d phrases the port can show, %d of them new here.' % (where, len(phrases), added))
    else:
        print('%s: written with %d phrases, every one of them empty.' % (where, len(phrases)))
    print('%d of %d translated. Fill in the empty ones, in the same order or any other.' % (done, len(table)))
    if done < len(table):
        print('An empty phrase stays English, so the file can be used before it is finished.')
    if args.language == TEMPLATE:
        print('The game offers it in Settings as a language while it is there, so it can be heard as it is')
        print('written. When it is ready, rename it to the language code and add that code to LANGUAGES.')
    print('Then: py tools/verify_localization.py --language %s' % args.language)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
