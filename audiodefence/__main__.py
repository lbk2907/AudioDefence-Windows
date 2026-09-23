"""Audio Defence for Windows and the Mac.

The game is started by ``py AudioDefence.py [options]``, which calls
``main()`` here; ``python -m audiodefence`` runs the same thing.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time


def _setup_logging(level: str) -> None:
    from .paths import user_dir
    handlers = [logging.FileHandler(os.path.join(user_dir(), 'audiodefence.log'), 'w', encoding='utf-8')]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format='%(asctime)s %(name)s %(levelname)s %(message)s', handlers=handlers)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='audiodefence')
    parser.add_argument('--log-level', default='info')
    parser.add_argument('--game', help="the original app bundle (or the folder holding it), when it is not "
                                       "in the project's game folder")
    parser.add_argument('--endless', action='store_true',
                        help='start an endless game, unlocked or not (skips the menu and the tarot cards)')
    parser.add_argument('--challenge', metavar='NAME',
                        help='start a challenge by its plist name, e.g. tutorial_1, unlocked or not')
    parser.add_argument('--mute', action='store_true', help='testing: silence the listener')
    parser.add_argument('--no-speech', action='store_true', help='testing: do not speak')
    parser.add_argument('--exit-after', type=float, metavar='SECONDS',
                        help='testing: quit after this many seconds')
    args = parser.parse_args(argv)
    if args.game:
        # set before anything imports audiodefence.paths: that module resolves the bundle on import
        os.environ['AUDIODEFENCE_GAME'] = args.game
    _setup_logging(args.log_level)
    log = logging.getLogger('main')
    from . import paths
    log.info('game data: %s (from %s)', paths.BUNDLE, paths.BUNDLE_SOURCE)
    if not os.path.isdir(paths.BUNDLE):
        log.error("the game's data is not where the port looks for it: put the original audiodefence.app "
                  "in the project's game folder, or pass --game PATH (see the README)")
    if not paths.FROZEN:
        from .platform import version
        version.current()                               # a checkout with no VERSION file gets one now

    import pygame
    from .app import App
    from .game.parameters import GameParameters
    from .platform.runloop import RunLoop
    from .platform.speech import Speech
    from .s3d.engine import S3DEngine
    from .ui.host import ScreenManager

    if args.no_speech:
        Speech.shared().speak = lambda *a, **k: None
        Speech.shared().speak_automatic = lambda *a, **k: None
    GameParameters.screen_reader_running = Speech.shared().screen_reader_running()
    Speech.shared().choice = GameParameters.shared().speech_output()   # Settings -> Miscellaneous
    Speech.shared().configure_sapi(**GameParameters.shared().sapi_config())

    from .platform.pad import Pads, set_hints
    set_hints()                                         # before SDL's joystick layer starts, in pygame.init()
    pygame.init()
    pygame.display.set_caption('Audio Defence')
    pygame.display.set_mode((640, 480))
    Pads.shared().start()                               # PORT ADDITION: game controllers
    Pads.shared().speak = lambda text: Speech.shared().speak(text, False)

    host = ScreenManager()
    Pads.shared().changed = host.pads_changed           # Settings -> Joystick follows a controller in and out
    running = [True]
    host.request_quit = lambda: running.__setitem__(0, False)
    app = App.delegate()
    app.host = host
    if args.endless or args.challenge:
        app.init_papa_engine()
        app.run_sanity_check()
        if args.endless:
            app.go_to_gameplay()
        else:
            app.go_to_challenge_with_dict(App.dictionary_for_challenge_with_name(args.challenge))
    else:
        app.application_did_finish_launching()          # logo, then the opener or the control scheme choice
    if args.mute:
        from .s3d import openal as oal
        S3DEngine.engine().al.alListenerf(oal.AL_GAIN, 0.0)

    loop = RunLoop.main()
    engine = S3DEngine.engine()
    started = time.perf_counter()
    try:
        while running[0]:
            if args.exit_after is not None and time.perf_counter() - started > args.exit_after:
                break
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running[0] = False
                elif event.type == pygame.WINDOWFOCUSLOST:
                    app.application_will_resign_active()
                else:
                    host.handle_event(event)
            loop.run_once()
            engine.pump()
            host.frame()
            wait = min(loop.next_deadline() - loop.now(), 0.005)
            if wait > 0:
                time.sleep(wait)
    except KeyboardInterrupt:
        pass
    finally:
        log.info('shutting down')
        try:
            try:
                Pads.shared().stop()                    # a DualSense keeps a trigger feel until told not to
            except Exception:
                log.exception('could not reset the controllers')
            try:
                Speech.shared().shutdown()              # and speech lets its own card go before the engine's
            except Exception:
                log.exception('could not stop the speech')
            engine.shutdown()
        finally:
            pygame.quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
