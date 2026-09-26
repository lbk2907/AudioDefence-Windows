"""Start Audio Defence (the Windows and Mac port).

Double-click this file, or run:  py AudioDefence.py  (on the Mac:  uv run AudioDefence.py)
Options such as --endless or --challenge tutorial_1 are passed through (see the README).
"""
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


#: the packages the source version needs, by the module whose name comes back when one is missing.  A
#: player who downloads the source zip rather than a release has Python and nothing else, and the traceback
#: they get says "No module named 'pygame'", which is true and no help at all.
PACKAGES = {'pygame': 'pygame-ce', 'numpy': 'numpy', 'av': 'av', 'comtypes': 'comtypes',
            'prism': 'prismatoid'}
INSTALL = 'py -m pip install pygame-ce numpy av comtypes prismatoid'
MAC_INSTALL = 'uv run AudioDefence.py'


def _missing_package(exc) -> str | None:
    """The package to install, when what went wrong is that one is not installed."""
    if not isinstance(exc, ModuleNotFoundError):
        return None
    return PACKAGES.get((getattr(exc, 'name', '') or '').split('.')[0])


def _report_missing(package: str) -> None:
    """Say which package is missing and how to get it, rather than handing over a traceback."""
    mac = sys.platform == 'darwin'
    how = MAC_INSTALL if mac else INSTALL
    lines = ['Audio Defence could not start: the %s package is not installed.' % package, '',
             'This is the source version, which needs Python and a few packages.', '']
    lines += (['Run:  %s' % how] if mac else ['Install them with:', '', '    %s' % how])
    lines += ['', 'Or download the ready-made build from the releases page, which needs none of this.']
    text = chr(10).join(lines)
    _write_crash(text)
    if sys.stdout is not None:
        print(text)
    try:
        from audiodefence.platform.speech import Speech
        Speech.shared().speak('Audio Defence could not start. The %s package is not installed. This is the '
                              'source version: install what it needs with %s, or download the ready-made '
                              'build from the releases page.' % (package, how))
    except Exception:
        pass
    if sys.stdout is not None and sys.stdin is not None:
        try:
            input('Press Enter to close this window.')
        except (EOFError, RuntimeError):
            pass
    else:
        time.sleep(8)


def _write_crash(text: str) -> str | None:
    """A build made with --windowed has no console to print to, so the error goes to a file."""
    try:
        from audiodefence.paths import user_dir
        path = os.path.join(user_dir(), 'crash.txt')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(time.strftime('%Y-%m-%d %H:%M:%S\n\n') + text)
        return path
    except Exception:
        return None


def _report_failure(text: str) -> None:
    path = _write_crash(text)
    console = sys.stdout is not None and sys.stdin is not None
    if sys.stdout is not None:
        print(text)
    try:
        from audiodefence.platform import host
        from audiodefence.platform.speech import Speech
        Speech.shared().speak('Audio Defence could not start. The error is %s.'
                              % ('shown in the console window' if console else
                                 'in crash.txt, ' + host.user_dir_hint() if path else
                                 'not written down'))
    except Exception:
        pass
    if console:
        try:
            input('Press Enter to close this window.')
        except (EOFError, RuntimeError):
            pass
    else:
        time.sleep(6)               # no console to wait in, so wait for the speech itself


if __name__ == '__main__':
    try:
        from audiodefence.__main__ import main
        code = main()
    except SystemExit as exc:
        code = exc.code
    except BaseException as exc:
        package = _missing_package(exc)
        if package:
            _report_missing(package)
        else:
            _report_failure(traceback.format_exc())
        code = 1
    sys.exit(code)
