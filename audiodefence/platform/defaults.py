"""NSUserDefaults equivalent: JSON files in the user's AppData folder.

The original keeps one plist; the port splits it into save.json, settings.json and keys.json and routes
each key to its file by name (see SplitDefaults), so progress, preferences and input stay apart.

Getter semantics follow Foundation: ``integer``/``float``/``bool`` return 0 / 0.0 / False for missing keys
and convert strings and numbers like -integerForKey: etc.; ``object`` returns None for missing keys.
Dates are stored as {"__date__": unix_time}.
"""
from __future__ import annotations

import json
import os
import tempfile
import time

from .. import paths


#: PORT ADDITION: the original keeps everything in one NSUserDefaults plist.  The port splits it three ways,
#: so that progress, preferences and input each live in a file of their own - the key bindings in particular
#: are about to be joined by joystick bindings, and nobody wants those in the middle of a save.
#: Keys not named here are progress and go to save.json, which is the safe default for anything new.
SETTINGS_KEYS = frozenset({'buttonMode', 'controlScheme', 'sensivity', 'menuAxis', 'debugMapVisible',
                          'tutorialText', 'rememberFocus', 'checkUpdates', 'skippedUpdate',
                          'menuMusicVolume', 'vibration', 'triggerEffects', 'keyNames',
                          'keyNamesController', 'speechOutput', 'fineHaptics', 'sapiVoice', 'sapiRate',
                          'sapiRateBoost',
                          'sapiPitch', 'sapiVolume', 'sapiModernAudio'})
INPUT_KEYS = frozenset({'keymap', 'padmap', 'padmaps'})


class SplitDefaults:
    """The NSUserDefaults interface over three files, routed by key."""

    def __init__(self, folder: str):
        self.folder = folder
        self.save = UserDefaults(os.path.join(folder, 'save.json'))
        self.settings = UserDefaults(os.path.join(folder, 'settings.json'))
        self.keys = UserDefaults(os.path.join(folder, 'keys.json'))

    def store_for(self, key: str) -> 'UserDefaults':
        if key in INPUT_KEYS:
            return self.keys
        if key in SETTINGS_KEYS:
            return self.settings
        return self.save

    @property
    def stores(self) -> tuple:
        return self.save, self.settings, self.keys

    # --- the NSUserDefaults surface the game uses ------------------------------------------------
    def set_object(self, value, key: str) -> None:
        self.store_for(key).set_object(value, key)

    def set_integer(self, value, key: str) -> None:
        self.store_for(key).set_integer(value, key)

    def set_float(self, value, key: str) -> None:
        self.store_for(key).set_float(value, key)

    def set_bool(self, value, key: str) -> None:
        self.store_for(key).set_bool(value, key)

    def set_date(self, unix_time: float, key: str) -> None:
        self.store_for(key).set_date(unix_time, key)

    def remove(self, key: str) -> None:
        self.store_for(key).remove(key)

    def object(self, key: str):
        return self.store_for(key).object(key)

    def integer(self, key: str) -> int:
        return self.store_for(key).integer(key)

    def float(self, key: str) -> float:
        return self.store_for(key).float(key)

    def bool(self, key: str) -> bool:
        return self.store_for(key).bool(key)

    def date(self, key: str):
        return self.store_for(key).date(key)

    def synchronize(self) -> None:
        for store in self.stores:
            store.synchronize()


class UserDefaults:
    _standard = None

    @classmethod
    def standard(cls):
        if cls._standard is None:
            cls._standard = SplitDefaults(paths.user_dir())
        return cls._standard

    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as fh:
                    self.data = json.load(fh)
            except (OSError, ValueError):
                self.data = {}
        self._dirty = False

    # --- setters ---------------------------------------------------------------------------------
    def set_object(self, value, key: str) -> None:
        if value is None:
            self.data.pop(key, None)
        else:
            self.data[key] = value
        self._dirty = True

    def set_integer(self, value, key: str) -> None:
        self.set_object(int(value), key)

    def set_float(self, value, key: str) -> None:
        self.set_object(float(value), key)

    def set_bool(self, value, key: str) -> None:
        self.set_object(bool(value), key)

    def set_date(self, unix_time: float, key: str) -> None:
        self.set_object({'__date__': float(unix_time)}, key)

    def remove(self, key: str) -> None:
        self.set_object(None, key)

    # --- getters ---------------------------------------------------------------------------------
    def object(self, key: str):
        return self.data.get(key)

    def integer(self, key: str) -> int:
        return ns_int_value(self.data.get(key))

    def float(self, key: str) -> float:
        return ns_float_value(self.data.get(key))

    def bool(self, key: str) -> bool:
        v = self.data.get(key)
        if isinstance(v, str):
            s = v.strip().lower()
            return s[:1] in ('y', 't') or ns_int_value(s) != 0
        return bool(v) if isinstance(v, (bool, int, float)) else False

    def date(self, key: str) -> float | None:
        v = self.data.get(key)
        if isinstance(v, dict) and '__date__' in v:
            return float(v['__date__'])
        return None

    def synchronize(self) -> None:
        if not self._dirty:
            return
        folder = os.path.dirname(self.path)
        name = os.path.splitext(os.path.basename(self.path))[0]
        fd, tmp = tempfile.mkstemp(prefix=name, suffix='.tmp', dir=folder)
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(self.data, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.path)
        self._dirty = False


def ns_float_value(v) -> float:
    """-[NSString floatValue] / -[NSNumber floatValue]: leading numeric prefix, else 0."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.lstrip()
        end = 0
        seen_digit = seen_dot = seen_exp = False
        i = 0
        if i < len(s) and s[i] in '+-':
            i += 1
        while i < len(s):
            ch = s[i]
            if ch.isdigit():
                seen_digit = True
            elif ch == '.' and not seen_dot and not seen_exp:
                seen_dot = True
            elif ch in 'eE' and seen_digit and not seen_exp:
                if i + 1 < len(s) and (s[i + 1].isdigit() or (s[i + 1] in '+-' and i + 2 < len(s) and s[i + 2].isdigit())):
                    seen_exp = True
                    i += 1
                else:
                    break
            else:
                break
            i += 1
            if seen_digit:
                end = i
        try:
            return float(s[:end]) if end else 0.0
        except ValueError:
            return 0.0
    return 0.0


def ns_int_value(v) -> int:
    """-[NSString intValue]: leading integer prefix (so "15,000" -> 15); numbers truncate."""
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.lstrip()
        i = 0
        if i < len(s) and s[i] in '+-':
            i += 1
        j = i
        while j < len(s) and s[j].isdigit():
            j += 1
        return int(s[:j]) if j > i else 0
    return 0


def ns_bool_value(v) -> bool:
    """-[NSString boolValue] / -[NSNumber boolValue]."""
    if isinstance(v, str):
        s = v.lstrip()
        if s[:1] in ('+', '-'):
            s = s[1:]
        s = s.lstrip('0')
        return s[:1].lower() in ('y', 't') or (s[:1].isdigit() and s[:1] != '0')
    if isinstance(v, (bool, int, float)):
        return bool(v)
    return False


def now() -> float:
    return time.time()
