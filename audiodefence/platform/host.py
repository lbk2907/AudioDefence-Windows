"""PORT ADDITION: which operating system the port is running on, decided once.

The port was written for Windows, and it runs on the Mac as well.  Every choice that differs between
the two - the OpenAL Soft library, what speaks, where the settings live, the SDL library the controller
code reaches past pygame, the key that quits - is decided here or by the module this names, so the
game itself never asks ``sys.platform``.

Windows and Mac, one for one:

=================================  ==========================================
Windows                            Mac
=================================  ==========================================
``vendor/openal/soft_oal.dll``     ``vendor/openal-mac/libopenal.dylib`` (the same OpenAL Soft)
NVDA, Prism, SAPI 5                VoiceOver, then the system voice (platform/macspeech.py)
``%APPDATA%\\AudioDefence``         ``~/Library/Application Support/AudioDefence``
``SDL2.dll`` beside pygame         ``libSDL2-2.0.0.dylib`` in pygame's ``.dylibs``
``AudioDefence.exe``               ``AudioDefence.app``
PowerShell swaps an update in      a shell script swaps it in (platform/updater.py)
Alt+F4                             Cmd+Q
=================================  ==========================================
"""
from __future__ import annotations

import sys

WINDOWS = sys.platform == 'win32'
MAC = sys.platform == 'darwin'

#: how the port names itself: in the log, the credits, and the release archive's name
PORT_NAME = 'Mac' if MAC else 'Windows'
#: the release archive's platform tag
ARCHIVE_TAG = 'Mac' if MAC else 'Win'
#: what each platform's release zip is called, before its version.  The Mac's has no dash after
#: AudioDefence, and has to stay that way: GitHub's API lists a release's assets by name, ignoring case,
#: whatever order they were uploaded in, and every Windows build from before the Mac port takes the first
#: zip it is given.  A dash sorts before any letter, so 'AudioDefence-Win-' comes before 'AudioDefenceMac-'.
#: 'AudioDefence-Mac-' would come first, and an old Windows build would unpack the Mac app into its folder
#: and delete everything in _internal and game as files the new build had dropped.
ARCHIVE_PREFIXES = {'Win': 'AudioDefence-Win-', 'Mac': 'AudioDefenceMac-'}


def archive_name(version: str = '', tag: str = ARCHIVE_TAG) -> str:
    """The release zip's name: 'AudioDefence-Win-26.09.22-1.zip', or 'AudioDefenceMac-26.09.22-1.zip'."""
    prefix = ARCHIVE_PREFIXES[tag]
    return (prefix + version if version else prefix.rstrip('-')) + '.zip'


def quit_hint() -> str:
    """How you leave the game from outside it: no key in the game quits."""
    return 'Cmd+Q' if MAC else 'Alt+F4'


def user_dir_hint() -> str:
    """Where the settings, saves and crash.txt are, in words a player can find."""
    return ('in the AudioDefence folder in Application Support, in your Library folder' if MAC else
            'in the AudioDefence folder in AppData')
