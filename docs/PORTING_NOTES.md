# Windows port — status, controls and divergences

The port is written method by method against the disassembly (`py tools/query.py digest|fn …`);
each ported method carries its original address in a comment. This file records what is ported, the
input mapping that replaces touch and motion, and every place the port knowingly differs.

## Running

```
py AudioDefence.py                  # the game: logo, opener (or first control scheme choice), main menu
py AudioDefence.py --endless
py AudioDefence.py --challenge tutorial_1
```

Testing flags: `--mute`, `--no-speech`, `--exit-after SECONDS`, `--log-level debug`.
The log is written to `%APPDATA%\AudioDefence\audiodefence.log`; saves live in the same folder.

## Ported so far

| area | modules |
|---|---|
| audio engine (S3D on OpenAL Soft, HRTF from the embedded IRCAM set, original Freeverb reverb) | `s3d/` |
| run loop, NSTimer, notifications, NSUserDefaults, C rand | `platform/` |
| speech (NVDA controller client, other screen readers through Prism, SAPI fallback) | `platform/speech.py` |
| parameters, modifiers, inventory, persistent + in-game stats | `game/parameters.py`, `modifiers.py`, `inventory.py`, `persistent_stats.py`, `ingame_stats.py` |
| enemies, passers-by (cows, cars, jukebox, machine), diamonds, power-up containers | `game/enemy.py`, `passerby.py`, `passerby_manager.py` |
| bricks, brick manager, scripted sounds | `game/brick.py`, `brick_manager.py`, `adsound.py` |
| weapons, melee, projectiles, weapon manager | `game/weapon.py`, `projectile.py`, `weapon_manager.py` |
| power-ups (minigun, fireworks, tornado, tesla) and cooldown manager | `game/powerups.py` |
| ambience, player (tinnitus, heartbeat), missions, challenge data | `game/ambient.py`, `player.py`, `missions.py`, `challenge_data.py` |
| gameplay controllers (endless, challenge, opener), revive, pause | `game/gameplay.py` |
| app delegate (launch, menu music, navigation) | `app.py` |
| VoiceOver stand-in, ADNoBarViewController / ADViewController, status bar | `ui/accessibility.py`, `ui/viewcontroller.py` |
| logo, first control scheme choice, main menu, play menu, info pages | `ui/menus.py` |
| tarot (Endless start) | `ui/tarot.py` |
| Endless game over for screen reader users | `ui/gameover.py` |
| world list, challenge selector, challenge overview, challenge completed / failed | `ui/challenges.py` |
| armory: tabs, weapon shop, loadout, power-ups, currency, weapon and power-up detail views | `ui/armory.py` |
| settings, pause, control scheme table | `ui/settings.py` |
| stats portal: Zombiepedia, Statistics, Credits | `ui/statsportal.py`, `ui/credits_text.py` |

Every screen a player can reach with a screen reader is ported, so the port test menu is gone.

Not ported, and unreachable in the original: `ADScenarioRouletteViewController` and `ADStoryViewController`
(`goToRoulette` / `goToStory` have no callers, no nib action and no selector string reaches them),
`ADCheatViewController` (the main menu's cheat button is hidden), `ADEnemyUnlockPopupViewController` and
`ADScoreFeedbackViewController` (never allocated).  The non-accessible (sighted) variants of the ported
screens are not ported either: the port always runs with a screen reader.  A screen that is not ported shows
a placeholder with "Main menu", or "Close" when it was presented.

## Menu controls (VoiceOver stand-in)

Menu screens are built from the iPhone nibs (the 568x320 tag-2781 layout) and read like VoiceOver reads
them: elements top to bottom, then left to right, with their accessibility labels, "button", "dimmed" and
hints.

PORT INPUT: `UIAccessibilityIsVoiceOverRunning()` is always true here (`Speech.screen_reader_running`).
The original's other branch is its sighted game - `ADChallengeSelectorViewController`,
`ADArmoryViewController`, `ADGameOverEndlessViewController` and the rest, none of them ported, since the
port has nothing to look at - and every screen is spoken, by NVDA when it is running, by another screen
reader through Prism when one of those is, and by SAPI 5 when none is.  Asking whether NVDA was running sent a player on SAPI 5 down the sighted path: "... is not ported
yet" on opening a world's challenges and no spoken game view (`AccessibleGameView`).  It also chose the
button mode, which a new profile now picks for itself (see Divergences).

| key | VoiceOver gesture |
|---|---|
| Right / Tab | flick right: next element |
| Left / Shift+Tab | flick left: previous element |
| Ctrl+Right / Ctrl+Left, End / Home | first / last element |
| Enter | double tap: activate (Space did too, until it was taken off) |
| Shift+Enter | a row's second action, where it has one (Settings: the previous value on a row that steps through several - turn sensitivity, tutorial text, vibration, trigger feel) |
| Escape / Backspace | two-finger scrub: `accessibilityPerformEscape` (the Back button on screens with a status bar) |
| Ctrl+Tab / Ctrl+Shift+Tab | last / first element, as End / Home do |
| Down / Up (the unused pair) | next / previous tab or category, where the screen has them |
| Ctrl+Down / Ctrl+Up (the unused pair) | last / first tab or category |
| Page Up / Page Down | no gesture: the menu music volume, up / down (a port addition, see Divergences) |

PORT ADDITION: which pair of arrows moves the cursor is a setting - Left and Right by default, Up and Down
instead if Settings -> Miscellaneous -> Menu layout is switched (`GameParameters.menu_axis`, defaults key
`menuAxis`).  The unused pair does nothing in a menu; Tab, Shift+Tab, Home and End are not affected.  A
swipe has no direction to choose, so none of this comes from the original.

PORT ADDITION: holding a key that steps one element repeats it (`ScreenManager._hold_navigation_key`,
0.4 s then every 0.09 s).  Only 'next' and 'previous' repeat, and only while a menu screen is on top, so
the ends, Enter and every gameplay key are left alone.  VoiceOver's own repeat comes from the swipe being
repeated, so there is nothing in the original to copy here.

PORT UI: Settings holds seven categories - the original's Aiming, Controls and Sound, then Speech, Keyboard,
Joystick and Miscellaneous.  Speech carries who speaks the game and SAPI 5's own voice; Keyboard the key
bindings and Joystick a controller's buttons, each on its own so neither moves the other; Miscellaneous the
rest, from how the cursor moves through a screen to how a controller vibrates.  Keyboard and Joystick
restore their own defaults, and Miscellaneous holds the one button that resets every setting.

PORT ADDITION: the pair that does not move the cursor changes tab (`cross_axis_key`), so the two are always
different keys.  The armory steps through its four tab buttons (`ArmoryScreen.step_tab`, skipping Loadout
when it is not enabled, since its button only raises the EQUIP alert) and the settings panel steps through
its categories (`ControlSchemePanel.step_category`), which is the only way to reach one: the settings
screen opens inside Aiming with that category's heading as its first row, so there is no list of categories
and Escape always leaves the screen.  Both name what they opened before reading the element they land on
(`post_screen_changed(element, prefix)`), and both hold at the ends.  The original has neither:
its tab bar is tapped directly, and its nib label says so - "Change tabs at the bottom of the screen to
navigate the armory", which the port replaces with the keys that do it here.

## Gameplay controls (port input mapping)

The original is played by touch plus device motion; with VoiceOver running it replaces the touch views with
`ADAccessibleGameView`. The port does the same when NVDA runs, sending keys as touches in the matching
screen quadrant of the button-mode layout.

These are the defaults; every gameplay key can be rebound in Settings -> Keyboard, and "Restore default
keys" puts them back.

Next weapon and Reload are bound per control scheme (`KeyMap.BY_MODE`, stored as
`{"button": [...], "gesture": [...]}` under the `keymap` default).  Under Gesture the key stands for a
swipe, so the arrows keep the swipe's direction; under Button it stands for a corner button, where nothing
is directional, so the defaults are W and R.  Rebinding one scheme leaves the other alone, and a key bound
in one scheme does nothing in the other.  Every other action is a single binding shared by both.

| key | gesture mode | button mode |
|---|---|---|
| Space tap / hold | tap = single shot, hold over 0.2 s = continuous fire | top-right corner: tap = fire, hold = continuous |
| Left / Right Ctrl | triple tap: melee | top-left corner: melee |
| Up arrow / **W** | swipe up: next weapon | bottom-left corner: next weapon |
| Down arrow / **R** | swipe down: reload | bottom-right corner: reload |
| Left / Right | turn (see control schemes) | same |
| Escape | Pause button | same |
| Enter | Skip button (challenge narration; opener) | same |
| T | read the challenge timer label | same |

The revive screen after a death is read like the menus (VoiceOver starts on the tip, then Revive and Game
over).

PORT ADDITION: a game controller (`platform/pad.py`, through SDL's game controller layer, so the buttons are
laid out alike on every pad and only their spoken names change).  In play its buttons press the same
actions as the keys (`PadMap`, stored under `padmap` in keys.json beside `keymap`); in the menus
`ScreenManager._pad_menu_key` turns them into the keys the menus already take.

| controller | gesture mode | button mode |
|---|---|---|
| R2 (a trigger counts as pressed past half way) | as Space | as Space |
| R1 | as Ctrl: melee | as Ctrl: melee |
| a stick flicked up / L1 | stick: swipe up, next weapon | L1: next weapon |
| a stick flicked down / L2 | stick: swipe down, reload | L2: reload |
| either stick, sideways | turn at the speed it is pushed | same |
| Options | Pause button (and on the pause screen, Resume) | same |
| Cross | Skip button | same |
| Square | read the challenge timer label | same |

A stick counts as flicked past 60% and let go below 30%, in the direction of its larger axis, so a turn does
not switch weapons.  Turning ignores the first 18% of a stick's travel and grows in proportion past it, up
to the arrow keys' full speed; the three schemes above take that fraction as it is (the yaw rate, the drag
speed or the tilt angle), and a held turn key overrides the stick.

