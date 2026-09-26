"""Make or refresh a language file: every phrase the port can show or speak, ready to be filled in.

    py tools/make_language.py de            write localization/de.json, every phrase empty
    py tools/make_language.py ru            add to an existing one: what is translated stays

A language is a flat map from the English phrase to the phrase in that language.  This writes one holding
every phrase the port can put in front of a player - the text-carrying calls in its own code, and the
phrases of the game's own data - with an empty value for each, so a translator has the list rather than
having to find it.

Run it again whenever the port grows: a file that exists keeps every phrase already translated, and only
the ones that are new arrive empty.  Nothing is ever removed, because a phrase the port no longer uses may
still be one another language file wants, and an unused phrase costs nothing.

An empty value is left alone by the game (`localization.load` drops them), so a part-finished file is
perfectly usable: what is translated is translated, and the rest stays English.

When the file is finished, `py tools/verify_localization.py` says whether anything was missed, and the
language is offered once its code and name are in `LANGUAGES` (audiodefence/game/parameters.py).
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


def every_phrase() -> list:
    """Every phrase the player can read or hear, in the order a translator would meet them: the port's
    own text first, then the game's data.  The same phrase can be reached from several places; it is
    written once."""
    seen = {}
    for source in (verifier.code_phrases(), verifier.data_phrases()):
        for text, _where in source:
            if text in verifier.LEFT_ALONE:
                continue
            seen.setdefault(text, None)
    return sorted(seen)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('language', help="the language's code, as in localization/<code>.json (de, fr, ja)")
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

    phrases = every_phrase()
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
    print('Then: py tools/verify_localization.py --language %s' % args.language)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
