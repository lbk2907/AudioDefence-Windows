"""ADAppDelegate - launch sequence, menu music and screen navigation.

Navigation methods build the controller the original allocates and hand it to the screen host
(``-loadViewController:``: dismiss the presented controller, present the new one).  Screens that are not
ported yet are requested by their original class name; the host decides what to show for them.
"""
from __future__ import annotations

import logging

from .platform.runloop import RunLoop
from .platform.tracker import Tracker
from .s3d.engine import S3DEngine

log = logging.getLogger('app')


class App:
    _delegate: 'App | None' = None

    @classmethod
    def delegate(cls) -> 'App':                            # [[UIApplication sharedApplication] delegate]
        if cls._delegate is None:
            cls._delegate = App()
        return cls._delegate

    def __init__(self):
        self.host = None                                   # ScreenManager (window + root view controller)
        self.view_controller = None                        # the presented controller
        self.menu_music_playing = False
        self.current_menu_music = None
        self.open_sound = None
        self.fade_out_timer = None
        self.start_theme_after_fade = False
        self.status_bar = None                             # the last loaded ADStatusBarViewController
        #: PORT ADDITION: whether the player is inside Play, which is what the coins and the diamonds are
        #: shown on (StatusBar._wanted); set by `go_to_play_menu` and cleared by `go_to_main_menu`
        self.in_play = False

    # --- launch ----------------------------------------------------------------------------------
    def application_did_finish_launching(self) -> None:  # 0x10008099c
        self.init_papa_engine()
        Tracker.shared().init_game_play_tracker()
        Tracker.shared().init_armory_tracker()
        # the logo is presented over the empty root controller
        self.load_view_controller_named('ADLogoScreenViewController')
        self.run_sanity_check()

    def run_sanity_check(self) -> None:                   # 0x100081014
        from .game.brick_manager import BrickManager
        bm = BrickManager.shared()
        bm.load_brick_chance_plist('brick_chance')
        # -[ADBrickManager runSanityCheck] 0x1000c1a94 only logs broken spawn_after links: not ported

    def init_papa_engine(self) -> None:                   # 0x1000829d4
        S3DEngine.playlist_meta_path = 'meta'
        S3DEngine.product_name = 'AudioDefense'
        engine = S3DEngine.engine()
        engine.set_master_gain(1.5)
        engine.trace_level = 0
        engine.set_reverb_room_size(1.5)
        engine.set_reverb_dampening(50.0)
        engine.set_reverb_volume(1.0)
        engine.set_distance_scale(0.8)
        engine.set_max_spatial_gain(6.0)
        self.activate_buttons_playlist()

    def activate_buttons_playlist(self) -> None:          # 0x100082bf8
        pl = S3DEngine.engine().play_list_with_name('buttons')
        if pl is not None:
            pl.activate()

    # --- presentation ----------------------------------------------------------------------------
    def load_view_controller(self, controller) -> None:   # 0x1000811bc
        if self.host is not None:
            self.host.load_view_controller(controller)
        self.view_controller = controller

    def load_view_controller_named(self, class_name: str, **kwargs) -> None:
        if self.host is not None:
            controller = self.host.create_view_controller(class_name, **kwargs)
            self.load_view_controller(controller)

    def present_view_controller_named(self, from_vc, class_name: str, **kwargs) -> None:
        """[fromVC presentViewController:[[class alloc] initWithNibName:...] animated:NO completion:nil]."""
        if self.host is not None:
            self.host.present_over(from_vc, self.host.create_view_controller(class_name, presented=True, **kwargs))

    @staticmethod
    def dictionary_for_challenge_with_name(name):         # 0x1000810c8
        from .game import data
        return data.plist(name)

    def screen_reader_running(self) -> bool:              # UIAccessibilityIsVoiceOverRunning()
        return bool(self.host is not None and self.host.screen_reader_running())

    # --- navigation ------------------------------------------------------------------------------
    # DIVERGENCE: the original starts the menu theme on three screens only - the main menu, the play menu
    # and the world list - and lets it run on from there, so any menu you reach straight out of a game is
    # silent.  The port starts it on every menu (the pause screen, the revive screen and the two failure
    # screens keep their own sound).  startMenuMusic: returns at once when the theme is already playing.
    def go_to_accessible_challenge_overview_with_dictionary(self, d) -> None:   # 0x1000813b0
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('Accessible_ADChallengeOverviewViewController', dictionary=d)

    def go_to_challenge_overview_with_dictionary(self, d) -> None:   # 0x100081458
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('ADChallengeOverviewViewController', dictionary=d)

    def go_to_input_mode_select_screen(self) -> None:     # 0x100081500
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('ADInitialControlSchemeViewController')

    def go_to_opener(self) -> None:                       # 0x100081584
        from .game.gameplay import OpenerGameplayController
        self.load_view_controller(OpenerGameplayController(self.host))

    def go_to_game_over_endless(self) -> None:            # 0x100081608
        if self.screen_reader_running():
            self.load_view_controller_named('Accessible_ADGameOverEndlessViewController')
        else:
            self.load_view_controller_named('ADGameOverEndlessViewController')

    def go_to_challenge_selector(self) -> None:           # 0x1000816e0
        from .game.parameters import GameParameters
        # DIVERGENCE: the original starts the menu music for the main menu, the play menu and the world
        # list, but not for the challenge list inside a world, so coming back here from a game leaves it
        # silent.  The port starts it here too; startMenuMusic: does nothing when the theme already plays.
        self.start_menu_music('main_menu_theme')
        world = GameParameters.shared().last_challenge_world
        if self.screen_reader_running():
            self.load_view_controller_named('Accessible_ADChallengeSelectorViewController', world_name=world)
        else:
            self.load_view_controller_named('ADChallengeSelectorViewController', world_name=world)

    def go_to_challenge_completed_with_dictionary(self, d) -> None:   # 0x10008189c
        self.start_menu_music('game_over_theme')
        if self.screen_reader_running():
            self.load_view_controller_named('Accessible_ADChallengeCompletedViewController', dictionary=d)
        else:
            self.load_view_controller_named('ADChallengeCompletedViewController', dictionary=d)

    def go_to_challenge_failed_with_dictionary(self, d) -> None:   # 0x1000819b8
        self.load_view_controller_named('ADChallengeFailedViewController', dictionary=d)

    def go_to_armory(self, from_vc, loadout_enabled: bool) -> None:   # goToArmoryFromVC:EnableLoadOut: 0x100081a60
        if self.host is None:
            return
        if self.screen_reader_running():
            vc = self.host.create_view_controller('Accessible_ADArmoryViewController', presented=True,
                                                  loadout_enabled=loadout_enabled)
        else:
            vc = self.host.create_view_controller('ADArmoryViewController', presented=True,
                                                  loadout_enabled=loadout_enabled)
        self.host.present_over(from_vc, vc)                # presented modally over the calling screen

    def go_to_challenge_after(self, challenge) -> None:   # 0x100081c70
        from .game.challenge_data import ChallengeData
        from .game.parameters import GameParameters
        cd = ChallengeData.shared()
        world = GameParameters.shared().last_challenge_world
        if not cd.has_challenge_after(challenge, world):
            self.go_to_world_selector()
            return
        nxt = cd.challenge_after(challenge, world)
        if self.screen_reader_running():
            if cd.has_weapon_for_challenge_with_name(nxt):
                self.go_to_accessible_challenge_overview_with_dictionary(self.dictionary_for_challenge_with_name(nxt))
            else:
                self.go_to_challenge_selector()
            return
        d = self.dictionary_for_challenge_with_name(nxt)
        if cd.has_weapon_for_challenge_with_name(nxt):
            self.load_view_controller_named('ADChallengeOverviewViewController', dictionary=d)
        else:
            self.load_view_controller_named('ADChallengeLockedViewController', dictionary=d)

    def go_to_story(self) -> None:                        # 0x1000820dc
        self.load_view_controller_named('ADStoryViewController')

    def go_to_roulette(self) -> None:                     # 0x100082160
        self.load_view_controller_named('ADScenarioRouletteViewController')

    def go_to_gameplay(self) -> None:                     # 0x1000821e4
        from .game.gameplay import GameplayController
        self.stop_menu_music()
        self.load_view_controller(GameplayController(self.host))

    def go_to_challenge_with_dict(self, d) -> None:       # 0x100082278
        from .game.gameplay import ChallengeGameplayController
        self.stop_menu_music()
        self.load_view_controller(ChallengeGameplayController(d, self.host))

    def go_to_world_selector(self) -> None:               # 0x10008233c
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('ADWorldChallengeListViewController')

    def go_to_main_menu(self) -> None:                    # 0x1000823d8
        self.in_play = False                              # out of Play: no coins or diamonds (StatusBar)
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('ADMainMenuViewController')

    def go_to_play_menu(self) -> None:                    # 0x100082474
        # PORT ADDITION (user request): everything from here until the main menu is "inside Play", and that
        # is what the coins and the diamonds are shown on - a mode added later included (StatusBar._wanted)
        self.in_play = True
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('ADPlayMenuViewController', should_animate=False)

    def go_to_info_screen(self, page_name) -> None:       # 0x100082514
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('ADInfoViewController', page_name=page_name)

    def go_to_tarot(self) -> None:                        # 0x1000825bc
        # DIVERGENCE: the original leaves the menu music to whatever was playing when you got here, which
        # after an Endless game over is nothing at all; the port starts the theme so the card screen is
        # not silent.  startMenuMusic: crossfades if another theme is running.
        self.start_menu_music('main_menu_theme')
        self.load_view_controller_named('ADTarotViewController')

    def pop_to_root(self) -> None:                        # 0x100082640
        pass

    def go_to_tabbed_challenge_screen(self) -> None:      # 0x100082644
        self.load_view_controller_named('ADWorldChallengeListViewController')

    # --- menu music ------------------------------------------------------------------------------
    #: DIVERGENCE: game_over_theme.m4a and main_menu_theme.m4a are the same file - 2,121,278 bytes each,
    #: identical SHA-256, one 129-second piece of music shipped under two names.  The original treats them
    #: as different tracks, so leaving a finished challenge for the challenge list "changes" the music by
    #: fading it out and starting it again from the beginning - the same music, restarted, for no audible
    #: reason.  Treated as one track here, so whichever name is asked for, music already playing stays.
    SAME_MUSIC = ('main_menu_theme', 'game_over_theme')

    def start_menu_music(self, name: str, play_open_sting: bool = True) -> None:   # 0x100082ca0
        pl = S3DEngine.engine().play_list_with_name('main_menu')
        if pl is None:
            return
        equivalent = self.SAME_MUSIC if name in self.SAME_MUSIC else (name,)
        # the opening sting is the front of that same piece, so it counts as the music already running
        if self.open_sound is not None and self.open_sound.playing and name in self.SAME_MUSIC:
            return
        if self.menu_music_playing:
            # DIVERGENCE: the original returns here whenever main_menu_theme is playing (0x082db0), taking
            # it to mean "already playing, nothing to do".  While a fade is running that theme is on its way
            # out, not staying, so the request would be dropped and startThemeAfterFade never set: the fade
            # finishes, stops everything, and nothing starts it again - which left a whole round silent
            # after a quick Try again.  A dying theme no longer counts as playing.
            playing_now = [pl.sound(n) for n in equivalent]
            if (any(t is not None and t.playing for t in playing_now)
                    and not (self.fade_out_timer is not None and name in self.SAME_MUSIC)):
                return
            self.stop_menu_music()
            self.start_theme_after_fade = True
            return

        def activated(_pl, name=name):                    # startMenuMusic:_block_invoke 0x100082ee0
            self.apply_menu_music_volume()                # PORT ADDITION
            if name == 'main_menu_theme' and play_open_sting:
                self.open_sound = pl.sound('main_menu_open')
                if self.open_sound is None:
                    return
                self.open_sound.set_gain(0.4)
                self.open_sound.play()

                def monitor(sound, elapsed, duration):    # _block_invoke_block_invoke 0x100083178
                    if duration * 0.7 > elapsed:
                        return False
                    if not self.menu_music_playing:
                        self.current_menu_music = pl.sound(name)
                        if self.current_menu_music is not None:
                            self.current_menu_music.set_gain(0.4)
                            self.current_menu_music.set_stream(True)
                            self.current_menu_music.play(True)
                        self.menu_music_playing = True
                    # the original's BOOL result is whatever objc_release leaves in w0; keep monitoring
                    return False
                self.open_sound.add_3d_sound_monitor(monitor)
            else:
                self.current_menu_music = pl.sound(name)
                if self.current_menu_music is not None:
                    self.current_menu_music.set_gain(0.4)
                    self.current_menu_music.set_stream(True)
                    self.current_menu_music.play(True)
                self.menu_music_playing = True
        pl.activate(activated)

    @staticmethod
    def apply_menu_music_volume() -> None:
        """PORT ADDITION: the menu music volume (Page Up / Page Down in the menus, see
        screens.menu_music_volume_key), on every sound of the main_menu playlist - the theme, the game-over
        theme and the opening sting, which is all it holds.  Called as the music starts and whenever the
        volume changes, so a change is heard at once."""
        from .game.parameters import GameParameters
        pl = S3DEngine.engine().play_list_with_name('main_menu')
        if pl is not None:
            volume = GameParameters.shared().menu_music_gain()
            pl.each(lambda sound: sound.set_volume(volume) and False)

    def stop_menu_music(self) -> None:                    # 0x1000833dc
        if self.fade_out_timer is not None:
            return
        self.fade_out_timer = RunLoop.main().schedule_timer(0.05, self.reduce_main_menu_theme_volume, True)

    def reduce_main_menu_theme_volume(self) -> None:      # 0x100083460
        pl = S3DEngine.engine().play_list_with_name('main_menu')
        music = self.current_menu_music
        if music is not None:
            music.set_gain(music.gain + -0.01)
        if self.open_sound is not None:
            self.open_sound.set_gain(self.open_sound.gain + -0.01)
        music_gain = music.gain if music is not None else 0.0          # [nil gain] == 0
        open_gain = self.open_sound.gain if self.open_sound is not None else 0.0
        if music_gain <= 0.0 or open_gain <= 0.0:
            if music is not None:
                music.set_gain(0.0)
            if self.open_sound is not None:
                self.open_sound.set_gain(0.0)
                self.open_sound.stop()
            if music is not None:
                music.stop()
            self.menu_music_playing = False
            if self.fade_out_timer is not None:
                self.fade_out_timer.invalidate()
            self.fade_out_timer = None
            if pl is not None:
                pl.deactivate()
            if self.start_theme_after_fade:
                # DIVERGENCE (user request): the original restarts the menu music here with the full
                # startMenuMusic: path, which plays main_menu_open - a 13.2 s sting the theme only joins at
                # 70% of (the monitor at 0x100083178).  That is right when the menus are opened fresh, but
                # this call is a *return* to the menus: leaving a finished challenge for the challenge list
                # replayed the whole intro before the music came back.  The theme starts directly instead.
                # Launching the game, the main menu and every other path still play the sting.
                self.start_menu_music('main_menu_theme', play_open_sting=False)
            self.start_theme_after_fade = False

    # --- lifecycle -------------------------------------------------------------------------------
    def pause_game(self) -> None:                         # 0x100083738
        from .game.gameplay import GameplayController, OpenerGameplayController
        vc = self.view_controller
        # DIVERGENCE: the original presents the pause screen even when one (or the revive view) is
        # already up; the port skips an already paused game so focus changes cannot stack screens.
        # DIVERGENCE: ADOpenerGameplayViewController is an ADGameplayViewController, so the original's
        # isKindOfClass: test pauses the opener too.  Resigning active is rare on a phone and constant on
        # Windows - every alt-tab - so the port pauses real gameplay only, never the opener.
        if isinstance(vc, OpenerGameplayController):
            return
        if isinstance(vc, GameplayController) and not vc.paused:
            vc.pause_button_touched()

    def application_will_resign_active(self) -> None:     # 0x10008381c
        self.pause_game()