Control schemes (the original's `controlScheme`):

* 1 gyro: holding an arrow rotates the virtual device yaw at 2 rad/s (port choice, `KeyboardMotion.yaw_rate`).
* 2 swipe: holding an arrow drags at 600 points/s (port choice, `SWIPE_POINTS_PER_SECOND`).
* 3 tilt: holding an arrow tilts the virtual device by 0.5 rad (port choice, `KeyboardMotion.tilt`).

The heading itself goes through the original scroll-view model: a 430-point `line.png` strip
(`line@2x.png`, iPhone nib), `(int)offset % (int)width`, and the 5.68889 points-per-degree swipe scale.

## Divergences

* `-[ADWeapon playSingleShootSound]` spins on the main thread until it picks a `_fire_` sound that is not
  playing; with no such sound it would hang forever (the port returns instead).  The weapons' fire sounds last
  1 to 1.7 s while the Tactical Rifle fires every 0.25 s and the Micro SMG every 0.2 s, so after a few quick
  shots every fire sound is still playing and the original waits - the whole game froze for up to a second,
  after the hit sounds had already started.  When every fire sound is still playing the port gives the shot a
  source of its own (`S3DEngine.play_copy_of`) so the shots overlap: an S3DSound owns one OpenAL source, and
  playing it again restarts it, which is heard as the last shot being cut off.  Measured over 20 shots: the
  Tactical Rifle cut 17 of them before this, none after; the Hunting Rifle (0.6 s) never needed it.
* Every enemy plays its own copy of its sounds (`ADEnemy.voice_of`, `S3DSound.copy`).  In the original the
  enemies of one type share a playlist (`playListWithName:atBundlePath:` 0x1000fc050 caches it by name) and
  the playlist holds one sound per file (`-[S3DPlayList each:]` 0x1000ffeb8 caches the agent by key), so
  two zombies of a type share a sound whenever they pick the same file.  Playing a sound that is already
  playing restarts it once, without its loop (`play:fadein:` 0x100105eb8 sets `restart`; the cleanup block
  sends `play`, which is `play:0`); a sound keeps only the last end callback it was given
  (`add3DSoundMonitor:forSound:` 0x100109c7c empties the set first); and the first zombie to be hit or change
  step stops the sound under the other, which then walks on in silence.  Two Shield zombies walking side by
  side for 40 s: one was silent for 13.8 s of it before this, neither for any of it after.  The same sharing
  silenced a second death: the waves of a run all stay in `bricks` (nothing removes one), so the zombie that
  killed you before a revive still holds its attack sound, and when the next zombie of its type kills you,
  `stopAllEnemiesAfterPlayerDeathByEnemyWithName:` 0x1000c71b4 sends the old one
  `stopAfterPlayerWasKilled` 0x100060a58 - it is no longer attacking, so it stops that sound at once.  The
  Shield zombie has one attack sound, so its second kill in a run was always silent.  The file is still
  chosen by the playlist with the same random draws; a copy has its own source, position and end callback
  on the same buffer, and the playlist stops and unloads the copies with its own sounds.
* A critical kill of an enemy with no critical death sound falls back on its ordinary death.
  `playDeathSound` 0x100063688 looks for `death_crit`, then `_diecrit_` on a critical kill and for nothing
  else, having first stopped the enemy's hit sound (0x1000637a4); Shield, WeakZombieD, ZombieC and the
  passers-by and pickups have no critical death, so a critical kill cut their hit sound off and played
  nothing.  Melee weapons are critical 5 to 25% of the time, so meleeing a Shield did it often.
* A playlist whose enemy is still being heard is not unloaded yet.  When a dying enemy's last sound ends,
  -[ADEnemy update:] 0x10005eb94 sends `checkPlaylistDeactivation` 0x1000c2da8, which unloads `anyObject`
  of the playlists the waves since stopped using, and its deactivate: completion (0x1000c2f24) sends it
  again until the list is empty.  A wave is cleared the moment its last enemy starts to die, so when two
  died close together the first to fall silent unloaded the other's playlist and stopped its death sound
  half way.  Such a playlist now waits for a later call, which the enemy's own end makes.  (The port had
  dropped the completion's chain and unloaded one playlist per death; it is back.)
* Sound files are decoded ahead of time on a background thread when their playlist is activated, and streamed
  sounds (music, ambience) load in the background like the original's engine-queue loading, so first plays do
  not stall the game (the port used to decode on the main thread: 3-70 ms per new sound, 0.3-0.5 s for an
  ambience at the start of a game).
* `-[ADAppDelegate pauseGame]` presents the pause screen even over an already paused game (or the revive
  view). The port ignores focus loss while paused so screens cannot stack.
* The stats screen's "Money earned" and "Diamonds collected" rows are dead in the original: nothing writes
  those keys (`saveCoinsData:` 0x1000869f4 and `saveDiamondsData:` 0x100086c2c only ever add to
  "Total Money Spent" and "Total Diamonds Spent", which no screen shows), so both read 0 for ever.  The
  port credits them as a run's rewards are paid out (`save_coins_earned`, `save_diamonds_earned`) and adds
  a "Money spent" and a "Diamonds spent" row beside them, reading the totals the original already keeps.
  The crediting is done by `-[ADInventory setCoins:]` 0x10000dfd8 and `setDiamonds:` 0x10000e0d4, which
  already record the other direction when the balance falls: a rise records what was earned, unless the
  save is being restored, since putting a balance back is not earning it.  (Until 2026-09-21 the two
  functions existed and nothing called them, so the rows still read 0 - the fault this note described in
  the original, reproduced by accident.)
* `-[ADAppDelegate pauseGame]` tests `isKindOfClass:[ADGameplayViewController class]`, and
  `ADOpenerGameplayViewController` is one, so the original pauses the opener as well when the app resigns
  active.  On a phone that is a phone call or the home button; on Windows it is every alt-tab, so the port
  pauses real gameplay only (`App.pause_game`).  The logo and the menus never paused in either.
* The settings rows play `click_button` when pressed.  The original's accessible table is silent, but its
  sighted twin's rows are `ADButtonWithFont`s, which click (`-[ADButtonWithFont playSound]` 0x100073578) -
  and the port's categories are pressed like buttons, so they click like them.
* `-[ADAppDelegate startMenuMusic:]`'s sound monitor returns an undefined BOOL (a tail call into
  `objc_release`); the port keeps monitoring.
* ARC deallocation side effects (`-[ADWeapon dealloc]` deactivating the weapon playlist, `-[ADPlayer dealloc]`)
  run where the owning reference is dropped.
* Analytics (`ADTracker`, Google Analytics) only log locally.
* `-[ADBrickManager runSanityCheck]` (log-only) is not ported; its `loadBrickChancePlist:` side effects are.
* `-[ADTarotCardViewController flipCard:]` 0x1000a5e50 returns at once while VoiceOver runs, and the flip
  sound is played at the end of the animation it skips, so a VoiceOver player hears nothing at all while the
  two cards are dealt.  The port keeps the animation skipped and plays the sound, one card at a time (about
  1 s and 2 s in), so the deal is audible.
* `-[ADStatusBarViewController deactivateButtons]` 0x10001cee4 fades the Back and Armory buttons to alpha 0
  while a screen animates in - on the tarot screen, the 2.3 s of the deal - which takes them out of the
  reading order for those seconds: long enough to arrow past where the Armory button is about to appear and
  think it is missing.  The port keeps the lock-out but dims them instead of hiding them, so the screen has
  the same shape throughout and the buttons say why they cannot be pressed yet.
* `-[ADTarotViewController viewDidLoad]` 0x10003461c makes Play visible and usable at once while VoiceOver
  runs - the sighted path leaves it off until the deal's block (`viewDidLoad_block_invoke` 0x100034e84,
  2.3 s later) - while `deactivateButtons` locks Back and Armory for those seconds, so Play was the one
  button on the screen that worked during the deal.  The port dims Play with them, and the block brings it
  back when the cards are dealt, as it does for a sighted player.
