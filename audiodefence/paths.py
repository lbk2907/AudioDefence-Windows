"""Filesystem locations used by the port.

The game's own data - the plists, the `en.lproj` strings, the S3D playlist models under `meta/` and the
sounds under `sounds/` - is read straight out of the original app bundle, in the layout the bundle already
has, so nothing is copied or converted.  The bundle's contents sit in ``game/`` inside the project.

``game/`` is where it is looked for, unless the AUDIODEFENCE_GAME environment variable (``--game`` on the
command line) points somewhere else - another copy of the bundle, or a folder holding one.  In a PyInstaller
build the code, ``assets/`` and ``vendor/`` come out of the unpacked bundle, while ``game/`` is the copy
sitting next to the executable: the game's own files are not something a build can carry.  The Mac build
is the exception: its ``game/`` goes inside ``AudioDefence.app`` (``Contents/Resources/game``), because
macOS may run a downloaded app from a private copy of the bundle alone (App Translocation), where nothing
beside it can be seen.
"""
from __future__ import annotations

import os
import sys

from .platform import host

FROZEN = getattr(sys, 'frozen', False)
if FROZEN:
    ROOT = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))        # what PyInstaller bundled
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))              # what sits beside the .exe
    if host.MAC and os.path.basename(EXE_DIR) == 'MacOS':                   # .../AudioDefence.app/Contents/MacOS
        APP_BUNDLE = os.path.dirname(os.path.dirname(EXE_DIR))
        EXE_DIR = os.path.dirname(APP_BUNDLE)                               # what sits beside the .app
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    EXE_DIR = ROOT

ASSETS = os.path.join(ROOT, 'assets')
HRTF_DIR = os.path.join(ASSETS, 'hrtf')
VENDOR = os.path.join(ROOT, 'vendor')
#: PORT ADDITION: the phrase files the optional localization reads (audiodefence/localization.py).
#: Bundled like assets/, so a language file lives inside the build.
LOCALIZATION = os.path.join(ROOT, 'localization')
OPENAL_DLL = (os.path.join(VENDOR, 'openal-mac', 'libopenal.dylib') if host.MAC else
              os.path.join(VENDOR, 'openal', 'soft_oal.dll'))
NVDA_DLL = os.path.join(VENDOR, 'nvda', 'nvdaControllerClient64.dll')

GAME_ENV = 'AUDIODEFENCE_GAME'
APP_NAME = 'audiodefence.app'


def _candidates():
    env = os.environ.get(GAME_ENV)
    if env:                                             # a path, or an IPA / Payload folder holding the app
        yield 'the %s environment variable' % GAME_ENV, env
        yield 'the %s environment variable' % GAME_ENV, os.path.join(env, 'Payload', APP_NAME)
        yield 'the %s environment variable' % GAME_ENV, os.path.join(env, APP_NAME)
    yield 'the game folder', os.path.join(ROOT, 'game')
    if FROZEN and host.MAC and 'APP_BUNDLE' in globals():   # the Mac build carries it inside the .app
        yield 'the game folder inside the app', os.path.join(APP_BUNDLE, 'Contents', 'Resources', 'game')
    if EXE_DIR != ROOT:                                 # frozen: a game folder next to the executable
        yield 'the game folder next to the executable', os.path.join(EXE_DIR, 'game')


def _is_game_data(path: str) -> bool:
    """The data the port reads: the playlist models and the sounds live here."""
    return os.path.isdir(os.path.join(path, 'meta')) and os.path.isdir(os.path.join(path, 'sounds'))


def find_bundle():
    for source, path in _candidates():
        if path and _is_game_data(path):
            return os.path.normpath(path), source
    return os.path.join(EXE_DIR, 'game'), 'the game folder (missing)'


BUNDLE, BUNDLE_SOURCE = find_bundle()               # the game's data, wherever it is
PLAYLIST_META = os.path.join(BUNDLE, 'meta', 'S3DPlayListModel')


def user_dir() -> str:
    """Where settings and saves live (the NSUserDefaults equivalent): %APPDATA% on Windows, Application
    Support on the Mac."""
    if host.MAC:
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support')
    else:
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    path = os.path.join(base, 'AudioDefence')
    os.makedirs(path, exist_ok=True)
    return path


def bundle_path(*parts: str) -> str:
    return os.path.join(BUNDLE, *parts)
