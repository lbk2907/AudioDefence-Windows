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
    except BaseException:
        _report_failure(traceback.format_exc())
        code = 1
    sys.exit(code)