* The armory's nib label (#2) is an element VoiceOver reads; the port says its line when the armory opens -
  after the tab it opens on, "Weapons. Up and Down change tab..." - and leaves it out of the reading order.
  The four tab buttons (#38, #6, #76, #10) are left out too: the arrows change tab and name what they land
  on, so the buttons are only the controllers' own state now.  Their "This tab is currently selected" hint
  goes with them; the opening line says which tab you are in instead.
* Four of the game's strings are written in capitals for the screen - TAROT_NO_RELOAD, CHALLENGE_INFO_TITLE,
  FACEBOOK_LIKE, TWITTER_FOLLOW.  What is spoken is sentence case, with the label's line breaks collapsed
  (`data.spoken_text`); the text on screen is unchanged.
* `Accessible_ADGameOverEndlessViewController viewDidLoad` 0x100099f50 does not call `[super viewDidLoad]`,
  which is where `startMenuMusic:@"game_over_theme"` lives (0x1000d37cc), so the Endless game over screen is
  silent - kept, because that screen is the run you just lost rather than a menu.  What the port adds is the
  theme on the card screen it leads to, which the original leaves silent as well.
* `-[ADAmbientManager checkAmbiant]` 0x100099444 refuses to start an ambience only when the player is
  dead.  Ending a game from the pause screen is not a death, and `killGameplay`'s clean-up 0.1 s later
  reports every enemy as gone, which calls `checkAmbiant` again - with a Chainsaw still in the brick that
  starts `Chainsaw_ambiant` over, after the game has finished, with nothing left to stop it: it plays on
  over the menus until the next game.  The port also refuses once `killGameplay` has cleared the gameplay
  controller, which is what "there is no game any more" looks like.
* `-[S3DSound resume]` 0x100105694 is one line, `[self setPlayRate:1]`, because the original's engine
  pauses by play rate; the port pauses the OpenAL source instead, and a stopped source still carried its
  paused flag - so a later resume (the next pause, or any `AmbientManager.resume`) called alSourcePlay on
  it and started it again from the beginning.  An enemy's ambience - the Chainsaw's is the audible one -
  could come back over the menus after the game had ended.  Stopping a sound now clears the flag, and
  resume only resumes a source that OpenAL still reports as paused.
* `-[ADInfiniteScrollView awakeFromNib]` 0x10009c4b0 sets the starting content offset (half the content
  width) *before* it sets itself as the delegate, so `scrollViewDidScroll:` never runs for it and the
  engine's head orientation stays 0 while the heading is really pi.  On a phone the gyro pushes the real
  heading within milliseconds; with keys nothing moves until a turn key is pressed, so the first enemies
  are heard half a turn from where they are - behind sounds in front, right sounds left.  The port sends
  the starting heading once, at the end of the same setup.
* The original starts the menu theme on three screens - the main menu, the play menu and the world list -
  and lets it run on from there (`goToChallengeSelector` 0x1000816e0, `goToTarot`, the challenge overview
  and the info pages start nothing), so any menu reached straight out of a game is silent.  The port starts
  it on every menu.  The screens that have a sound of their own keep it: the pause screen, the revive
  screen, the challenge failed screen (its `gameover_N` jingle) and the two game over screens
  ("game_over_theme").
* `-[ADArmoryViewController backButtonPressed]` 0x100076080 dismisses the armory even when a detail view
  has taken the back button, so Escape inside a weapon or a power-up left the armory altogether.  In the
  port Escape closes the detail first, exactly as the detail's own Back button does, and closing a detail
  returns the cursor to the row it was opened from instead of the top of the screen.
* `-[ADAccessibleGameView solveButtonPress]` 0x10008a914 starts continuous fire when the fire quadrant is
  tapped in Button mode, however short the press was.  Continuous fire is a looping "_conti" sound, so the
  release stops it milliseconds later: tapping fire spends bullets almost silently, and because the empty
  click and the reload call-out are only reached from the continuous update, an empty clip is silent too
  unless the key is held.  The button that quadrant stands for does the opposite - `ADButtonWithSwipe`
  fires a single shot when the press is under 0.28 s - and so does Gesture mode, so the port fires a single
  shot for a tap here as well.  Holding still starts continuous fire, from `update()`, untouched.
* The power-up upgrader's button is titled "Upgrade for %i" and the currency is a coin image drawn beside
  it (`setCoins:` then `centerButtonTextWithCoinsImage`, 0x10004da74), which VoiceOver cannot read.  The port
  keeps the title and speaks "Upgrade for N coins".
* The Zombiepedia's sound button (nib #170) is an image view with a tap recogniser and no accessibility
  label - the nib names the two arrows, `applyAccessibility` names the text labels, nothing names this one,
  so VoiceOver reads its image file as "button audio large".  The port calls it "Preview sound", since it is
  the only way to hear the zombie at all.  The two arrows are labelled "Previous button" and "Next button" in
  the nib, which reads as "Next button, button" once the trait is added, so the port calls them "Previous"
  and "Next" and shortens their hints ("Click to view the next enemy's description. This button will be
  unavailable if you are at the end of the list" becomes "Click to view the next enemy").
* The revive screen waits for the killing enemy's `_attack` sound to finish: `-[ADEnemy attack]` 0x100060304
  registers `add3DSoundEndCallback` -> `afterAttackSound` -> `showReviveView`.  Those sounds run from about a
  second to 8.7 s (WeakZombieC, WeakZombieD; Chainsaw 8.2 s) and `Jim_attack.m4a` is 71 s, long enough to
  look like a hang.  The port waits for the sound as the original does but no more than `ADEnemy.REVIVE_AFTER`
  (5 s); the sound is left to finish underneath.
* `ADChallengeFailedViewController`'s two buttons (nib #103 and #84) hold an image and nothing else - no
  title, no accessibility label in the nib or in `viewDidLoad`, and the screen has no `Accessible_` nib - so
  VoiceOver reads them by their image file name ("menu try again single").  The port labels them "Try again"
  and "Challenge selection", after the actions they are wired to.
* Spoken texts that name a touch gesture name the port's key instead: the opener's "Triple tap to skip intro"
  says "Press Enter to skip intro", a tarot card's "(double tap to change for N diamonds)" says "(press Enter
  to change for N diamonds)", and the same for the challenge selector's two hints, the armory's tab hints and
  power-up rows, and the control scheme's "double tap to select" / "Double tap to toggle in-game
  announcements" / "Double tap to test your headphones".  The Aiming rows also replace the original's device
  descriptions ("Holding the device in front of you, turn to face the zombie") with one short line each about
  the turn keys, and the Controls rows say what Button and Gesture change for a keyboard player instead of
  where to tap and swipe.
* A button that only carries an image is read by its image file name ("menu try again single"), which is what
  VoiceOver does with an unlabelled image button; a selected table row is read as "Selected, <row>".
* Most float ivars are Python doubles. Float32 rounding is reproduced only in the touch hold timers
  (0.2 s / 0.28 s thresholds, where it moves continuous fire by one 50 ms tick) and in the heading model;
  other accumulated timers may cross their thresholds one tick differently.
* With nothing stored, `-[ADGameParameters lastControlScheme]` answers -1 and the first launch goes to the
  first control scheme screen - whose Gyro button is hidden while a screen reader runs, so Gyro could never
  be chosen there.  The port starts on **Gyro (scheme 1)** instead, so that screen is skipped; Settings ->
  Aiming still offers Gyro, Swipe and Tilt.
* `-[ADGameParameters isHeadsetPluggedIn]` always answers YES (Windows cannot reliably tell headphones from
  speakers), so the main menu's "Wear headphones" alert is not shown.
* Game Center is removed entirely (user request): the main menu has no Game Center button, and neither the
  main menu's player authentication nor the game over score report exists.
* The stats portal's "More games" button (ADMoreGamesViewController) is left out (user request);
  Zombiepedia, Stats and Credits are there.
* The armory's currency tab is an empty table: its row count comes from a `products` array that nothing in
  the binary ever sets, so the four "free coins" actions it can build (Facebook, Twitter, more games, App
  Store - all of them open web pages) are unreachable in the shipped game and none of them is ported.
* The armory's 1 ms browsing timer only feeds the analytics tracker, so the port does not run it.
* The Zombiepedia's detail pages live side by side in a scroll view; the port only lets the screen reader
  into the page being shown (iOS clips the others).
* A modal view (`accessibilityViewIsModal`) hides its siblings from the screen reader, as UIKit documents:
  the armory's weapon description leaves the tab buttons and the status bar reachable, while the power-up
  upgrader - a child of the armory's own view - hides them (it has its own Back button).
* The game over screen's "Share on twitter" button is removed (user request).
* The three results screens read one row per result, exactly as Copy results pastes it, and Copy results
  comes straight after them, before the screen's own buttons (user request).  The Endless game over
  table has two sections under the headers "Rewards" and "Statistics" (numberOfSectionsInTableView:
  0x10009a89c, tableView:viewForHeaderInSection: 0x10009a690) and reads its rewards as sentences - "Coins,
  You earned 87 coins for killing zombies" (cellForRewardsAtIndex: 0x10009aa80); the challenge completed
  table adds a "Stars" section (0x1000672f8) and inherits the sentences.  Here there are no header rows and
  each value is one line ("Coins Earned: 87", "Score: 1200", the statistics as cellForStatsAtIndex:
  0x10009b7cc and 0x100067c0c word them).  The Endless screen's first row is the run's tarot cards -
  "Tarot cards: More Power Ups! and Glue Barrels" - which the original never shows; a challenge screen
  starts with the challenge's name and "Result: Completed" or "Result: Failed".  The failed screen, which
  shows no figures in the original, reads its rows first and its tip after them.  Copy results reads the
  same rows, adding only its heading.
* The challenge completed screen reads Retry first, then Challenge selection and Next challenge (user
  request).  The nib lays them across one row - Challenge selection at x 5, Next challenge at 189,
  Retry at 364 (#70, #32, #3) - and the reading order follows the frames, so the three were read in
  that order; the port puts Retry's frame first in the row instead, as Try again already comes before
  Challenge selection on the failed screen.  Nothing here is looked at, so the row is only an order.
* What the original typed wrong is put right as its text is read in (user request, `data.TYPOS`, applied in
  `data._load` and `data.localized`, so every screen that shows a piece of the game's writing gets it
  right).  Six misspelled words: the Farty's page says its zombies are "inflated like ballons" and that
  there is no way to "keep al the gas inside"; a training-grounds tip has zombies "more aggresive"; a tarot
  card has "anticlimatic" music; the storm challenge has a "thunderstom"; The Mixed Bag says "remeber".  A
  word typed twice: "In the the Mayan Ruin Arena".  And five capitals in the wrong place: a loading tip
  opening "if you think a Zombie", the Machine Gun's "but careful, It takes ages", the Fireworks' "Each
  Upgrade" where the other four power-ups say "Each upgrade", "Unlocked After beating" on Endless, and
  "Defeat All level 1 Bricks".  A word missing: the Generator Malfunction tarot card says "Shoot it stop it
  for a while".  And a word too many: Meet The Farty's tip warns of being deafened "for a few seconds you
  if they blow up", where tutorial_8's tip already says the same thing correctly.  The game's own files are
  left as they are, so a copy of the app given with --game is corrected too.  How the original writes is
  otherwise its own: its British and American spellings side by side, Dr Bastard with and without his dot,
  the nouns it capitalises on purpose (Zombie, Melee, the Loadout Tab) and its title-case titles are left
  alone.
* The Endless game over screen's PLAY AGAIN button (nib #47) is called Close (user request).  It still does
  what playAgainButtonPressed: 0x10009bf54 does - leave for the Endless card screen - and its hint says so.
* PORT UI: Settings (and the settings part of the pause screen) opens its options as categories - Aiming,
  Controls, Sound, Keyboard - instead of the accessible table's one list under headings; Enter opens a
  category, Escape leaves it.  The original's sighted control scheme screen has the same three as tabs.
  Every change is spoken ("Tilt selected", "Announcer ON", "Turn sensitivity 2").
* PORT ADDITION: the Aiming category can set the turn sensitivity (0.5 to 3, default 1.5, Enter for the next
  value and Shift+Enter for the previous, wrapping round) and restore the aiming defaults.  The original only has that slider on its sighted screen, and stores the value with
  `setInteger:` so 1.5 comes back as 1; the port stores a float.  Sensitivity scales the port's gyro and
  swipe turn rates the way it scales the original's tilt formula.
* PORT ADDITION: `platform/keymap.py` holds the key bindings (the original is touch driven, so it has none).
  Settings -> Keyboard rebinds any gameplay action - press Enter on a row, then the new key, or Escape to
  keep the old one - and "Restore default keys" resets them.  Melee defaults to Left or Right Ctrl.
* PORT ADDITION: the main menu has a Quit button, read last, which shuts the engine down and ends the run
  loop; iOS apps have no Quit.
* View controller presentations and UIView animations are not animated: a screen appears at once, and
  animation completions run after the animation's duration.
* VoiceOver's reading order is approximated from the nib frames (see `ui/accessibility.py`), and no
  screen wraps: moving past the last element (or before the first) stays there, alerts included.
* The original reverb (csl::Stereoverb: two Freeverbs, 6 combs and 3 allpasses each) runs in the port
  itself (`s3d/reverb.py`, checked against the per-sample model in `tools/reverb_calibrate.py`).  Sounds that
  send to it play on a second OpenAL Soft device (loopback, same HRTF) whose render is mixed with the reverb
  into the output through a callback source: about 0.5 ms later than sounds on the output device.  Only
  dryGain = wetGain = 1 is supported, the only values the game uses.
* The per-sound hard clip of the binaural panner (`vDSP_vclip ±1`) is not reproduced.
* Dying in a challenge starts no music.  `-[ADChallengeGameplayViewController showDeathOverlay]` 0x1000db788
  calls `startMenuMusic:@"game_over_theme"` at 0x0db7f0 with nothing guarding it, yet in a recording of the
  real game no theme is heard when you die in a challenge, nor on the retry screen that follows.  What plays
  there is that screen's own sting, a random `gameover_1..3` started by `-[ADChallengeFailedViewController
  viewDidLoad]` 0x100071718 at 0x071c90, and the theme returns only at the challenge selector.  Checked and
  ruled out as the cause: `startMenuMusic:` 0x100082ca0 and its two early exits, `killGameplay` 0x10005c170
  and its 0.1 s block, `playListWithName:` 0x1000fc050 (cached, still returns the playlist once deactivated),
  `activate:` 0x1000fe9c0 (it only skips while already activating), the retry screen's own `viewDidLoad`, and
  all three callers of `stopMenuMusic`.  The mechanism is unidentified - most likely something in S3D's
  asynchronous activation on the device - so this one item follows the ear rather than the line.  Pressing
  End Challenge never reaches here at all, which is why that path was already silent.
* A wave is not reported cleared before its sounds exist.  `-[ADBrick initSounds]` 0x10009f274 builds a
  wave's `ADSound`s inside the playlist's activation callback (the block at 0x10009f4c0), so for a short
  window after the wave loads its `sounds` array is empty although the wave has some, and `brickIsCleared`
  0x1000a1658 walks the enemies and then that empty array and answers "yes".  A wave whose only content is a
  cutscene - tutorial_7_brick_4, the closing line of "Meet The Farty", has no enemies at all - therefore
  looked finished the instant it loaded, and the challenge ended before its sound existed.  On the phone the
  callback lands before anything can ask; here the question arrives first, because a kill produces a second
  deactivation right behind the one that advanced the wave.  A wave that is supposed to have sounds is not
  cleared until it has them - unless its playlist is missing altogether, in which case the sounds can never
  be built and waiting for them would never end.
* Escape on the challenge-completed screen returns to the challenge list (user request).
  `-[ADChallengeCompletedViewController backButtonPressed]` 0x100048728 stops the screen's animations and
  calls `goToMainMenu` at 0x100048804, which on the phone is a one-finger scrub back out of the whole
  challenge flow: the next challenge was then three screens away again, through Play, the world and the
  list.  Escape now calls what the screen's own Select challenge button calls, `missionSelectButtonPressed`
  0x100068f64, so it returns to the list the challenge was started from, and the main menu is one Escape
  further through the world selector.  The button itself is unchanged, and the challenge-failed screen
  (`backButtonPressed` 0x100072004) still goes to the main menu as the original does.
* Returning to the menus does not replay the opening sting (user request).  When a fade ends,
  `reduceMainMenuThemeVolume` 0x100083460 restarts the music through the whole of `startMenuMusic:`
  0x100082ca0, which plays `main_menu_open` - a 13.2 s sting that the theme only joins at 70 per cent of it
  (the monitor block at 0x100083178).  That is right for menus opened fresh, but this call is a *return* to
  the menus, so leaving a finished challenge for the challenge list played the whole intro again before the
  music came back.  The theme starts directly on that path; launching the game, the main menu and every
  other path still play the sting.
* `game_over_theme` and `main_menu_theme` are treated as one track, because they are one file.  Both are
  2,121,278 bytes with the same SHA-256: a single 129-second piece of music shipped under two names.  The
  original treats them as different tracks, so `startMenuMusic:` 0x100082ca0 finds "the track you asked for
  is not playing", calls `stopMenuMusic` at 0x082dc4 and restarts the same music from the beginning - you
  hear it fade out and start again for no audible reason every time you leave a finished challenge for the
  challenge list, or arrive at the completed screen.  The opening sting counts as that music too, being its
  front.  Asking for either name while either is playing now leaves it alone, so the music runs continuously
  from a challenge's closing line through the completed screen and back into the menus.
* PORT ADDITION removed: the gameplay screen used to speak "Skip" when the skip button appeared.  The
  original posts `UIAccessibilityLayoutChangedNotification` with a nil argument (0x1000da8c4), which tells
  VoiceOver the screen changed without speaking or moving the cursor, so every dialog in a challenge was
  being interrupted to announce a button that the key bindings already cover.
* A menu-music request made during a fade is no longer lost.  `startMenuMusic:` 0x100082ca0 returns at
  0x082db0 whenever the theme being asked for is playing, taking that to mean "already playing, nothing to
  do".  While a fade is running that theme is on its way out, not staying, so the request was dropped and
  `startThemeAfterFade` never set: the fade finished, stopped everything, and nothing started it again -
  which left a whole round silent after a quick Try again.  A dying theme no longer counts as playing.
* A playlist can no longer be wedged into never activating again.  `-[S3DPlayList activate:]_block_invoke`
  0x1000fed40 clears `activating` only on the no-completion path (loc_1000ff1c0, the store at 0x0ff1c8).
  Asked to activate a playlist that is already active *with* a completion, it dispatches the completion and
  branches to the epilogue at loc_1000ff198 without clearing the flag, so `activating` stays 1 for good and
  every later `activate:` returns at the guard in 0x1000fe9c0 with its completion never run.  For `main_menu`
  that is silence until the game is restarted, which is what it sounded like: the music stops and no menu or
  replay brings it back.  The flag is cleared on both paths here; the completion still runs either way.
  0x1000fed40 clears `activating` only on the no-completion path - the store at 0x0ff1c8, under
  loc_1000ff1c0.  Asked to activate a playlist that is *already* active and given a completion, it logs
  "ALREADY active, skipping", dispatches the completion, and branches to the epilogue at loc_1000ff198
  without clearing the flag.  `activating` then stays 1 for the rest of the run, and every later
  `activate:` returns at the guard in 0x1000fe9c0 with its completion never run.  For `main_menu` that is
  silence no menu, replay or new challenge can undo - the shape of "the music stopped and never came back".
  The flag is cleared on both paths here; the completion still runs exactly as before.
* PORT ADDITION: the cursor lands on the screen's own first element, not on the status bar.  VoiceOver
  starts at the first element of a screen, which on every screen with a status bar is its Back button, then
  the coins and the diamonds - three pieces of chrome to walk past before reaching what the screen is for.
  `AccessibleScreen.first_content_element` skips the status bar's subtree (view #87, which owns Back, the
  currencies and Armory) when nothing else has decided where to go.  They are all still there, one step
  back.
* PORT ADDITION: Settings -> Miscellaneous -> Remember cursor position, **off by default**.  When it is on,
  leaving a screen records the label the cursor was on and returning puts it back there - matching by label,
  since the rows are new objects after the rebuild.  Off, a screen opens at its first element the way the
  original always does.
* PORT ADDITION: a menu music volume, changed with Page Up and Page Down on any menu screen
  (`screens.menu_music_volume_key`) and kept in settings (`GameParameters.menu_music_volume`, defaults key
  `menuMusicVolume`), 0 to 100% in steps of 10, 100% by default; Reset all settings puts it back.  The keys
  do nothing while the screen underneath is the gameplay, so the pause and revive screens leave them alone
  too, and a key being captured for a binding in Settings -> Keyboard takes Page Up like any other.  It
  applies to the three sounds of the `main_menu` playlist - `main_menu_open`, `main_menu_theme` and
  `game_over_theme`, which is all that playlist holds - through `S3DSound.volume`, a factor on top of the
  gain the game sets (0.4 on the sting and on the theme, `startMenuMusic:` blocks 0x100082f74, 0x10008308c,
  0x10008324c).  100% is that gain unchanged, so the music is never louder than the
  original's.  The volume is kept apart from `gain` because `reduceMainMenuThemeVolume` 0x100083460 fades by
  taking 0.01 off the gain every 0.05 s until it reaches 0: scaling the gain would change how long the fade
  lasts.  The percentage is squared into a gain so the steps sound even.  The ends hold rather than wrap.
* PORT ADDITION: game controllers - see *Gameplay controls* for the bindings and the turning.  A controller
  connecting or going is announced; a button held when it goes is let go.  In the menus a controller button
  stands for a key (the D-pad and sticks for the arrows, Cross Enter, Circle Escape, Square Shift+Enter,
  Triangle Delete, L1/R1 the tab arrows, L2/R2 Page Down/Up), and those key presses carry `pad`, so a key
  being captured in Settings -> Keyboard is cancelled by a controller button instead of taking the key it
  stands for.  SDL is asked (before pygame.init) to let PlayStation pads rumble over Bluetooth.
* PORT ADDITION: SAPI 5 is spoken on a thread of its own, and the game plays it rather than Windows
  (`platform/speech_audio.py`, `speech._SapiThread`; Settings -> Speech -> **Modern audio output**, on by
  default, `sapiModernAudio`).  Two things were measured on the user's machine and both are fixed here.
  Every SAPI call costs the thread that makes it - 10 ms to hand over a line, 26 to 30 ms when it cuts off
  the one before, up to 50 ms to stop - which on the main thread is a stutter in the arena each time a row
  is read; the calls are made on `_SapiThread` now, and handing over a line costs the game 1.3 ms.  And
  SAPI hands its audio to Windows, which buffers it: asked to stop, the voice keeps talking for what is
  already on its way to the card - 29 ms after 50 ms of speech, 59 after 200, **100 after 500**, growing
  the longer it has been talking - which for a player who interrupts at every row is most of what makes a
  voice feel slow.  With Modern audio output on, SAPI renders the line into an `SpMemoryStream` at the
  engine's own rate and shape (44.1 kHz, stereo, 16 bit, so nothing is resampled; 160 to 220 times faster
  than real time) and `SpeechAudio` plays it through a source of the game's own, filled by an
  `AL_SOFT_callback_buffer` callback as the reverb bus is, `AL_DIRECT_CHANNELS_SOFT` so a voice is not put
  through the HRTF.  Stopping is then dropping what has not been played, which is instant (measured: a line
  with 512,808 samples still to play is down to the 352 of its fade the moment the next line is asked for),
  with 4 ms of ramp so the cut is not a click.  A `generation` counter carries the interruption to the
  thread: a line whose generation has passed is dropped rather than spoken.  With the row off - or with no
  engine to play through, or if a render fails - SAPI speaks to Windows as it always did, and that path
  stops better too: `ISpeechAudio.SetState(STOP)` before the purge, which halves the tail (100 ms to 45).
  NVDA solves the same problem the same way and calls it the same thing, so its players know the name; none
  of its code is here (it is GPL), and the two are not alike inside - NVDA streams through an `ISpAudio`
  object of its own into its WASAPI player, where this renders to memory through SAPI's documented stream
  and plays it through the engine the game already has.
* PORT ADDITION: what a controller makes you feel (`platform/haptics.py`).  The original never vibrates.
  The proximity heartbeat (`ADPlayer`, player.py) pulses the heavy motor on each beat, scaled as the sound
  is (closeness squared * 0.7 + 0.3).  The rest is felt where it happens to a zombie, so a bullet, a melee
  blow, a projectile and a power-up are all caught the same way: `hitByWeapon:` 0x100060b30 and
  `hitByExplosionAtPosition:...powerupname:` 0x100061284 (which `hitByProjectile:` 0x100061098 calls) pulse
  by the damage the zombie actually lost (0.6 + 0.4 * (damage / 80) ^ 0.6 of full strength, the floor raised from 0.5, which left a small gun faint, so a Micro SMG
  hit is felt and a Bazooka's is felt more), melee as a longer, heavier thud; a shot the shield takes
  (state 6 in `hitByWeapon:`) is a light knock; `die` 0x100061ac8 is a kill; `attack` 0x100060304, the blow
  that kills you, a second of heavy rumble.  `solveExplosionWithDictionary:...` 0x1000c5c40 - a projectile,
  a Farty going off (`explode` 0x100061e6c), the fireworks power-ups - is a rumble by its distance from you
  (full within a metre or so, never under a half), and `blowEnemiesAway:` 0x1000c3e88 (the tornado) a soft
  gust when it pushes anything.  A diamond and a power-up container die like anything else, so `die` hands
  what it is felt as to `Enemy.felt_death`, which `ADDiamondDropper` and `ADPowerUpContainer` override
  (passerby.py): two bright ticks for the diamond, a crack for the crate, neither a kill's low thump.  The
  power-up itself is felt when it takes effect rather than when the crate opens - `-[ADPowerUp activate]`
  0x10001db08 reads the announcement first and `activate:_block_invoke` 0x10001dc6c uses the power-up when
  it has been read, so the swell goes there, behind the `use` the block already made.  It starts with the
  power-up's own sound rather than with the block (user request): `PowerUp.felt_sound` is the deploy the
  `use` has just played - the Tesla's, the Tornado's and the Fireworks' launch, the Minigun's fire loop -
  and `felt_when_it_starts` waits a run-loop pass at a time until that sound is playing, since a sound not
  yet on the card is loaded by being played and starts a moment after `play:`.  After a second of passes it
  is felt anyway.  It then runs as long as that sound does, waveform and motor pulse alike (`felt_start`),
  and for the Minigun, which plays no launch sound at all - `minigun_launch_a/b` are in the playlist but
  `use` 0x1000b2850 only ever plays `minigun_fire` - the 1.5 s `update:` 0x1000b2934 holds its fire for
  while it spins up.  A launch sound has no duration when it is asked for, so the length comes from the
  decoded file the playlist prewarmed, and anything still undecoded falls back to 0.6 s rather than making
  the game wait.  `FELT_START_MAX` caps it at 3 s: the Tornado's launch is 5.7 s and the Fireworks' 5.6,
  which is the whole thing coming in rather than a start, and a rumble that long reads as a pad fault; the
  Tesla's 2.74 s deploy is under the cap and is felt whole.  Two of the four are then felt while they work
  (user request): `-[ADMinigunPowerUp update:]` 0x1000b2934 asks for the gun's own buzz every
  `Haptics.SUSTAIN` (0.12 s) once it is past the spin-up, which goes through the pass's pulse like anything
  else - so a hit it lands is felt *over* the gun rather than instead of it, the motors taking the stronger
  of the two and the grips playing both - and `-[ADTeslaPowerUp update:]` 0x1000d786c cracks when the coil
  takes a zombie, over the kill `setLife:` has just made: high where the kill is low, so the two read as
  one thing.  Neither reaches a DualSense's motors, which the grips carry better.  The menus
  are felt too, and at a strength the hand notices (user request): `ui/accessibility.menu_tick` for the
  cursor moving (`_move`, `_jump`, `MenuScreen.move` and the category and tab keys), 60 ms on both motors,
  as firm as the pulse Settings plays when a strength is stepped; `menu_toggle` for anything activated
  (`View.activate` and `MenuScreen.activate`, so every setting stepped or toggled and every button
  pressed), firmer and longer; and `ScreenManager._felt_screen_change` for a screen, two knocks low to high
  going in (`push_overlay`, `load_view_controller`) and high to low coming back out (`pop_overlay`, only
  where it refocuses - the pops that clear the stack are not a way back), so which way you went is felt as
  well as heard.  None of these reach a DualSense's motors: the grips carry them, and the motors would
  drone through a menu.  What happens in one pass of the run loop is felt once: each kind at its
  strongest, a little firmer for each more of it, the motors at the strongest kind.  A DualSense on USB is
  a four-channel sound card to Windows as well, whose third and fourth channels drive its two haptic
  actuators; `platform/haptic_audio.py` opens it through SDL's audio (pygame._sdl2.audio, 48 kHz float) and
  plays the heartbeat recording the game has just played, low-passed to the actuators' range, and short
  sine knocks, thuds and filtered-noise rumbles for the rest, saturated (`haptic_audio.fat`) so each
  carries as much as it can under a peak of 1, which is what those actuators answer to.  An
  explosion, a death and a kill go to that pad's motors as well (`RUMBLE_AS_WELL`), the fine haptics
  having no weight for the big low things; a bullet's hit and the rest are the fine haptics alone,
  which do not drown the game's sound.  Settings -> Miscellaneous -> Fine haptics (`fineHaptics`, on by
  default) turns the grips off, so such a pad is felt through its motors like any other - for hearing what
  everyone else feels, and for a pad whose fine haptics are not wanted.  Vibration scales every pulse
  (0.4, 0.7, 1), and Strong is
  the pad at full, so anything more has to come from the pulses themselves.  The three were 0.6, 0.85 and 1,
  where Medium and Strong felt alike - a waveform is felt by its height the way a sound is heard by it, and
  0.85 of full is under a decibel and a half down - so they were set well apart and then lifted a little
  (both user requests).  Over
  Bluetooth there is no such card and it rumbles.  Shaking a pad that has an accelerometer (SDL's sensor,
  reached through pygame's own SDL2.dll) calls `motionEnded:withEvent:` 0x10005a108 as the phone's shake
  does, so it swings the melee weapon under Gesture and does nothing under Button; the threshold is 25 m/s2
  against gravity's 9.8, once per half second.  A DualSense's adaptive triggers get the pad's simple
  effects through `SDL_GameControllerSendEffect` - R2 is the pad's weapon effect, shaped like a pistol's:
  take-up to 55% of the travel with nothing in it, the wall from there to 72%, and the break at 72% is the
  shot (`Pads.trigger_points`: R2 with that feel on it presses through the wall at GUN_DOWN and resets at
  GUN_UP, just under the wall, as a pistol does; every other trigger keeps the plain half-way TRIGGER_DOWN,
  having no wall to press through); L2 (reload under Button) is a light spring - only while the game is in
  front;
  a pause, the menus and closing the game set them plain.  Settings -> Miscellaneous -> Joystick vibration
  and Trigger feel set how strong both are - Off, Light, Medium or Strong (`vibration` and `triggerEffects`
  in settings.json; Medium by default, and reset by Reset all settings; a stored true or false from before
  is read as Medium or Off), and the Trigger feel's hint says that only a DualSense has
  one.  Vibration scales every pulse (0.4, 0.7, full); the trigger levels are the effect's strength
  byte (R2 0x14 / 0x28 / 0x50, L2 0x0C / 0x18 / 0x30).  The scale was softened a step after playing with
  it: 0xC0 was too stiff to fire with, and at 0x28 / 0x50 / 0x90 Medium was still hard, so what was Light is
  Medium now and Light is softer than anything there was.  Stepping the row gives a connected DualSense that
  feel for eight seconds (`ControlSchemePanel.sample_triggers`), since the triggers are a game's feel and no
  game is running while you choose it; leaving Settings makes them plain again.  Settings -> Miscellaneous -> Names in hints and tutorial (`keyNames`: Keyboard keys by
  default, or Controller buttons) names a connected pad's buttons, in its family's names (`pad.family`,
  from the name SDL gives it): every row's hint turns the keys a menu button stands for into that button
  (`pad.menu_words`: Shift+Enter, Enter, Delete and Escape become Square, Cross, Triangle and Circle, or X,
  A, Y and B), as do the three labels of the port's that name Enter (a power-up's "press Enter to upgrade",
  a tarot card's "press Enter to change", a challenge's "press Enter to go to armory";
  `View.label_key_words`, worked out as they are spoken, so a pad coming or going is followed at once), and
  the tutorial text, the skip-intro line, `cross_axis_text` ("L1 and R1 change tab, D-pad left and right
  move through it") and the Button / Gesture rows name its game buttons.  With several kinds connected,
  Controller for names (`keyNamesController`) chooses which; otherwise it is the one connected last.  With
  none connected the row is dimmed (a dimmed cell says so, as a dimmed button does), and starting the game
  with none, or the last one going wherever the player is, sets `keyNames` back to Keyboard keys and saves
  it (`Pads._keys_when_none`).  A pad coming or going tells the host (`Pads.changed` ->
  `ScreenManager.pads_changed`), so Settings -> Joystick and Miscellaneous lay themselves out again and a
  button being set for a pad that has gone is given up.  Each kind of pad has its own bindings
  (`PadMap.for_model`, `padmaps` in keys.json, keyed by that name), made from the defaults and saved the
  first time it connects; the one set there was before (`padmap`) is taken over by the first kind connected
  after.  In play each pad's buttons go through its own (`Pads.padmap_for`), and each DualSense's trigger
  feel follows its own Fire and Reload.  Settings -> Joystick rebinds the buttons of the pad its Controller
  row names (with several kinds connected, Enter and Shift+Enter step through them) as Keyboard does keys
  (`PadMap.add` / `set` / `remove_last`, per scheme for Next weapon and Reload), and lists none with no pad
  connected; while a button is being set the host hands the screen the pad's presses as they are
  (`takes_pad_input`).  A stick pushed sideways and the guide button cannot be bound.  Turning is both:
  either stick turns as far as it is pushed and is the pad's own, while `turn_left` and `turn_right` are
  bound to the D-pad to begin with and can be set to any button (user request; `PAD_LABELS` names their
  rows Alternate turn left and Alternate turn right, under the Turn row that says what the sticks do).  A
  button turns at the keyboard's speed, being down or up with nothing in between, and goes through the
  same `GameplayScreen.press` the turn keys do; while one is held it decides, and the sticks have it back
  as soon as it is let go.  `_turn_keys` maps what is held - a key code, or a pad button's source - to the
  action it pressed, so the last one pressed decides whichever it came from.
* A fresh profile plays in **Gesture** (user request).  `-[ADGameParameters lastButtonMode]` 0x1000a3aec
  answers `UIAccessibilityIsVoiceOverRunning()` when `buttonMode` is not stored, which in the port is
  always true and so put every new player in Button mode; `GameParameters.DEFAULT_BUTTON_MODE` is False
  instead.  Only a profile with nothing stored is affected: `__init__` writes the mode the first time the
  game runs, so anyone who has played keeps what they had, whether they chose it or the original chose it
  for them.  Settings -> Controls still steps between the two.
* PORT ADDITION: Settings -> Miscellaneous -> Reset all settings (`ControlSchemePanel.reset_all_settings`)
  puts every setting back to what its getter answers when nothing is stored - control scheme 1 (Gyro), the
  turn sensitivity, the button mode (Gesture, as a new profile is), the announcer on, tutorial text,
  menu arrows, cursor memory, the update check, the menu music volume, the vibration and the trigger feel,
  the names in hints and tutorial, and the speech output - through the same setters the rows use.  The key
  bindings are left alone (Settings -> Keyboard has its own Restore default keys), and so are the
  controllers' buttons (Settings -> Joystick -> Restore default buttons).  The original has no reset; this
  one replaced the port's own Restore aiming defaults and Restore menu defaults rows.
* PORT ADDITION: Settings -> Speech -> Speech output (`speechOutput` in settings.json,
  `Speech.choice`, `platform/speech.py OUTPUTS`): Automatic by default - NVDA through its controller
  client, else another screen reader through Prism, else SAPI 5 (`Speech.speak_automatic`) - or one of
  NVDA, JAWS, ZDSR, Narrator, ZoomText, System Access, Window-Eyes, PC-Talker, Boy PC Reader, Sense Reader
  and SAPI 5 only (the Prism ones through `_Readers.current(only)`), with nothing spoken while that one
  cannot speak.  Automatic tries the Prism ones in that same order, not Prism's own (which puts PC-Talker,
  ZDSR and Boy PC Reader before JAWS, and Narrator last).  Enter and Shift+Enter step through them and
  wrap.  The row says each step through the new choice or, when that one cannot speak (`Speech.can_speak`),
  through the automatic one with the reason ("JAWS is not running, so the game will be silent until it is",
  or that Prism is not installed): said through the choice itself, it would not be heard, and a player
  stepping through would not know where they had landed.  The game reads the choice as it starts
  (`__main__`), and the log says when the chosen one stops being able to speak and when it can again.
  While SAPI 5 is what speaks - chosen, or Automatic with nothing else running
  (`ControlSchemePanel.sapi_speaking`, looked at once a second while the category is open, so the rows come
  and go as a screen reader starts or closes) - rows for SAPI 5 itself follow (`_Sapi`, `sapiVoice` / `sapiRate` /
  `sapiRateBoost` / `sapiPitch` / `sapiVolume`): the voice - Control Panel's, as a new SpVoice starts on,
  then every installed token - the rate (-10 to 10) and the volume (0 to 100 in tens), which are SpVoice's
  own properties and start at Control Panel's, and the pitch (-10 to 10), which SAPI has only as XML,
  `<pitch absmiddle>`.  The rate boost is `<rate speed="10">` on top of the rate; some voices go faster
  that way than rate 10 allows and some do not (here Zira did, US Paul and BestSpeech Fred did not), so
  each voice is tried once a session, speaking a line into memory both ways (`boost_supported`), and the
  row is offered only where it helps.  NVDA's own SAPI 5 rate boost is another thing: it speeds the voice's
  audio up with the Sonic library, which the port does not have.  The XML is sent only while the pitch or
  the boost is in use, since a voice may take XML oddly; otherwise the text goes as plain text
  (SVSFIsNotXML), never parsed.  Each change is said in SAPI 5 at the new setting, whatever else is
  speaking.
* DIVERGENCE: a dead player can no longer fire, melee, reload or switch weapons.  `showDeathOverlay` brings
  the death overlay to the front of the gameplay view and gives it `userInteractionEnabled` (0x10005b9e4 and
  0x10005ba20; the challenge controller's own at 0x1000db814), so on a phone it swallows every touch and the
  weapon views beneath it stop responding.  Endless also sets `paused`, which the port already honoured; the
  challenge controller does not, so a dead player kept firing until the failed screen loaded.  Keys are not
  routed through the view hierarchy here, so the overlay is honoured explicitly in `GameplayScreen.key_down`.
  Pause, skip and the timer are handled before that gate and still work, and `key_up` is left ungated so a
  key held at the moment of death still releases cleanly.
* The Swipe aim scheme applied the turn sensitivity twice.  `touchesMoveDetected` 0x10005a3e0 multiplies the
  drag by the sensitivity, as the original does; the port's own key-to-drag generator scaled the drag rate
  by it as well, so Swipe turned with the *square* of the setting while Gyro and Tilt were linear -
  26 degrees a second at 0.5 and 634 at 3.0, against Gyro's 38 and 224.  The port's generator now runs at a
  fixed rate and leaves the scaling to the original's own line.  Measured after: 53.6 / 105.5 / 158.2 /
  211.0 / 316.5 degrees a second at sensitivity 0.5 / 1.0 / 1.5 / 2.0 / 3.0 - linear, like the other two.
* PORT INPUT: the three aim schemes describe themselves by speed.  On a phone Gyro, Swipe and Tilt are three
  different devices; on a keyboard all three are the turn keys held down, and what actually separates them
  is the rate each code path turns at - about 110, 160 and 190 degrees a second at the default sensitivity,
  all scaling in proportion to it.  The rows say so, in place of the original's GYRO_DESCRIPTION,
  SWIPE_DESCRIPTION and TILT_DESCRIPTION, which tell the player to move the handset.
  it was last focused on (`_LAST_FOCUS` in `ui/accessibility.py`) and restores it when it is entered again,
  matching by label because the rows are new objects after the rebuild.  The original rebuilds the screen
  and VoiceOver starts at the first element every time, so leaving a challenge, the armory or the settings
  meant walking back down the list.  A screen seen for the first time opens where it always did.
  0x082db0 whenever `main_menu_theme` is playing, reading that as "already playing, nothing to do".  During
  the 2 s fade `stopMenuMusic` runs (0x100083460, 0.01 of gain every 0.05 s from 0.4) that theme is on its
  way out, so the request is dropped *and* `startThemeAfterFade` is never set; the fade then stops
  everything and nothing starts it again.  Every challenge-ending dialog carries `startMusicBeforeEnd`
  (3 seconds, 5 in tutorial 3), so pressing Try again quickly enough put the next round's request inside
  that fade and left the whole round silent - which is why it would not reproduce to order.  A theme that is
  fading no longer counts as playing, so the request falls through to `startThemeAfterFade`, which
  `reduceMainMenuThemeVolume` already honours when the fade ends.  Scoped to `main_menu_theme`, the only
  track that flag restarts, so the game-over paths are untouched.
* The armory's Back button takes one step, not two.  `backButtonPressed` 0x100076080 hands the press to the
  open detail view (`handleBackActionFromStatusBar` at 0x076120), clears the delegate, and then dismisses
  the armory anyway in the tail call at 0x0761b8 - so one press closed the weapon page *and* threw you out
  of the armory, skipping the list.  Back now matches Escape (`accessibility_perform_escape`): it closes the
  detail and leaves the cursor on the row it was opened from, and a second press leaves the armory.
* The statistics screen speaks a weapon's exact accuracy (user request).  `configureWeaponCell:ForRow:`
  0x1000d0ff0 builds the label at 0x0d129c from everything before the first dot of the accuracy's string
  value, so 66.6 per cent is announced as 66; and a weapon that has never been fired has shotsHit /
  shotsFired = 0 / 0, which is nan, so its row is read out as "accuracy, nan percent".  The figure is spoken
  to one decimal instead, and a weapon with no shots says so.
* PORT ADDITION: every screen names itself as you enter it - "Main Menu. Play, button".  These are the
  game's own names: each of these controllers sends `-[ADStatusBarViewController setPageTitle:]` in its
  `viewDidLoad` (ARMORY, PLAY, CHALLENGE, ZOMBIPEDIA, STATISTICS, INFO, GAME OVER, Credits, Dr Bastard's
  Tarot, Challenge completed), and the iPhone nib has no `pageTitle` outlet, so every one of them goes to
  nil and is never seen or heard.  The capitals are not shouted, and four screens are named for the button
  that opens them rather than for the original's title, so the two agree: the main menu is "Main Menu" and
  not "AUDIO DEFENCE"; the stats portal, which the main menu's Info button opens, is "Info" and not
  "AUDIO DEFENCE"; `ADInfoViewController` says which page you opened - "Challenge Info" or "Endless Info",
  after the two buttons on the play menu - instead of the original's bare "INFO"; and the tarot screen is
  "Endless", since it is how Endless starts and the button that reaches it says Endless.  Settings has no
  title in the binary at all and is called "Settings".
  The challenge screens all set "CHALLENGE", which made four different screens announce the same word, so
  each is named for the row that opened it: the world list keeps "Challenge" (the play menu's button says
  that), a world's challenge list takes the world's name from `challenges_index.plist`, a challenge's
  overview takes that challenge's `title`, and the failed screen is "Challenge failed" to sit beside the
  completed screen's own "Challenge completed".  A screen
  that already names what it opened, like the armory's tab, is not made to say it twice.
* PORT ADDITION: the tutorial announcer's lines are also spoken as text, with the keys you have bound
  (`game/tutorial_text.py`, hooked into `-[ADSound play]` 0x1000b416c).  The announcer tells you to tilt the
  device, swipe, or tap a corner button, none of which a keyboard can do.  The brick scripts name these
  sounds with a placeholder - `announcer_tutorial_aim_CONTROLMODE`, `announcer_tutorial_shoot_BUTTONMODE` -
  which `init_sound` 0x1000b3594 resolves against the control scheme and the button mode, so the three aim
  variants share one line and each button/gesture pair shares another.  Rebinding a key changes what is
  said.  With a controller connected and Settings -> Miscellaneous -> Names in hints and tutorial on Controller
  buttons, the lines name its buttons instead ("the R2 button", "a stick flicked up"), aiming is "To aim,
  push either stick left or right", with the buttons that turn named after it by whatever they are bound to
  ("or press the D-pad left button or the D-pad right button", `PAD_AIM_BUTTONS`; with neither bound the
  sticks stand alone).  It says what it is for first, as the melee line does, since a screen reader reads
  the chain of buttons straight through and the purpose would otherwise arrive last.  Under Gesture the
  melee line offers the shake as well ("or shake the controller") when the controller being named has the
  sensor for it (`Pads.can_shake`).  `aimhelp` and `aimprompt` name
  no key and have no line.  Settings -> Miscellaneous -> Tutorial
  text chooses "As the announcer speaks" (the default), "After the announcer finishes", or "Off".
* PORT ADDITION: an action can hold several keys, and the binding rows say how.  Enter adds a key,
  Shift+Enter replaces every key the action has, and Delete removes the one added last; an action is never
  left with none.  The storage was already a list per action - only the rebinding screen was one key at a
  time.  Melee is bound to both Ctrls by default, so it is under whichever hand is not on the turn keys.
* PORT ADDITION: changing a tarot card says the new card.  `changeCardButtonPressed:` 0x1000a62b8
  rewrites the card's `accessibilityLabel` in place, under a cursor that is already sitting on it, and a
  screen reader reads a label when it is moved onto one - not when one changes beneath it.  On the phone
  that mattered less: VoiceOver users flipped with a double tap and swiped on.  Here the card you had
  just paid three diamonds for could only be heard by arrowing off it and back.  It now speaks
  `View.spoken()`, which is the exact text the arrow keys produce when the cursor lands on that card, so
  a changed card is heard as any card is heard.  `announce_card` in `ui/tarot.py`.
* DIVERGENCE (user request): a paused game no longer reloads.  `pauseGame` 0x10005b5fc stops the timers
  and pauses the bricks and the ambience, and says nothing about the weapon, so two things went on
  through a pause.  The reload sound is not a brick's and kept playing.  And `-[ADWeapon update:]`
  0x100014c8c advances `timeInState` by the wall clock between calls rather than by the timer's dt (the
  quirk at the top of `game/weapon.py`), so the first pass after resuming credited the entire length of
  the pause to whatever state the weapon was in: pausing during a reload finished it, however long the
  reload and however long the pause.  Pausing mid-reload was a free reload and a way to stop the clock
  while getting one.  `Weapon.pause` / `.resume` pause the reload and continuous sounds and re-base the
  wall clock on resume, and `pauseGame` / `resumeGame` send them through the weapon manager.
* TRIED AND REVERTED: placing the melee hit on the enemy.  A melee weapon has two recordings, `_miss_`
  and `_hit_`, and the original plays both with `setSpatialized:NO` (`-[ADMeleeWeapon playHitSound]`
  0x100007538, `playMissSound` 0x100007610), so a swing that connects arrives at the head exactly like
  one that does not.  A version of this port placed `_hit_` on the enemy that was struck and played
  `_miss_` at the player for the swing, since the enemy makes no sound of its own for a melee blow -
  `playImpactAndHitSoundForDamages:melee:` 0x10006150c skips the impact sound when `melee` is YES - so
  nothing at all said where the blow landed.
  It shipped in 26.09.22-1 and the players did not want it, which settles it.  Two reasons worth keeping
  here so that nobody reaches for this again.  `_hit_` is not the impact on its own: it is the swing
  *and* the impact in one file, the wok's being 0.97 s of rising whoosh into the clang where `_miss_` is
  0.67 s of whoosh alone.  Splitting that across two positions cuts across a recording that was made as
  one, and it was heard as the impact being clipped rather than as the blow opening out.  And it was a
  deliberate change to a game that had not asked for one: a melee weapon sounding from the hand is what
  the original does, on purpose, and this port's business is that game rather than a better idea of it.
  The gain arithmetic that went with it is gone too; it is in the history if it is ever wanted.
* PORT ADDITION: Restart challenge on the pause screen.  `ADPauseViewController` offers Resume
  (`validateButtonPressed` 0x100055bbc) and End Game (`quitButtonTouched` 0x1000559c0) and nothing else,
  so a challenge already lost - a time limit missed, an accuracy that cannot be recovered - had to be
  played out to its end, or ended and then found again three screens away in the challenge list.  The
  button tears the run down the way End Game does (`MissionManager endGameplay`, then `killGameplay`) and
  starts the same dictionary again, which is what the failed screen's Try again does
  (`tryAgainButtonPressed` 0x100071ee8).  It is built only when the paused game has a challenge
  dictionary, so an endless run does not grow a button for a challenge it is not playing, and it sits
  between the two nib buttons so the order read is Resume, Restart challenge, End Game: least final
  first, most final last.
  The new game has to be started *after* `killGameplay`'s deferred block, not after `killGameplay`
  returns.  That block (0x10005c770, a tenth of a second later) ends in `BrickManager.clean()` and
  `WeaponManager.clean()`, both of which are the shared singletons rather than the dying controller's
  own, so starting the challenge straight away built the new arena first and emptied it a tenth of a
  second afterwards: an arena with nothing in it, and a weapon that still fired.  The delay is
  `KILL_GAMEPLAY_CLEANUP`, named where `killGameplay` schedules it so the two cannot drift apart.
* PORT ADDITION: the game updates itself, which on iOS was the App Store's job and has no counterpart in
  the binary.  `platform/updater.py` asks GitHub for the newest release, compares its tag with the
  version compiled into the executable (`compiler.py` writes the repository's `VERSION` into a module,
  `version.BAKED_MODULE`, so no file beside the executable can change it or be lost), and offers what it
  finds through the game's own alert rather than a Windows dialog, so a screen reader reads it like every
  other screen.  Two things are worth knowing.
  First, nothing a player owns is at risk by construction: every write the game makes goes to
  `paths.user_dir()`, the installed folder is read-only while the game runs, and the updater will not
  write outside the folder the executable is in - so replacing program files cannot touch a save.
  Second, the download is a delta.  The release is one zip of about 155 MB of which nearly all is the
  game's audio, identical in every build; `platform/remotezip.py` fetches the archive's central directory
  over HTTP byte ranges and compares each member's CRC-32 with the file already installed, so a
  code-only build downloads megabytes rather than the lot.  A server that will not serve ranges, or a
  zip64 archive, falls back to fetching the whole asset.  The last step cannot happen from inside the
  game, because a running program holds its own executable and DLLs open: the changed files are staged
  under `%APPDATA%\AudioDefence\updates` with a backup of what they replace, and a PowerShell script
  waits for the game to exit, copies them in, and starts it again - putting the backup back if the copy
  fails.  PowerShell rather than a `.cmd` because a player's folder can have non-ASCII characters in it.
  A download the player puts off is kept, marked ready, and offered again at the next start rather than
  fetched twice; the sweep that clears staging folders leaves that one alone.  The offer has three answers:
  Yes, No (asked again at the next start) and Skip this version (`GameParameters.skipped_update`: the check
  at start-up passes that tag over, a newer one is offered, and Check for updates on the main menu, being
  a question the player asked, still offers it).  The buttons carry hints, which UIAlertView's do not.
  `tools/verify_updater.py` proves the whole path offline, against a local server that serves ranges and
  a real hand-off, on a folder whose name has a space and Arabic in it.
* PORT ADDITION: key names are spoken as the keys people call them.  pygame's names for the two Enter keys
  are "return" and "enter", which read out as "Return or Enter" and sound like one key said twice; they are
  "Enter" and "Numpad Enter" here, the arrows are "Left Arrow" and so on, and space is "Spacebar".
* PORT ADDITION: the one defaults file is split three ways - `save.json` (progress: coins, diamonds,
  weapons, power-ups, missions, challenge data and the four stats blocks), `settings.json` (control scheme,
  button mode, sensitivity, menu arrows, cursor memory, tutorial text, the update check, a skipped update and
  the menu music volume) and `keys.json` (the key bindings, and the joystick later).  The game reaches all three through one `UserDefaults.standard()`, which routes each key by name.
  the figure at 0x0d129c from everything before the first dot of the number's `stringValue`, so a weapon
  that has never been fired (`shotsHit` / `shotsFired` = 0 / 0, which is nan) is read out as
  "accuracy, nan percent", and a real figure is cut at the decimal point - 66.6 per cent announced as 66.
  The port speaks one decimal place, trimming a trailing zero, and says "not fired yet" when there are no
  shots to divide.
  sends `startMenuMusic:@"game_over_theme"` at 0x0db7f0 with nothing guarding it, but a recording of the
  real game has no theme at the death nor on the retry screen that follows: what is heard is that screen's
  own sting, a random `gameover_1..3` playlist started by `-[ADChallengeFailedViewController viewDidLoad]`
  0x100071718 at 0x071c90, and the menu theme only returns at the challenge selector.  Ruled out as the
  cause, read as listings rather than digests: `startMenuMusic:` 0x100082ca0 (neither early exit applies),
  `killGameplay` 0x10005c170 and its 0.1 s block, `playListWithName:` 0x1000fc050 (a cache, still returns
  the playlist after a deactivate), `activate:` 0x1000fe9c0 (skips only while already activating), the
  retry screen's own `viewDidLoad`, and all three callers of `stopMenuMusic`.  The mechanism is
  unidentified - most likely something in S3D's asynchronous activation on the device - so this one follows
  the recording rather than the line, and is the only divergence here that is not read off the binary.
  Pressing End Challenge never reaches `showDeathOverlay`, so that path was already silent.
* The status bar's coins and diamonds counters keep their spoken labels in step with the number on screen.
  `animateCoins:` 0x10001c728, `animateDiamonds:` 0x10001c850 and their timer methods 0x10001ca14 /
  0x10001cb68 only call `setText:`; the accessibility label is set once by `setCoinsLabel:` 0x10001d278 /
  `setDiamondsLabel:` 0x10001d394 and refreshed only by `refreshCoinsAndDiamonds` 0x10001c3d0, which the
  tarot screen never calls - so in the original a VoiceOver player hears the count from before the purchase
  until some other screen happens to refresh it, while the screen itself is right the whole time.
* A tarot card you pay to change is stored.  In the original only `-[ADTarotViewController
  loadCardWithNumber:]` 0x100035390 writes `tarotCardN`, and only when the key is missing;
  `changeCardButtonPressed:` 0x1000a62b8 and `changeCard` 0x1000a65a4 never touch it, so leaving the screen
  and coming back deals the stored card again and the diamonds are gone.  `change_card` now saves the new
  modifier under the same key.  Nothing else moves: `applyAllModifiers` 0x100035a5c still reads the live
  card, and `resetCardsModifiersIfNeeded` 0x1000d42a8 still clears all three keys after an endless game
  lasting over 60 seconds, so a fresh deal still follows a real run.
* After a tarot card is paid for, both cards' "You have N diamonds" hints are rebuilt.
  `changeCardButtonPressed:` 0x1000a62b8 calls `changeCard` (0x1000a63fc, ending in `refreshCard`) before
  `setDiamonds:` at 0x1000a6518, so the hint was built from the old balance; the card that was not changed
  was never refreshed at all and kept the number it was dealt with.  The amount taken is unchanged
  (3, 2, 1 diamonds by card level, `viewDidLoad` 0x1000a4bd4).
* The loadout tab names the currency a locked weapon is actually sold in.  `weaponStatus:` 0x100049c1c
  always formats the `price` key as "Locked, costs : %i coins", so the Sonic Cannon - which only has
  `priceInDiamonds` - was announced as "costs : 0 coins" while its own detail view said "Buy for 100
  diamonds".  The split used here is `checkBuyOrUpgradeButton`'s own (0x10006fa68): a price below 1 means
  the diamond price.  This line is only in the accessible loadout; the sighted `ADArmoryLoadoutViewController`
  is a drag-and-drop scroller with no price text.
* A tarot card says how many diamonds you have now, not when it was dealt.  `-refreshCard` 0x1000a58e0
  builds the card's hint, "You have N diamonds", when a card is dealt and when one is changed, and nothing
  runs it when the screen comes back - the armory is presented over this screen, so spending in it leaves
  the card quoting the balance from before.  The words are rebuilt as the screen reappears.  Only the
  words: the card, its cost and its action are untouched, because `refreshCard` also re-adds the card's
  target, and doing that twice would change the card twice, and charge twice, on one press.
* The price on a power-up's Upgrade button is right the moment it changes.  `upgradeButtonPressed:`
  0x10004e1b4 ends by asking for `loadInformation` a second later (the `dispatch_after` before
  0x10004ea84), because that second is the badge animation; the button's words are the next level's price,
  so for that second it offers a price that is no longer the one you would pay.  Sighted, the animation
  covers it.  With a screen reader, stepping off the button and back inside that second reads the old
  number as fact.  The words are refreshed at once, and the delayed call still runs, so the animation ends
  as it did.
* PORT ADDITION: three table rows that answered a key with nothing now click.  The original's buttons
  click - `-[ADButtonWithFont playSound]` 0x100073578, the status bar's and the play menu's being the same
  code - but its table rows never do.  Sighted, that is fine: the screen visibly changes.  On a keyboard,
  with the screen reader still finishing the row you were on, a press that makes no sound is
  indistinguishable from a key that did not register.  The three are the challenge selector's rows
  (`tableView:didSelectRowAtIndexPath:` 0x100054f8c, which opens the overview and is the only silent step
  of Play, world, challenge), the Zombiepedia's names (`cellSelectedWithZombieName:` 0x10007abcc), and its
  Preview sound button (`handleTapForSound:` 0x10008b9b4, where the zombie itself is held back a second by
  `dispatch_after` at 0x10008ba58 so it does not fight VoiceOver - a second that sounded like nothing
  happening), and the challenge-failed screen's Challenge selection (`missionSelectButtonPressed:`
  0x100071e1c, whose sibling on the completed screen does call `playButtonSound`, so the two screens
  answered the same key differently).  A challenge row locked by its requirements stays silent, because
  nothing happens.  This is the same reasoning as the Settings rows, which are `ADButtonWithFont`s in the
  sighted original.

  Not in this list, because it was a fault rather than a choice: the challenge-completed screen's three
  buttons - Retry, Challenge selection and Next challenge, read in that order (see Divergences) - do call
  `playButtonSound` 0x100049300 in the
  original (at 0x048884, 0x0489e0 and 0x048bc0), which plays `click_button` at gain 3, and the port had
  simply missed it.  They click now because the original does.
* PORT ADDITION: the Credits screen names the studio, and carries the port's own credits.
  `ADAboutCreditsViewController` 0x100020ea4 lays out two text views, and the nib's credits (object #25)
  list every person who made the game and `www.audiodefence.com`, but never Somethin' Else - the studio's
  name is nowhere on the screen.  Two lines go above that text saying whose game it is.  A third text view
  follows the nib's two, read last, with who made the Windows port and where the repository is; it is a
  view of its own so the cursor reaches it in one step instead of through the whole cast.  The nib's text
  is unchanged, and `ui/credits_text.py` still holds it exactly as extracted.
* REMOVED (user request): the magic tap, and F2, the key the port had bound it to.  VoiceOver's
  two-finger double tap is a gesture iOS gives no keyboard equivalent, and every screen that answered it
  did so with a button the screen already reads out - so the key was a second way to press something the
  cursor reaches anyway, and on the revive screen a second way to end the run by accident.  What each
  implementation did, for anyone comparing with the original: `-[ADViewController
  accessibilityPerformMagicTap]` 0x100072940 announced that a screen has none; the main menu 0x100065d40,
  the tarot screen 0x100036634 and the challenge overview 0x1000403e0 pressed Play (the overview's pressed
  it even while Play was disabled); the play menu 0x1000abc80 pressed Endless once tutorial_5 had been
  completed and Challenge before that; the Endless game over 0x10009bff8 pressed Play again; the
  challenge-completed screen 0x10006974c pressed Next mission; and the revive screen 0x100021cb4 pressed
  Game over.  F1, which read the focused element out again, went with it (user request): a screen
  reader's own review keys already do that, on any window.
* REMOVED (user request): the armory's Currency tab.  Its table asks `products` for its row count and
  nothing in the binary ever sets `products`, so the tab was blank on every device.  It was built to hold
  four "free coins" offers - Facebook, Twitter, the studio's other games, the App Store - each opening a web
  page, none of them wired up.  The port briefly kept it with a row explaining itself; it is now gone, so
  the armory has three tabs.  Two knock-ons: `showNotEnoughMoneyAlert` 0x1000768d4 no longer offers its
  "More coins" button, which called `currencyButtonPressed`, and `COINS_ALERT_CONTENT`'s last sentence -
  "You can also get coins in the Armory's currency tab" - is cut, since it would point at nothing.  The
  button itself stays in the nib layout, unreachable and with nothing routed to it.
* A power-up no longer survives the game it was picked up in.  `-[ADWeaponManager clean]` 0x1000aad50 cleans
  the power-up of the manager it is sent to, and killGameplay's block only sends it to the gameplay manager,
  whose own `powerUp` is always nil - `initPowerUp:` and `usePowerUp` go through `+sharedWeaponManager`,
  which nothing ever cleans.  The shared one is cleared with the rest of the game.
* A "survive" mission advances.  `-[ADMissionManager update:]` 0x1000085ac asks whether tutorial_5 is
  complete, throws the answer away, and never forwards the tick, so `-[ADMission update:]` 0x100044e30 never
  ran and `survivalTime` stayed at 0 however long you lived: the mission could be shown, attempted and
  saved, but never completed.  The tick is forwarded.
* A "kill N zombies" mission remembers its count.  `-[ADMission encodeWithCoder:]` 0x1000464c0 stores twelve
  fields and omits `progression_zombies`, which `isMissionCompleted` tests - so the count went back to zero
  on every restart and the mission could only be finished in one sitting.  It is saved with the rest.
* A finished game's rewards are paid once.  `-[ADGameOverWithStatsViewController viewDidLoad]` sends
  `ignoreRewards` at 0x100042030 and discards the answer, so the coins and diamonds were credited by every
  screen of that family - including the challenge overview, which sets `ignoreRewards` to YES precisely to
  avoid it, and which paid again each time it was opened.  The answer is tested.
* The completed screen reports a failed accuracy objective as failed.  The pass and fail paths converge at
  loc_100068794 and `accuracyObjectiveReached:1` is sent from there unconditionally.  The time-limit star
  three lines below already reports its failure properly; accuracy now does the same.
* A weapon at its maximum level says nothing instead of "Not enough Diamonds!".  With no next level there is
  no cost to compare, both branches read 0, and the alert was shown; `checkBuyOrUpgradeButton` 0x10006fa68
  hides the button by then, which is why it is hard to reach, but the alert was wrong wherever it appeared.
* The first control scheme screen offers Gyro.  The nib wires `gyroTextButton` to the Gyro button itself
  (`tiltTextButton` and `swipeTextButton` are not connected at all), so hiding the "text buttons" under a
  screen reader hid the recommended scheme - the one a fresh profile starts on - leaving Tilt and Swipe as
  the only choices on the one screen that exists to make that choice.
* A cow or a car is added to the passer-by list once.  `generateCow` 0x1000d5d04 appends it and then hands
  it to `ADBrickManager addPasserBy:`, which forwards straight back and appends it again; the duplicate was
  updated alongside the original, so they moved and aged at twice their speed.  Cars do the same at
  0x1000d5f08.
* A cow that cannot spawn waits its turn.  `generateCow` returns without touching `nextCow` when both cow
  playlists are busy, and `nextCow` is already below zero, so `update:` retried it every single tick.  The
  timer is re-rolled instead.
* The tornado cleans up once.  `update:` 0x100097af0 cleans it after its four gusts but never clears
  `active`, so every later tick fell through the guard and cleaned it again for the rest of the game.
* The enemy unlock gate reads the enemy's name, not the brick's slot label.  `canUseBrickWithName:`
  0x1000c259c looks each `Enemies` key up verbatim, but a brick wanting two of the same enemy labels the
  slots "Chainsaw - 2", "Runner - 3", "WeakZombieB " with a trailing space.  Those match nothing in
  `enemies.plist`, so the requirement came back 0 and the slot walked through the gate.  No gated enemy is
  written that way today, so nothing actually escaped - but one added in a repeat slot would have.
* An explosion pauses a jukebox.  `-[ADJukeBox hitByExplosionAtPosition:withDamages:dispersal:radius:]`
  0x100066784 pauses the music, but every sender - `solveExplosionWithDictionary:` 0x1000c5c40 and
  `hitByProjectile:` 0x100061098 - uses the five-argument `...powerupname:` form, so the override was never
  reached and ADEnemy's implementation ran instead: the jukebox took the damage and played on.
* The post-game statistics show the combo they measured.  `buildMiscPostGameData` 0x1000bacfc labels entry 4
  "Highest combo" and fills it from `numberOfEnemyKills` (the load at 0x1000bb1fc), so the screen reported
  the kill count twice and never showed `highestCombo`, which is maintained right beside it.


## Original quirks kept on purpose

* Melee cancels a reload.  `shootWithMelee` 0x1000aaa98 interrupts a reload in progress and *then* asks
  `isWeaponReadyToShoot` 0x1000aa350, which by then answers yes because interrupting put the weapon back
  in Idle: melee does not override the check, it clears the state the check reads.  Firing waits instead,
  `readyToShoot` 0x10001537c answering no in the reload states, so the two do not behave alike.  This was
  changed on 2026-09-21 so that melee waited as firing does, and reverted the same day at the user's
  request: swinging the machete mid-reload is something the game lets you do, and losing the reload is
  what it costs.  (`interruptReload` has a second caller, the weapon switch, which is meant to cancel.)

These are the original's, reproduced deliberately.  Each is either a design decision rather than a fault, a
change that would alter how the game plays or sounds rather than what it tells you, or something with no
observable effect at all.

* **Endless hides enemies that challenges show.**  `-[ADBrickManager canUseBrickWithName:]` 0x1000c259c
  refuses a wave while any enemy in it still has a kill requirement (`bestiary -> Unlock requirement` minus
  the save's total kills, 0x100084ea8).  Challenges do not check: `scenarioBrickNameForWaveNumber:`
  0x1000c28d8 indexes the challenge's own brick list, and several scripts hold gated enemies - maya_8 is all
  Berserk (250 kills), maya_10 Berserk and Riot Gear Zombie, maya_5 and maya_6 the Whisperer.  The gated
  five: Whisperer 150, Berserk 250, Riot Gear Zombie 350, Zombie Dog 400, Colossus 450.  This is the design -
  challenges are scripted set pieces - and changing it either breaks them or removes Endless's progression.
* **`brick_chance.plist` has a row 12 that nothing can read.**  `brickNameForWaveNumber:` clamps the wave
  with `arg1 > 11 ? 11 : arg1`, so from wave 11 the mix stops changing and `loadNextBrick` ramps
  `difficultyModifier` by 0.14 a wave instead.  Reaching row 12 would change the difficulty curve of every
  long Endless run.
* **The weapon timers advance by wall-clock time** (`CACurrentMediaTime`), not by the timer's interval.
  Changing it would alter every weapon's fire rate and reload.
* **Only an enemy's looping voice and footstep sounds reach the reverb**
  (`playAnySoundContaining:looping:spatialized:` with spatialized YES); its hit, pain, death, impact and
  explosion sounds are dry.  Changing it would rewrite how the game sounds.
* **The explosion falloff cancels its own radius**: `1 - (d2 / radius) * radius`, so damage falls off by
  squared distance whatever the blast radius.  Changing it would re-balance every explosive weapon.
* **A dead Berserk-style enemy cannot be hit by a blast until it wakes.**  `canBeShotAt` 0x100061f68 excludes
  state 0, and both the blast solver and the explosive weapon's targeting consult it, so an explosion next to
  a Berserk that has not been shot does nothing.  Confirmed in play with the grenade.
* The accessible Endless game-over screen is silent, because `-[Accessible_ADGameOverEndlessViewController
  viewDidLoad]` 0x100099f50 never calls `[super viewDidLoad]` and so never starts `game_over_theme`.  Kept at
  the user's request: it is the score you just lost, not a menu.
* `-[ADSound initWithDictionary:]` hardcodes a speed of 2.0 and ignores any `speed` key.  No scripted sound
  in any of the game's plists carries one, so nothing can reach it.
* The diamond dropper schedules `[nil deactivatePlaylist]` five seconds after dying (the `str xzr` at
  0x10007e950): the receiver is nil, so nothing is scheduled and nothing happens.
* `-[ADWeapon changeState:]` 0x100015148 returns `(old != 0) != newState`, comparing a bool with a state
  number.  Every caller discards the result.
* The challenge selector asks the app delegate for the sighted challenge overview with a nil challenge;
  `goToChallengeSelector` 0x1000816e0 always passes nil for `challengeToLoad`, so the port never reaches that
  call at all.
* The tarot schedules each card flip with `dispatch_after(<card number>)`, a time already past, so the block
  runs on the next pass and then flips after that many seconds - which is the timing either way.
* `checkEquipButtons` 0x10006ff8c leaves `equip1Button` with whatever hidden state it had when the weapon is
  a melee weapon; the nib's state is visible, which is what that branch wants.
* `-[ADPersistentStats allUnlockedEnemies]` 0x100085dd4 keys its dictionary by display name rather than by
  the enemy's internal name.
