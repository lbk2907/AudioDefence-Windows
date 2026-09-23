# Audio Defence — Windows and Mac port

A port of *Audio Defence: Zombie Arena* (Somethin' Else, iOS, 2015) to Windows
and the Mac:
the audio-only shooter you play by listening, turning towards a zombie you can
hear and firing before it reaches you. Endless mode, the challenge worlds, the
armory, the tarot cards, the Zombiepedia — and the whole of it through a screen
reader, because that is how the original was meant to be played.

The original was pulled from the App Store years ago and never came to anything
else. It needs a phone you may no longer own, running an OS that will not
install it. This port exists so it can be played on a desktop, with a keyboard
and NVDA or VoiceOver, by people who cannot see the screen and never needed to.

It is playable from the logo to the last challenge. If you find something that
sounds wrong, say so — most of what is fixed in here was found by someone
playing it and describing what they heard.

## Accessibility

The port is built for a screen reader, not adapted to one afterwards. It speaks
through **NVDA** when NVDA is running; through **JAWS**, **ZDSR**, **Narrator**,
**ZoomText**, **System Access**, **Window-Eyes**, **PC-Talker**, **Boy PC
Reader** or **Sense Reader** when one of those is, tried in that order (through
the Prism library); and through the **SAPI 5** voice when none is — nothing else is
required, and there is no visual mode worth using. A screen reader started or
closed while the game runs is followed within a few seconds. The game is the
same whichever speaks: with SAPI 5 you get every screen and the spoken game
exactly as an NVDA player does.

That choice is automatic. **Settings → Speech → Speech output** picks one
instead — NVDA, JAWS, ZDSR, Narrator, ZoomText, System Access, Window-Eyes,
PC-Talker, Boy PC Reader, Sense Reader or SAPI 5 — with Enter for the next and
Shift+Enter for the previous, and Automatic, the default, at the start of the
list. The one you pick is the only one used: while it is not running the game
is silent, even with another screen reader running. The row itself always tells
you what you picked, through the automatic choice when the one you picked
cannot speak ("JAWS is not running, so the game will be silent until it is"),
so you can step on to another without being left in silence.

While SAPI 5 is what speaks — chosen, or Automatic with no screen reader
running — five more rows follow it in the same tab, for SAPI 5 itself. They
come and go by themselves as a screen reader starts or closes:

| row | what it does |
|---|---|
| **SAPI 5 voice** | the voice set in Control Panel (the default), then every installed voice |
| **SAPI 5 rate** | -10 to 10, starting where Control Panel has it |
| **SAPI 5 rate boost** | faster again than the rate allows — only for a voice that can, which the game tries once per voice to find out |
| **SAPI 5 pitch** | -10 to 10, 0 being the voice's own |
| **SAPI 5 volume** | in steps of 10%, starting where Control Panel has it |

Enter and Shift+Enter change each one, and each change is said in SAPI 5 at the
new setting, even while NVDA speaks the rest, so you hear what you chose. Reset
all settings puts all five back to Control Panel's.

On the Mac the same page lists **Automatic**, **VoiceOver** and **System
voice**: VoiceOver when it is on, the system voice when it is not, and the
system voice's own five rows — voice, rate, pitch and volume, with no rate
boost — in place of SAPI 5's. See [On the Mac](#on-the-mac).

Every screen the original offered a VoiceOver user is here, read in the
order VoiceOver read it, with the same labels and hints, and a good number of
places where the original said the wrong thing or nothing at all have been
fixed. They are all listed under *How faithful this is*.

## How this was made

This is a vibe-coded project, and it says so plainly because the method is the
interesting part.

Nobody had the source. What existed was the shipped iOS app: an arm64 binary,
its NIBs, its property lists, and 915 `.m4a` files. Everything in
`audiodefence/` was written by reading that binary method by method and writing
the Python next to it — **Claude (Opus 5, at its highest reasoning effort)** did
the reading and the writing, prompted by a human who cannot see the screen and
who tested every line of it by ear.

The rule was: copy what the game *does*, not what it ought to do. Its bugs
included. Every ported method carries the address it was written against, so any
line can be checked against the disassembly, and every deliberate departure is
written down with the address of the method it came from. That rule is for the
game itself; what the port adds to it is listed on its own, under *How faithful
this is*.

The toolchain that made it possible lives in `tools/` and its output in
`analysis/` — a disassembler, an Objective-C class and selector dump, a digest
view that condenses a method to its sends and branches, a NIB layout reader, a
resource lister, and an extractor for the HRTF that was embedded in the binary.
The game's own binaural impulse responses are in `assets/hrtf/`, which is why it
sounds like the original rather than like a generic 3D mixer.

Two lessons paid for in bugs, recorded here because they are the whole method in
miniature:

- A summary is not the source. The digest tool used to drop ARC lines, which hid
  every early `return` compiled as a tail call — and a wave ambience spent weeks
  muted because of it. Read the listing when control flow matters.
- The tester is the instrument. Several faults were only ever visible by ear:
  music that vanished for a whole round, a sound that played a metre short, an
  ambience that outlived the game that started it. None of them would have been
  found by reading code.

## Whose work this is

`game/` holds the original's own data and audio — the narration, the zombies,
the weapons, the music, the playlists that arrange them. That is **Somethin'
Else's work, not ours**. It is in the repository so the port can run and be
built from a clone, and a build made by `compiler.py` carries it too.

Nothing of theirs is claimed here, this project is not affiliated with them, and
if they want it taken down it comes down.

## Getting it

There are two ways to play, and only one of them needs Python.

**The built game** is on this repository's Releases page: a folder with
`AudioDefence.exe` in it, and the game's own data beside it. Unzip it and run
the executable — nothing to install, no Python, 64-bit Windows and a pair of
headphones. `readme.html` and `changelog.txt` are in the same folder.

You only have to do that once. From then on the game tells you when a new
version is out and installs it for you, downloading only the files that
changed — see [Updates](#updates) below.

**On the Mac** it is the same folder with `AudioDefence.app` in it instead, in
`AudioDefenceMac-<version>.zip` on the same release — see
[On the Mac](#on-the-mac).

**From source** is everything below: the repository as it stands, run with the
Python you have. That is the one to take if you want to read the code, change
it, or build the executable yourself.

## Requirements

These are for running from source. A built game from Releases needs none of
them.

64-bit Python 3.12 or newer on Windows. The simplest way to get it is the
**Python install manager** from python.org, which is what that site now leads
with: install it, then

    py install 3.14

and `py` is the command for everything below. A traditional python.org
installer works just as well — it brings `py` with it — so if you already have
Python, you have what you need.

Then the packages to play:

    py -m pip install pygame-ce numpy av comtypes prismatoid

| package | what needs it |
|---|---|
| `pygame-ce` | the window, the keyboard and the frame loop (`audiodefence/__main__.py`, `ui/`) |
| `numpy` | the audio maths: decoding, mixing, the Freeverb reverb (`s3d/`) |
| `av` (PyAV) | decodes the game's `.m4a` sounds (`s3d/decoder.py`) — without it no sound plays |
| `comtypes` | the SAPI 5 voice, used when no screen reader is running (`platform/speech.py`); skip it if you always play with NVDA |
| `prismatoid` | Prism, for speech through the screen readers other than NVDA — JAWS, ZoomText, System Access and the rest (`platform/speech.py`); it brings `cffi` with it. Without it those players hear the SAPI 5 voice instead; skip it if you always play with NVDA |

Nothing else is imported outside the standard library. OpenAL Soft
(`vendor/openal/soft_oal.dll`) and the NVDA controller client
(`vendor/nvda/nvdaControllerClient64.dll`) ship with the repository, so there
is nothing to install for either, and no system OpenAL is used.

One more package is needed only to redo the reverse engineering, never to play:

    py -m pip install capstone

| package | what needs it |
|---|---|
| `capstone` | the arm64 disassembler (`tools/disasm.py`, and `tools/extract_hrtf.py`) |

`numpy` and `av` are used by the tools as well — `numpy` by `tools/build_hrtf.py`
and `tools/reverb_calibrate.py`, `av` for the sound durations in
`tools/resources.py` — but you already have both for playing.

And one more only if you want to build an executable rather than run from
source (*Building an executable*, below):

    py -m pip install pyinstaller

## Running from source

    py AudioDefence.py

That is the whole story: the logo, the opener, then the main menu. The launcher
can be double-clicked, and it takes the options below:

    py AudioDefence.py --endless
    py AudioDefence.py --challenge tutorial_1
    py AudioDefence.py --help

Settings, saves and the log live in `%APPDATA%\AudioDefence` (on the Mac,
`~/Library/Application Support/AudioDefence`), in three files:

| file | what is in it |
|---|---|
| `save.json` | progress: coins, diamonds, weapons, power-ups, missions, challenges, statistics |
| `settings.json` | control scheme, button mode, turn sensitivity, menu arrows, cursor memory, tutorial text, menu music volume, the update check and a version you skipped, how strong the vibration and the trigger feel are, and whether hints name keys or controller buttons, and which controller's, and the speech output and SAPI 5's voice, rate, rate boost, pitch and volume |
| `keys.json` | the key bindings, and each kind of controller's, by its name |

Deleting the folder starts a fresh profile — the first run then begins on Gyro
with the default key bindings.

## On the Mac

The Mac build is the same port — the same engine, the same game data, the same
OpenAL Soft and the game's own HRTF — with the Mac's own speech, folders and
app. Nothing in the game itself asks which it is on:
`audiodefence/platform/host.py` holds every choice that differs.

| | Windows | Mac |
|---|---|---|
| the game | `AudioDefence.exe`, with `game/` beside it | `AudioDefence.app`, with the game's data inside it |
| speech | NVDA, the other screen readers through Prism, SAPI 5 | VoiceOver, then the system voice |
| settings, saves, log | `%APPDATA%\AudioDefence` | `~/Library/Application Support/AudioDefence` |
| OpenAL Soft | `vendor/openal/soft_oal.dll` | `vendor/openal-mac/libopenal.dylib` |
| release zip | `AudioDefence-Win-<version>.zip` | `AudioDefenceMac-<version>.zip` |
| leaving the game | Alt+F4, or Quit | Cmd+Q, or Quit |

### Playing the built game

Unzip `AudioDefenceMac-<version>.zip` and move the `AudioDefence` folder
somewhere of your own — your Applications folder will do — then open
`AudioDefence.app` in it. The app is not signed with an Apple developer
certificate, so the first time macOS refuses to open it: open **System
Settings → Privacy & Security**, and choose **Open Anyway** for AudioDefence
near the bottom. You only do that once. It runs on Apple silicon Macs.

Move the folder before you first open the game. An app opened where it was
downloaded is run by macOS from a temporary copy, and from there it cannot
update itself; it tells you so if you ask it to.

### VoiceOver

With VoiceOver on, the game speaks through it, in your own voice and at your
own rate, and a braille display shows the same lines. It speaks to VoiceOver
by AppleScript, which VoiceOver allows only when asked to: in **VoiceOver
Utility → General**, tick **Allow VoiceOver to be controlled with
AppleScript**. The first time the game speaks, macOS asks whether
AudioDefence may control VoiceOver — say OK. Until both are done the game
still speaks, as announcements VoiceOver reads while the game's window has
focus, but they can be cut short by VoiceOver's own speech.

VoiceOver's Quick Nav takes the arrow keys for itself, and the game needs
them: if the arrows seem to do nothing, press Left and Right arrow together to
turn Quick Nav off.

With VoiceOver off, the game speaks with the system voice — the one set in
**System Settings → Accessibility → Spoken Content** — and Settings → Speech
lists its voice, rate, pitch and volume, as it lists SAPI 5's on Windows.

In the menus Command works as Control does with the arrows: Command with the
menu's arrows goes to the first or last element, and with the other pair to
the first or last tab.

### Running from source

The Mac uses [uv](https://docs.astral.sh/uv/) for Python and the packages,
which the repository's `pyproject.toml` and `uv.lock` pin:

    brew install uv
    uv run AudioDefence.py

`uv run` makes `.venv` with the right Python and packages the first time; the
options are the same as on Windows. `pygame-ce`, `numpy` and `av` are the same
three, `pyobjc-framework-cocoa` takes the place of `comtypes` and
`prismatoid` for speech, and PyInstaller comes with them for building.
`AudioDefence.command` can be double-clicked in Finder to do the same.

### Building the app

    uv run compiler.py

or double-click `compiler.command`. It is the same compiler with the same
menu and flags, less the one-file build, which on a Mac would unpack itself
on every launch. It leaves `dist/AudioDefence` holding `AudioDefence.app`,
readme.html, changelog.txt and license.txt, and zips it into
`dist/AudioDefenceMac-<version>.zip`, keeping the app's links and execute
bits so Finder unzips a working app. The game's data goes inside the app, at
`Contents/Resources/game`, less the original's iOS executable and its code
signature, and the app is signed again, ad hoc, once it is complete.

Put the Mac zip on the same release as the Windows one, in either order. Each
build's updater takes the zip made for it, by its name. Keep the names exactly
as the compiler makes them. GitHub lists a release's files alphabetically,
not in the order they were uploaded, and a Windows build from before the Mac
port takes the first zip it finds. `AudioDefence-Win-` sorts before
`AudioDefenceMac-` because a dash comes before any letter. A Mac zip called
`AudioDefence-Mac-` would come first, and those older Windows builds would
install it over themselves.

`vendor/openal-mac/libopenal.dylib` is OpenAL Soft 1.25.2 built for arm64,
the same version as the Windows DLL. `tools/build_openal_mac.sh` rebuilds it
from source (it needs cmake and the Xcode command line tools), for an Intel
Mac with `--arch x86_64`.

## Controls

In the menus, the port stands in for VoiceOver: it reads the elements of a
screen the way VoiceOver reads them, with their labels, hints and "button".

| key | what it does in the menus |
|---|---|
| Right / Tab | next element |
| Left / Shift+Tab | previous element |
| Ctrl+Right / Ctrl+Left, Ctrl+Tab / Ctrl+Shift+Tab, End / Home | last / first element |
| Down / Up | next / previous tab or category |
| Ctrl+Down / Ctrl+Up | last / first tab or category |
| Enter | activate |
| Shift+Enter | a row's second action, where it has one |
| Escape / Backspace | back |
| Page Up / Page Down | menu music louder / quieter |

Hold a key that moves one element — the arrows, Tab or Shift+Tab — and it
repeats, so a long list can be walked through without tapping. It starts
repeating after about a third of a second. Nothing else repeats: a jump to an
end has nowhere to go, Enter must act once, and a key held in a game belongs to
the game.

In a game, these are the defaults; all of them can be rebound in
**Settings → Keyboard**, and "Restore default keys" puts them back.

| key | what it does in a game |
|---|---|
| Space | fire: tap for a single shot, hold for continuous fire |
| Left Ctrl or Right Ctrl | melee |
| W, or Up arrow under Gesture | next weapon |
| R, or Down arrow under Gesture | reload |
| Left / Right arrow | turn |
| Escape | pause: Resume, Restart challenge (in a challenge), End Game |
| Enter | skip the narration |
| T | read the challenge timer |

Those two follow the control scheme, because the scheme changes what the action
is. Under **Gesture** you are swiping: up switches weapon, down reloads, and
the arrows stand for the swipes. Under **Button** you are pressing the four
corner buttons, where nothing is directional, so they are letters — W and R.
Rebinding either one changes it for the scheme you are in and leaves the other
alone; the rest of the keys are one binding for both.

An action can hold more than one key. On a binding row, **Enter** adds a key,
**Shift+Enter** replaces every key that action has, and **Delete** removes the
one you added last — an action is never left with no key at all. Key names are
spoken the way people say them, so the two Enter keys are "Enter" and "Numpad
Enter".

The arrows that move through a screen are a setting: Left and Right by
default, or Up and Down if you prefer them, in **Settings → Miscellaneous → Menu
arrows**. Whichever pair you choose, Ctrl with it jumps to the first or last
element, and Tab, Shift+Tab, Home and End work either way.

The other pair changes tab. In the armory, Down and Up step through Weapons,
Loadout and Powerup without walking to the bottom of the list first,
and each one is named before it reads what you land on; Settings opens straight
inside **Aiming**, and the same two keys move it to Controls, Sound, Keyboard
and Miscellaneous — there is no list of categories to go through first. Choose Up and Down
for moving through a screen and the two swap over, so the tabs land on Left and
Right. Ctrl with the tab pair jumps to the first or last tab, exactly as Ctrl
with the other pair jumps to the first or last element; Tab stays with the
elements, so Ctrl+Tab and Ctrl+Shift+Tab jump to the last and first element
from wherever you are. The ends hold rather than wrap, as everywhere else.

Settings speaks every change and clicks like the original's buttons. Escape
leaves it; the turn sensitivity and the key bindings live in Aiming and
Keyboard. **Settings → Miscellaneous → Reset all settings** puts every setting
back to how a new profile starts, except your key bindings, which Keyboard has
its own Restore default keys for. Quit is on the main menu.

### With a game controller

A controller works in the menus and in play: a DualSense, a DualShock 4, an
Xbox or Switch Pro controller, or most others Windows recognises. Plug it in
before or after starting the game; it says so when one connects or goes. The
buttons are named as your controller names them — Cross and R2 on a
PlayStation pad, A and RT on an Xbox one.

In the menus it stands in for the keys:

| controller | what it does in the menus |
|---|---|
| D-pad or either stick | the arrows: move through the screen, and change tab on the other pair |
| Cross (A) | Enter: activate |
| Square (X) | Shift+Enter: a row's second action |
| Circle (B) | Escape: back |
| L1 / R1 | previous / next row, without reaching for the D-pad |
| Cross (A) held, with a direction or L1 / R1 | the first or last row, or the first or last tab |
| L2 / R2 | menu music quieter / louder |
| Triangle (Y) | Delete, on a key binding row |

In a game:

| controller | what it does in a game |
|---|---|
| either stick, sideways | turn — a small push turns slowly, all the way as fast as the arrow keys |
| D-pad left / right | turn, at the same speed as the arrow keys (Alternate turn left / right — the only turning you can rebind) |
| R2 | fire |
| R1 | melee |
| L1, or a stick flicked up under Gesture | next weapon |
| L2, or a stick flicked down under Gesture | reload |
| Options | pause, and Options again to resume |
| Cross (A) | skip the narration |
| Square | read the challenge timer |

Under **Gesture** a stick flicked up or down is the swipe, as the Up and Down
arrows are on the keyboard; a stick pushed more sideways than up or down only
turns, so turning does not switch weapons by accident. Shaking the controller
is shaking the phone: under Gesture it swings your melee weapon, as it did in
the original, and under Button it does nothing, as it did not. It needs a pad
that can feel movement — a DualSense, a DualShock 4 or a Switch Pro.

A controller that can vibrate lets you feel the game:

- the **heartbeat** when a zombie is close, on every beat and harder the closer
  it is;
- a **hit**, as hard as it hurt: a big gun's hit is felt more than a small
  one's, a melee blow is a heavier thud, and several hits at once are firmer
  still. A shot the Shield zombie's shield takes is a light knock, and a miss
  is felt as nothing;
- a **kill**, whatever did it;
- an **explosion** — a Farty going off, a rocket, a power-up's blast — harder
  the closer it is, and the zombies it hurts;
- the tornado's **gust** pushing the zombies back;
- and **your own death**, a long heavy rumble when a zombie gets you.

A **DualSense on USB** goes further: its grips play the game's own heartbeat —
the very recording you hear, felt in your hands — and its own knocks, thuds
and rumbles for the rest, through the fine haptics PlayStation games use rather
than plain rumble. Over Bluetooth Windows does not offer that, and it rumbles
like any other pad. On a **DualSense** the triggers change too while you play:
R2 is shaped like a pistol's trigger: a long take-up with nothing in it, then
the wall, where it holds; pressing through the wall breaks it and the shot goes
at the break, not when you first meet it. Letting it back out to just under the
wall is the reset, and it fires again from there, so you can shoot without
letting go all the way. Under Button, L2 pulls against a light spring where it
reloads. In the menus and on the pause
screen they are plain again, and they are set back when the game closes.

**Settings → Miscellaneous → Fine haptics** (on by default) chooses how a
controller that has both plays what you feel: through the fine haptics in its
grips, or through its motors like any other pad. Turn it off to feel a
DualSense as an ordinary controller. With no such controller connected, the
motors are used whatever it says.

**Settings → Miscellaneous** sets how strong **Joystick vibration** and the
**Trigger feel** are: Off, Light, Medium (the default) or Strong, with Enter
for the next and Shift+Enter for the previous. Each step of Joystick vibration
gives a pulse at the new strength so you can feel it, and each step of the
Trigger feel puts that feel on the triggers for eight seconds so you can
squeeze R2 and try it there and then. The Trigger feel is only for a
DualSense — no other controller has one.

**Settings → Joystick** names the controller that is connected, and lets you
change which button does what, the way Keyboard does for keys:
Enter (Cross) on an action
adds a button, Shift+Enter (Square) replaces them all, Delete (Triangle)
removes the last one, and Escape on the keyboard cancels. Next weapon and
Reload are set for the control scheme you are in, as on the keyboard. A stick
pushed sideways cannot be bound — it turns — and neither can the PS or Xbox
button, which Windows or Steam often keeps. Each kind of controller keeps its
own buttons, by the name it gives itself — a DualSense's, a DualShock 4's, an
Xbox pad's — made from the defaults the first time it is connected, so setting
up one never changes another. With two or more kinds connected, the
**Controller** row says which one's buttons are listed ("DualSense Wireless
Controller, 1 of 2"), and Enter or Shift+Enter goes to the next or previous.
**Restore default buttons** puts that controller's buttons back, and Reset all
settings leaves them alone. With no controller connected the buttons are not
listed. If Steam is running it
may take the controller over and present it as an Xbox pad; the game still
works, but for your own controller's button names, turn Steam Input off for
the game.

**Settings → Miscellaneous → Names in hints and tutorial** chooses whether the
hints and the tutorial text name the keyboard's keys (the default) or the
connected controller's buttons, as that controller calls them: "Press Cross to
copy the results", "use the R2 button to fire your weapon" on a PlayStation
pad, "Press A" and "RT" on an Xbox one. Enter or Shift+Enter switches it. So do
the other lines that name a key: the tab and category keys ("L1 and R1 change
tab, D-pad left and right move through it"), the Button and Gesture rows, and
"Press Cross to skip intro". With two or more kinds of controller connected,
**Controller for names** under it chooses which one. With no controller
connected the row is dimmed and it is Keyboard keys: starting the game without
one, or unplugging the last one wherever you are, sets it back to Keyboard keys
and saves that, so choose Controller buttons again when you next play with one.

## Sharing a result

Every screen at the end of a run has a **Copy results** button, read straight
after the results and before the screen's other buttons: after an endless game,
after a challenge you completed, and after one you failed. It puts a short list
on the clipboard as
plain text, ready to paste into a message, and says "Results copied to
clipboard." After an Endless game it looks like this:

    Audio Defence Endless Statistics

    Tarot cards: Electric Shield and Zombies With Helmets!
    Coins Earned: 7802
    Diamonds Earned: 14
    Score: 11882144
    Kills: 162
    Accuracy: 76.53 %
    Survival time: 17:04
    Maximum combo: 483

After a challenge the heading is *Audio Defence Challenge Statistics*, then the
challenge's name and whether you completed or failed it, then the stars,
rewards and statistics that screen shows. There are no tarot cards in a
challenge.

The lines are taken from the screen itself rather than worked out again: each
results screen reads exactly these lines, one row each, and only the heading is
not on it, since the screen has its own title. The game's version is never in
it. The original had one way to share a score, a Twitter sheet, which needed an
account and an iPhone; this needs neither.

The failed screen used to tell you nothing at all — the original shows a tip,
and two buttons. It now reads your results first, the same kills, accuracy and
time the completed screen shows, so a run you lost can be compared with one you
won, and so the copy is not handing you figures you were never told. The tip
follows them.

## Updates

The game keeps itself up to date. When the main menu opens it asks GitHub
whether there is a newer build, and says nothing at all unless there is one —
if there is, it tells you the version and gives you three answers. **Yes**
downloads it. **No** means not now: the next time the game starts, it asks
again. **Skip this version** means not this one: that build is not offered
again when the game starts, though a later one still will be.

Because that check is silent when there is nothing to report, the main menu
also has a **Check for updates** button, between Settings and Quit. It answers
either way: it either offers the new version or tells you the one you are on.
It offers a version you skipped as well, since you asked — which is how to
change your mind.

Say yes and it downloads, then offers to restart. It has to close to put the
new files in place and starts itself again afterwards. **Your progress is never
at risk**: saves, settings and key bindings live in `%APPDATA%\AudioDefence`
(`~/Library/Application Support/AudioDefence` on the Mac), and an update only
ever replaces the game's own program files.

**An update downloads only what changed.** The release is around 155 MB, and
nearly all of it is the game's audio, which is the same in every build. The
updater reads the archive's index over the network and compares it with what
you already have, file by file, so a build that only fixes code is a download
of a few megabytes rather than the whole game again.

If you would rather it did not look, **Settings → Miscellaneous → Check for
updates when the game starts** switches it off. The main menu's Check for
updates button asks whenever you like, and its hint is the version you are on.
Run from source, that button is a line saying updating is not available — a
checkout is updated with git, not from a release. Answering "Not yet" to a
restart keeps the download:
the next time you start the game it offers to finish the job rather than
fetching anything a second time.

Turning is the one place a phone cannot be copied. The original turns with the
gyroscope, a finger drag or a tilt; here all three are the turn keys held down,
and the only difference left is how fast they turn:

| Settings → Aiming | turn speed at the default sensitivity |
|---|---|
| Gyro | the slowest, about 110 degrees a second |
| Swipe | in between, about 160 |
| Tilt | the fastest, about 190 |

**Turn sensitivity** — 0.5 to 3, Enter for the next value, Shift+Enter for the
previous — scales all three in proportion, so it is the dial to reach for
first; the three rows only choose where it starts from. All three are kept
because the tutorial has a separate announcer clip for each.

## How faithful this is

Faithful here means the game itself. What you play is the original's, and it
stays that way: the waves, the zombies, the weapons and what they cost, the
challenges, the sounds, and the quirks that shape how it plays. The port also
adds things, and will go on adding them — some around the game, like the updater
or Copy results, and in time some inside it, like new tarot cards or another
arena. Whatever is added follows the original's concept and sits beside what the
original has, rather than changing it. You can hear the line in Settings: the
original's own rows work as they always did, and only the rows the port added
step through their values with Enter and Shift+Enter. The additions are listed
together under *New in the port*, apart from the changes to what the original
already had.

The port is written method by method against the original's arm64 disassembly, and the rule it follows is to
copy what the game does rather than what it ought to do — its bugs included. Every place it departs from
that is listed below, and `docs/PORTING_NOTES.md` carries the same list with the address of the method each
one came from, so any of them can be checked against the binary or put back.

There are **112 divergences** and **15 original quirks kept on purpose**.

### 1. Windows standing in for a phone

The original is played by touch and device motion. None of that exists here, so the input layer is the
port's own work and has no counterpart in the binary.

- Every gameplay action is a key, and every key is rebindable in **Settings → Keyboard**. An action can hold
  several keys: Enter adds one, Shift+Enter replaces them all, Delete removes the one added last, and an
  action is never left with none.
- Turning replaces the gyroscope, the finger drag and the handset tilt. All three schemes remain, because
  the tutorial has a separate announcer clip for each, but on a keyboard they differ only in speed — about
  110, 160 and 190 degrees a second at the default sensitivity, all scaling in proportion to it.
- The menus are driven by a VoiceOver stand-in: elements are read in the nibs' frame order with their
  labels, hints and traits. Which arrow pair moves the cursor is a setting; the other pair changes tab.
  Holding a movement key repeats it.
- Settings gained categories, a turn sensitivity (a sighted-only slider in the original) and the key
  bindings. The main menu gained a Quit button, which no iOS app needs.
- Key names are spoken the way people say them, so the two Enter keys read as "Enter" and "Numpad Enter".
- Saves are split into `save.json`, `settings.json` and `keys.json` instead of one plist.

### 2. Where the original's screen-reader path was wrong

These are the largest group. The original ships a VoiceOver path that in places says the wrong thing, says
nothing, or says something no keyboard player can act on.

- **Escape on the completed screen goes back to the challenge list** (the original goes to the main menu,
  which on a phone is a scrub out of the whole flow). The list is where the next challenge is, and the main
  menu is one Escape further. The screen's Select challenge button is unchanged, and the screen you get
  after failing a challenge still goes to the main menu.
- **A row that does something makes a sound.** The original's buttons click but its table rows do not,
  which sighted is invisible and on a keyboard is not: opening a challenge, opening a zombie's page, or
  pressing Preview sound answered with silence, and silence is what a key that missed sounds like. Those
  three now click. A challenge row you cannot open yet stays silent, because nothing happens.
- **Screens name themselves.** Every screen sets a page title that the iPhone layout has nowhere to show, so
  on iOS it is never seen or heard. Four are named for the button that opens them rather than the original's
  own word, so the two agree — the main menu, the stats portal reached by Info, the two Info pages, and the
  tarot screen, which is called Endless because that is how Endless starts. The challenge screens all set
  "CHALLENGE", which made four different screens announce the same word; each is now named for the row that
  opened it.
- **The results screens read one line per result** — "Coins Earned: 7802", "Score: 11882144" — the same
  lines Copy results pastes, with Copy results straight after them, before the other buttons. After an
  Endless game the first line is the tarot cards you played with, which the original never tells you;
  after a challenge it is the challenge's name, then whether you completed or failed it. The original reads
  "Rewards", "Statistics" and "Stars" headings, and its rewards as sentences: "Coins, You earned 7802 coins
  for killing zombies". The Endless screen's Play again button is called **Close**: it still takes you
  back to the Endless screen, where you can play again.
- **The cursor opens on a screen's own first item**, not on the Back button and the coin and diamond
  readouts that precede it. They are still one step back.
- **The tarot deal is silent on iOS** — the flip sound plays at the end of an animation that is skipped for
  VoiceOver. Here you hear the cards.
- **A card you pay to change is never saved on iOS**: leave the screen and the old card is back, diamonds
  gone. Here it is saved.
- **The coins and diamonds counters only update their spoken label on certain screens**, so a purchase could
  leave you hearing the old balance. Here the spoken number follows the one on screen.
- **The statistics screen speaks a weapon's exact accuracy.** iOS cuts it at the decimal point and reads a
  weapon you have never fired as "accuracy, nan percent".
- **The loadout tab names the currency** a locked weapon is sold in, instead of announcing a diamonds-only
  weapon as "costs : 0 coins".
- **The armory's Back button takes one step**, closing the weapon page and leaving you on the row you opened,
  instead of closing the page and the armory together.
- Zombiepedia's preview button, its Next and Previous buttons, and the armory's upgrade button were
  unlabelled, double-labelled or silent about their price. Four strings written in capitals are spoken in
  sentence case; the screen keeps the capitals.

### 3. Original bugs fixed

Faults in the game's own logic, not in how it describes itself. Each was read against the disassembly first.

- **A finished game's rewards are paid once.** `ignoreRewards` is asked and the answer thrown away, so the
  challenge overview — which sets it precisely to avoid paying — credited the last game's coins and diamonds
  again, every time it was opened.
- **A power-up no longer survives the game it was picked up in.** The clean-up is sent to the gameplay
  weapon manager, whose power-up is always nil; the shared manager that actually owns it was never cleaned.
- **A "survive" mission advances.** The mission manager's tick asks one unrelated question and never
  forwards itself, so survival time stayed at zero however long you lived.
- **A "kill N zombies" mission remembers its count** across restarts; the field was missing from the save.
- **A dead player can no longer fire, reload, melee or switch weapons.** On iOS the death overlay swallows
  the touches; keys do not route through the view hierarchy here, so it had to be honoured explicitly.
- **The first control-scheme screen offers Gyro.** The nib wires its label outlet to the Gyro button itself,
  so under a screen reader the recommended scheme — the one a fresh profile starts on — was hidden.
- **Cows and cars move at their own speed.** Each was added to the passer-by list twice and updated twice.
- **The tornado cleans up once** instead of on every tick for the rest of the game.
- **An explosion pauses a jukebox.** The handler that does it overrides a selector nobody sends.
- **The post-game statistics show the combo they measured**, not the kill count a second time.
- **The completed screen reports a failed accuracy objective as failed.**
- **A weapon at its maximum level says nothing** instead of "Not enough Diamonds!".
- **The armory's Currency tab says it is empty**, rather than being a tab you land in with nothing in it.
- **The enemy unlock gate reads the enemy's name**, not the brick's slot label, so an enemy in a repeat slot
  could not walk through it.

### 4. Sound and music

- **Menu music plays on every menu.** The original starts it on three screens only, so any menu you reach
  out of a game is silent. The pause, revive, challenge-failed and statistics screens keep their own sound.
- **Returning to the menus does not replay the opening sting.** Coming back from a finished challenge used
  to restart the 13-second intro before the theme returned.
- **The menu theme and the game-over theme are the same file.** Both are 2,121,278 bytes with the same
  checksum: one 129-second piece of music shipped under two names. The original treats them as two tracks,
  so "changing" from one to the other faded the music out and started the very same music again from the
  beginning — which you heard on arriving at a completed challenge, and again on leaving it for the
  challenge list. Asking for either name while either one is playing now leaves it alone, so the music
  runs unbroken from a challenge's closing line through the menus.
- **Menu music asked for while the previous track is still fading is no longer lost**, and a second fault in
  the same area could wedge the audio playlist so nothing ever started it again for the rest of the session.
- **A wave that is only a cutscene plays it.** Its sounds are built asynchronously, so for an instant the
  wave looks empty — and a wave with no enemies looked finished the moment it loaded, ending the challenge
  before its closing line existed.
- **Dying in a challenge starts no music.** This is the one item on this list taken from a recording rather
  than the disassembly: the binary has a line that would start the game-over theme, the real game plays none,
  and the mechanism that suppresses it could not be found.
- **A wave's ambience plays.** `Horde_ambiant` is written into 17 waves and the port had been muting it
  through a misread of the disassembly; a zombie with its own ambience still takes over while it lives.
- **The Chainsaw ambience stops when a game ends**, instead of playing on until the app closes.
- **Two zombies of the same kind no longer silence each other.** They shared their sounds, one per file, so
  when both picked the same one, the first to be shot or to change step stopped it under the other, which
  walked on without a sound. The same sharing made a second death silent after a revive, when it was a
  zombie of the same kind again — always, for the Shield zombie. Each zombie now has sounds of its own.
- **A critical kill is never silent.** The Shield, WeakZombieD, ZombieC and the passers-by have no death
  sound of their own for a critical hit, and the original played nothing instead — after stopping the hit
  sound that was playing. Melee weapons are often critical, so a Shield killed with one tended to fall
  silent. They now die with their ordinary death sound.
- **Two zombies dying together are both heard to the end.** The first to fall silent could unload the
  other's sounds and cut its death off half way; a zombie's sounds now wait until it is quiet.
- 3D positioning is correct from the first frame; the original relies on the gyroscope firing to correct it.

### 5. Engine and presentation

- The original's reverb (two Freeverbs, six combs and three allpasses each) runs in the port itself, on a
  second OpenAL Soft device mixed into the output — about half a millisecond behind the dry path.
- Screens are not animated: a view controller appears at once, and animation completions run after the
  animation's duration.
- The reading order is approximated from the nib frames, and no screen wraps at its ends.
- Game Center, the Twitter and Facebook sharing buttons, and the "more games" screen are removed.
- The per-sound hard clip of the binaural panner is not reproduced.

### 6. New in the port

Things the original never had. Each one sits beside the original's own screens and rows rather than
replacing them.

- **Check for updates**, on the main menu, and a quiet check each time the game starts, which you can
  switch off in **Settings → Miscellaneous**. An update downloads only the files that changed. See
  [Updates](#updates).
- **Copy results**, on the screen at the end of a run, puts the results on the clipboard. See
  [Sharing a result](#sharing-a-result).
- **Restart challenge**, on the pause menu during a challenge, so a challenge you have already lost does not
  have to be played to the end.
- **The tutorial announcer's lines are also spoken as text**, naming the keys you have actually bound — or,
  if you choose, a connected controller's buttons ("use the R2 button to fire"), and under Gesture the melee
  line offers the shake too, on a controller that can be shaken. The
  announcer tells you to tilt the device, swipe, or tap a corner button, none of which a keyboard can do.
  **Settings → Miscellaneous → Tutorial text** chooses when, or turns it off: Enter steps to the next
  setting, Shift+Enter to the previous.
- **Settings → Speech**: Speech output — Automatic, or one screen reader or voice only — and SAPI 5's
  voice, rate, rate boost, pitch and volume. See [Accessibility](#accessibility).
- **Settings → Miscellaneous → Remember cursor position** (off by default) returns the cursor to the row
  you left a screen on.
- **A menu music volume**: Page Up and Page Down, on any menu, in steps of 10% from 100% — the original's
  own level, never louder — down to silent. It is kept with your settings. Only the menu music: in a game,
  and on the pause screen, the keys do nothing and the game's music and ambience are untouched.
- **Settings → Miscellaneous → Reset all settings** puts every setting back to its default, except your key
  bindings.
- **Game controllers**: a DualSense, DualShock, Xbox, Switch Pro or most other pads, in the menus and in
  play, with a stick that turns as fast as it is pushed, vibration for the heartbeat, hits, kills,
  explosions and your death, the phone's shake, and a DualSense's triggers that feel like a gun, each at
  the strength you choose. Each kind of controller keeps its own buttons, and the hints and the tutorial
  can name its buttons instead of the keys. See
  [With a game controller](#with-a-game-controller).

### Original quirks kept on purpose

Fourteen remain. Each is a design decision rather than a fault, a change that would alter how the game plays
or sounds rather than what it tells you, or something with no observable effect at all.

The ones you can notice:

- **Endless makes you earn an enemy; challenges hand it to you.** Five enemies carry a kill requirement —
  the Whisperer 150, the Berserk 250, the Riot Gear Zombie 350, the Zombie Dog 400, the Colossus 450 —
  counted against your total kills, of anything, across the whole save. Endless checks it and throws away
  any wave containing an enemy you have not earned yet, so you meet them roughly in the order intended.
  Challenge scripts never check, which is how a challenge called "Meet the Berserk!" can introduce one to a
  new player. Once your total passes the number, Endless spawns them too — the gate is temporary, and it is
  not a difference in what the two modes can contain.
- **An explosion cannot hurt a Berserk that has not been woken.** The blast solver and the explosive
  weapon's targeting both consult the same "can be shot at" test, which excludes an enemy in its sleeping
  state.
- **The difficulty mix stops changing at wave 11**, after which difficulty ramps by a fixed step instead.
  The wave table has a twelfth row nothing can reach.
- **Weapon timers advance by wall-clock time**, not by their timer's interval. Changing it would alter every
  fire rate and reload.
- **Only looping voice and footstep sounds reach the reverb**; hits, pain, death, impacts and explosions are
  dry. Changing it would rewrite how the game sounds.
- **Explosion damage falls off by squared distance whatever the blast radius** — the radius cancels itself
  out of the formula. Changing it would re-balance every explosive weapon.
- **The statistics screen after a death is silent**, because a skipped `viewDidLoad` never starts its theme.
  Kept deliberately: it is the score you just lost, not a menu.

The other seven have no observable effect: a message to a nil receiver, a return value every caller
discards, a hardcoded sound speed no data can reach, a navigation call the port never makes, a dispatch
whose timing works out the same either way, a button left in the state its branch wanted, and a dictionary
keyed by display name.

## What has been taken out

A few things the original shipped are gone rather than ported. Each is either something that cannot work
outside an iPhone in 2015, or a dead end that would only cost you a keypress to discover.

**Three keys: the magic tap on F2, the repeat key on F1, and Space.** VoiceOver has a two-finger double
tap that a screen can answer with its most obvious action, and the port had put it on F2. Every screen that
answered it did so by pressing a button the cursor already reaches — Play, Play again, Next mission — so it
was a second way to do something the menu does anyway, and on the revive screen after a death it was a
second way to end the run without meaning to. `docs/PORTING_NOTES.md` records what each screen's did. F1
read the focused element out again, which your screen reader's own review keys already do. Space activated
whatever the cursor was on, beside Enter; it is now the fire key in a game and nothing else. Enter, and the
number pad's Enter, activate.

**The armory's Currency tab.** It was built to hold four "free coins" offers — follow the game on Facebook,
follow it on Twitter, look at the studio's other games, rate it on the App Store — each of which opened a
web page. None of them was ever wired up: the tab's table asks a `products` array for its row count and
nothing in the binary ever fills that array in, so the tab was blank on every device that ever ran the game.
For a while this port kept it and had it explain itself, with a line that read:

> This tab is empty. It offered free coins for following the game on social media. Those links are long
> dead, and the original never filled this tab in either.

which is a fair description of a tab you should not have to visit. It is now removed, leaving Weapons,
Loadout and Powerup. Two knock-on changes came with it: the "Not enough Coins!" alert no longer offers its
"More coins" button, which opened that tab, and the last sentence of that alert — "You can also get coins in
the Armory's currency tab" — is not shown, since it would be pointing at nothing. The two ways of earning
coins that do work are still named.

**Sharing and Game Center.** The Twitter and Facebook buttons on the game-over screen, and the score
reporting to Game Center, are removed. There is no Game Center on Windows, and the sharing buttons opened
apps that are not here.

**The "more games" screen.** A catalogue of the studio's other iOS titles, reachable from the stats portal.
It advertised apps you cannot install from a machine that cannot run them.

**Unreachable screens are simply not ported**, which is a different thing from removal — the game still
contains them, nothing can open them, and the port does not implement them: the scenario roulette and the
story screen (nothing calls them, no NIB action reaches them), the cheat screen (its button is hidden), the
enemy-unlock popup and the score-feedback view (never allocated). `docs/PORTING_NOTES.md` lists them with
the reasoning.

**Touch handlers are ported but never called**, which is also not removal. A few of the original's methods
are here in full with nothing to reach them, because a keyboard sends no fingers: `touchesMoved:`
0x10008a5a4, the weapon buttons' touch-down and touch-up 0x1000a9d78 and 0x1000a9d7c, the shake
`motionEnded:` 0x10005a108. `hitByProjectile:` 0x100061098 is here for a different reason: nothing in the
original calls it either, because a rocket's damage is dealt by `solveExplosionOfProjectile` 0x1000c6360
instead. They stay as the record of what the original did, next to the keyboard code that stands in for
them. That is the line the magic tap fell the wrong side of: it was not a handler waiting for input the
port never sends, it was a gesture the port had invented a key for, so when the key went there was nothing
left to keep — and `post_announcement`, which existed only to say "no magic tap available on this screen",
went with it.

## What is in the repository

    AudioDefence.py     the launcher
    AudioDefence.command  the launcher, double-clicked on the Mac (uv run)
    .gitattributes      LF for text, hands off the binaries
    audiodefence/       the port
        s3d/            the S3D audio engine on OpenAL Soft: HRTF, playlists,
                        streaming decoder, the original Freeverb reverb bus
        platform/       run loop, timers, notifications, user defaults, C rand,
                        speech, the key map, the updater and its remote-zip reader;
                        host.py, every choice between Windows and the Mac, and
                        macspeech.py, VoiceOver and the Mac's system voice
        game/           gameplay: enemies, bricks, weapons, power-ups, missions,
                        challenges, inventory, stats, the gameplay controllers
        ui/             the screens, built from the NIBs, and the VoiceOver
                        stand-in that reads them
        app.py          the app delegate: launch, menu music, navigation
    compiler.py          builds the executable, and the release zip (see below)
    compiler.command    the same, double-clicked on the Mac
    pyproject.toml      the packages, for uv; uv.lock pins them
    VERSION             the release tag, e.g. 26.09.20-2, built into the executable
    game/               the original game's own files (see below)
    assets/hrtf/        the HRTF recovered from the binary
    analysis/           the reverse engineering: disassembly, digests, dumps
    docs/               PORTING_NOTES.md, GAME_STRUCTURE.md
    tools/              reverse-engineering and asset tools
    vendor/             OpenAL Soft (the Windows DLL, and the Mac dylib in
                        openal-mac/), the NVDA controller client

### `game/` — the original

The contents of the IPA's app bundle, unwrapped. The port reads them in place:
the plists, the `en.lproj` strings, the S3D playlist models under `game/meta/`
and the 918 sound files under `game/sounds/`, in the layout the bundle already
has. Nothing is copied and nothing is converted, so a clone has everything the
game needs.

The port reads it from `game/`, unless `--game PATH` (or the
`AUDIODEFENCE_GAME` environment variable) points somewhere else. The first line
in the log says which one it took.

Not all of it is used: the port never draws, so the `.png` artwork, the `.ttf`
fonts and `html/` are along for the ride, and `_CodeSignature/` is Apple's
tamper manifest. They are kept so `game/` stays the complete original. Do not
be misled by the underscore in `game/sounds/_weapons/` or in the `_fight` /
`_zombie` sub-playlists — those are game data, not metadata.

### `analysis/` — the reverse engineering

46 MB of generated material, and the reason the port can claim to be faithful:

| file | what is in it |
|---|---|
| `disasm/<unit>.s` | full annotated listings of all 7,692 functions, one file per class |
| `digest/<unit>.txt` | the condensed pseudo-code view of the same functions |
| `bin/` | the `arm64` and `armv7` slices pulled out of the fat binary |
| `objc.json`, `classdump.h`, `cxx_classes.txt` | 400 Objective-C classes, 43 C++ classes with vtables |
| `xrefs.json`, `functions.tsv` | per function: calls, callers, selectors, strings, ivars, float constants |
| `data/nibs/*.txt` | 150 NIB dumps: view trees, frames, texts, VoiceOver labels, outlets, actions |
| `data/plists/*.json`, `playlists.json`, `sounds.tsv` | the game's data as JSON, the 208 playlists, the sound inventory |
| `data/embedded_hrtf.dat` | the HRTF table extracted from the binary |

The game never reads any of it. It is all rebuildable from `game/`, and it is
what every address comment in the port points into.

## Command line options

None of them is needed to play; they exist so a session can be started at a
particular point, and so automated runs can finish on their own.

| option | what it does |
|---|---|
| `--endless` | start an endless game directly. This skips the play menu (so it works before Endless is unlocked by finishing `tutorial_5`) and skips the tarot cards, so no card modifiers are in play. |
| `--challenge NAME` | start one challenge by its plist name (`tutorial_1`, `arena1_3`, …). It skips the selector, so the challenge's weapon and completion requirements are not checked — your saved inventory is still what you play with. |
| `--game PATH` | read the game's data from somewhere other than `game/` (see below). |
| `--log-level debug` | log every decision the engine makes, not just the milestones. The first thing to try when something misbehaves. |
| `--mute` | set the listener's gain to zero: the game runs in silence. |
| `--no-speech` | never speak, so a test run does not talk over your screen reader. |
| `--exit-after SECONDS` | quit cleanly after this long, for unattended runs. |

A game started with `--endless` or `--challenge` saves its score, kills and
stats like any other, so it can legitimately unlock things.

### `--game`

The port does not hard-code where the original's files are: it reads `game/`
unless `--game PATH` (or the `AUDIODEFENCE_GAME` environment variable) names
another folder holding the data — one with `meta/` and `sounds/` inside it.
With the game in the repository you never need the option; it is there for the
cases where the data is somewhere else:

    py AudioDefence.py --game "D:/backups/audiodefence.app"

* a clone without `game/` (if it is ever ignored by git), with your own copy
  kept elsewhere;
* running against a second copy — another version of the bundle, or one you
  have edited — without touching `game/`;
* a packaged build whose data sits beside the executable.

It accepts the app bundle itself or a folder holding it (`audiodefence.app` or
`Payload/audiodefence.app` inside). The first line of the log says which path
won, so it is easy to tell whether the option took effect:

    main INFO game data: D:/backups/audiodefence.app (from the AUDIODEFENCE_GAME environment variable)

## Working on the port

The rule the port is written by: **never from memory**. Before changing a
ported method, read the original again — the address is in the comment above
it — and compare side by side.

    py tools/query.py digest "ADEnemy update:"        pseudo-code for a method
    py tools/query.py digest "ADWeapon " 90           a whole class, skipping tiny accessors
    py tools/query.py fn "ADPlayer update:"           the full annotated listing
    py tools/query.py sel setHeadOrientation:         who sends a selector
    py tools/query.py callers "ADBrickManager loadNextBrick"
    py tools/query.py str "brick_chance"              who references a string
    py tools/query.py ivar "ADEnemy._life"            who reads / writes an ivar
    py tools/query.py const 0.8                       who loads a float constant
    py tools/listing.py "ADWeapon fire" 0x100 0x200   a range of one listing
    py tools/nib_layout.py --all ADMainMenuViewController   a screen's frames and labels
    py tools/verify_stats.py                          every weapon and enemy vs the plists
    py tools/verify_updater.py                        the updater, end to end, offline

The digests are condensed and sometimes drop code that matters — when a branch
does not add up, read the `.s` listing for the same function. Annotation
conventions: `[receiver selector:args]` message sends, `self->ivar` field
access, `tN = …` temporaries, `if (cond) goto loc_…` branches, `switch (…)`
decoded jump tables, `one of {…}` where a value depends on the path taken.
Integer division by constants appears in compiled form — §2 of
`docs/GAME_STRUCTURE.md` has the patterns.

Screens are built from the NIB dumps in `analysis/data/nibs/`: the port uses
the iPhone tag-2781 layout, and the `Accessible_*` NIB wherever the original
has one, because the game swaps those in when VoiceOver is running.

When something has to differ from the original it goes in the Divergences
section of `docs/PORTING_NOTES.md`; when a bug of the original's is kept on
purpose it goes in the quirks section. Both say why.

Everything in the repository is stored with LF endings (`.gitattributes` says
so, and `game/`, `vendor/` and `analysis/bin/` are marked binary so not a byte
of them is touched). The tools write LF too, whatever machine they run on, so
regenerating `analysis/` produces no line-ending churn to commit.

## Rebuilding and recovering

Everything except `audiodefence/`, `tools/`, `docs/` and `game/` can be
regenerated. Run these from the project root.

**The whole analysis** — needs `capstone` (and `av` for the sound durations):

    py tools/macho.py extract game/audiodefence analysis/bin
    py tools/objc.py analysis/bin/audiodefence_arm64
    py tools/disasm.py analysis/bin/audiodefence_arm64 --out analysis
    py tools/query.py make-digests
    py tools/resources.py game --out analysis/data
    py tools/extract_hrtf.py analysis/bin/audiodefence_arm64

**The HRTF**, if `assets/hrtf/audiodefence_ircam1050.mhr` is deleted:

    py tools/build_hrtf.py

It rebuilds the file from `analysis/data/embedded_hrtf.dat` and prints the
interaural level difference and delays at five angles as a sanity check — a
sound on the right should be louder and earlier in the right ear. Add
`--verify` to replay the original's panner maths for every angle and compare
the two (non-zero exit code if they disagree); the file written is the same
either way. If `analysis/data/embedded_hrtf.dat` is gone as well, extract it
first — and note that the extractor needs the thin arm64 slice, not the fat
`game/audiodefence`:

    py tools/macho.py extract game/audiodefence analysis/bin
    py tools/extract_hrtf.py analysis/bin/audiodefence_arm64      needs capstone
    py tools/build_hrtf.py

## Building an executable

    py -m pip install pyinstaller

Then **double-click `compiler.py`** in Explorer, or type `py compiler.py` on
its own. It asks which build you want:

    1. Release build: file the changelog under the version, build, and zip
    2. Test build: build, zip, then run it for ten seconds and check its log
    3. Build without the zip
    4. Clean build: empty PyInstaller's cache first, for when a build behaves oddly
    5. Build with a console window, to see why the game will not start
    6. One-file build: a single executable instead of a folder
    7. Build without the game's data
    8. Show what a release build would do, without building anything
    0. Quit

Type the number and press Enter. The window waits for Enter at the end, so you
can hear how it went before it closes.

That is the whole build. The script checks what it needs, runs PyInstaller with
the right arguments, copies the game's data next to the executable and says
where the result is: `dist\AudioDefence\AudioDefence.exe`, in a folder that
runs on a machine with no Python on it at all.

Each choice is one of the options in the table below, and they still work typed
out — `py compiler.py --test` builds straight away with no menu. Run with no
options and nothing to type into — from a script — it goes straight to the
release build.

PyInstaller is the only extra package, and it goes in the same Python you play
with: a build is made by following the game's own imports, so `pygame-ce`,
`numpy`, `av`, `comtypes` and `prismatoid` have to be installed there too.
`prismatoid` is optional to play from source but not to build: a release has to
carry it, or JAWS players would hear SAPI 5. The script names
anything that is missing and stops rather than building half a game. 64-bit
Python on Windows produces a 64-bit Windows executable, and only that — there
is no cross-compiling to another system.

| option | what it does |
|---|---|
| `--onefile` | one executable instead of one folder — see below before you reach for it |
| `--no-game` | do not copy the game's data; the build then needs `--game PATH` to find it |
| `--console` | keep a console window beside the game, where a failed start-up prints its traceback |
| `--clean` | empty both of PyInstaller's working places first — this project's `build\` folder and the shared cache in `%LOCALAPPDATA%\pyinstaller` — when a rebuild behaves oddly. `dist\` is untouched, and so is everything in the repository |
| `--test` | run the result for ten seconds afterwards and read its log: that it found the game data, that the game's own HRTF is in use, and that it ended without a traceback |
| `--dry-run` | print what would happen, build nothing — including every file that would land beside the executable |
| `--no-package` | do not make the zip. A build otherwise ends by packing `dist\AudioDefence` into `dist\AudioDefence-Win-<version>.zip`, which is what a release's asset is and what the updater reads, warning first if `VERSION` is missing or `changelog.txt` still starts with `unrelease:` |

### Cutting a release

The archive has to be a **zip**, not a rar: the updater opens it with Python's
own `zipfile` and reads single files out of it over HTTP, which is what makes a
small fix a small download, and nothing can do either with a rar without
shipping an extractor. Every build makes it, unless you choose the build without
the zip (`--no-package`).

New changes go in `changelog.txt` under one heading at the top, `unrelease:`,
one line each. You never rename that heading yourself — the build files it.
In order:

- put the version in `VERSION`, exactly as GitHub will have it: `26.09.21-1`
- double-click `compiler.py` and choose **1, Release build**
- commit and push what it tells you changed — `changelog.txt`, and `VERSION`
  if it had to make one. Every build ends by saying whether there is anything
  to commit.
- tag the release `26.09.21-1` and upload `dist\AudioDefence-Win-26.09.21-1.zip`

The release build — choice 1, or `py compiler.py` with no options from a
script — does three things to the repository before it copies anything:

- the lines under `unrelease:` move to the entry headed exactly as `VERSION`
  says, build number and all: `26.09.21-1:`. If that entry is already there —
  you built again without changing `VERSION` — they go to the bottom of it
  instead of starting another. Change the number in `VERSION` and the next
  release build starts a new entry.
- `unrelease:` stays at the top, empty, ready for whatever changes next. If
  someone has deleted that line, it is put back.
- if there is no `VERSION` file, one is made, starting at today's first
  release: `26.09.21-1` on the 21st of September 2026.

The copy of the changelog beside the executable is the same, less the empty
`unrelease:` line, so it opens on the newest version. Every version's lines are
followed by one blank line, so where one version ends is something you hear.
Nothing under `unrelease:` means nothing is moved and the repository's
changelog is not touched. Building twice without committing is harmless: the
second build finds `unrelease:` already empty.

**Every other choice** — the test build, the clean build, the build without
the zip and the rest, or any of their options typed out — leaves the changelog
exactly as it is, because those builds are for trying something, not for
releasing it, and they end by saying there is no need to commit. If such a
build is zipped, it says so: its changelog still opens with `unrelease:`.
Choice 8, *Show what a release build would do*, reads out what the release
build would do to the changelog without writing anything.

`VERSION` is **`YY.MM.DD-XX`**: last two digits of the year, month, day, and
which release of that day it is, counting from 1. The first release on the 20th
of September 2026 is `26.09.20-1`; a second one the same day is `26.09.20-2`.
The compiler never works the number out: it follows whatever you wrote in
`VERSION`, and the changelog entry is named the same.

The build carries the number inside the executable rather than beside it: the
compiler reads `VERSION` from the repository and compiles it in. So there is no
`VERSION` file in a built game's folder, and nothing a player edits or deletes
there can change what the game thinks it is, or stop it from updating. A
`VERSION` file an older build left beside the executable is ignored. You only
ever change the number in the repository's `VERSION`. A build made with an
option while the repository has no `VERSION` file carries no number and never
offers an update, which is the one way to ship something that cannot be
updated afterwards; the release build never does this, because it starts the
file first.
Run from source, the game does the same as a release build when there is no
`VERSION` file: it makes one, at today's first release.

A build also carries three pieces of text beside the executable:
`changelog.txt`, `license.txt` (the repository's `LICENSE`, renamed so
Windows opens it without asking what with), and `readme.html` — this file,
converted at build time by
`tools/md_to_html.py`, which needs nothing installed. HTML rather than Markdown
because a screen reader moves through it by heading, table and list, where a
`.md` file reads every `#` and `|` aloud. The page is not committed, so it
cannot drift from this one; if the Markdown ever grows something the converter
does not know — a fenced code block, a numbered list — the build says so and
writes no page rather than shipping one with holes in it.
`py tools/md_to_html.py --check README.md` asks the same question at any
time.

### What a build carries, and what it does not

The port, the HRTF and the two vendored DLLs go inside the build. `game/` does
not — and `game/` is the game's audio: the 918 sound files under `game/sounds/`
(the narration, the zombies, the weapons, the music), the playlists under
`game/meta/` that arrange them, the plists and the strings. Every one of those
is Somethin' Else's recording, not the port's, and a build carries them with
it.

The script copies `game/` **next to the executable** — `AudioDefence.exe` and
`game/` side by side — which is where `audiodefence/paths.py` looks when
frozen, and `--game PATH` (`AUDIODEFENCE_GAME`) still overrides it. Build with
`--no-game` and you get the port alone: no sounds, silent until it is pointed
at a copy of the original. Everything else is read out of the bundle
PyInstaller unpacks, so `assets/hrtf` and `vendor/` need no copy.

`changelog.txt` is copied next to the executable as well, so whoever plays the
build can read what changed without the repository.

### One folder, not one file

The default is a folder, and that is the right shape here. `--onefile` gives a
single executable that unpacks its whole payload — Python, pygame, numpy and
av's FFmpeg, well over 100 MB of it — into `%TEMP%` at every launch, which is
seconds of silence before the game says anything. The one-folder build starts
at once. (One file does work: the game's data is still looked for beside the
executable, not inside the payload.)

### Checking the result

    py compiler.py --test

After building it starts the game for ten seconds and reads
`%APPDATA%\AudioDefence\audiodefence.log` for the three things that matter:
that the first line says `game data: … (from the game folder next to the
executable)` and not `(missing)`; that `game HRTF audiodefence_ircam1050 not in
use` does not appear, which would mean `assets/hrtf` never made it into the
bundle and OpenAL has quietly substituted its own; and that nothing ended in a
traceback. The same run by hand is
`dist\AudioDefence\AudioDefence.exe --exit-after 10 --log-level debug`.

What no script can check for you is the sound. Start it normally and listen to
the main menu — once with NVDA, and once with NVDA closed so that SAPI is
exercised. (SAPI goes through `comtypes`, which builds its COM wrappers in
memory in a frozen program instead of writing them to disk, so it is worth
hearing rather than assuming.) If you have another screen reader, such as JAWS,
listen once with that too: it goes through Prism, whose compiled half the
build carries in `_internal\prism\_native`.

### If something is missing from the build

`av`, `comtypes` and Prism (`prism`) are all imported the first time they are
needed rather than at the top of a module (`s3d/decoder.py`,
`platform/speech.py`), so they are what PyInstaller's analysis is likeliest to
walk past. The script already names them outright — `--collect-all av`,
`--collect-submodules comtypes`, `--collect-all prism` — so the usual failures
are covered. Prism needs two more: its compiled Python module,
`prism\_native\_prism_cffi.pyd`, sits in a folder that is not a package, so
`--collect-all` leaves it behind and the script adds it by name; and
`--hidden-import _cffi_backend`, which that module needs and nothing names. For anything else that turns up as a
`ModuleNotFoundError` in a frozen run, add `--hidden-import NAME` to the list
in `command()` in `compiler.py`.

### No console window

The script passes `--windowed`, so the built game is one window and not two: a
console alongside it would be another thing in the alt-tab order announcing
itself, for nothing. What a console is good for is the moment start-up fails,
so `_report_failure` in `AudioDefence.py` does that job without one — it writes
the traceback to `%APPDATA%\AudioDefence\crash.txt` and speaks a line saying
so, and falls back to printing and waiting for Enter when there *is* a console
to print in. Build with `--console` to get one; a run from source has had one
all along.

### Afterwards

`build/` is PyInstaller's scratch folder, `dist/` is its output and
`AudioDefence.spec` is the file it writes from the arguments above; the script
regenerates all three, and none of them belongs in the repository. The reverse
engineering lives in `analysis/` precisely so that `build/` stays free.

An unsigned executable is not something Windows trusts: expect SmartScreen to
warn the first time it runs on another machine, and antivirus to hold that
first start while it scans. Signing is the only real cure.

## Troubleshooting

Everything the port does is logged to `%APPDATA%\AudioDefence\audiodefence.log`
(`--log-level debug` for more). If it fails before it can play anything, the
traceback is spoken and written to `crash.txt` in that same folder.

**Positioning feels flat, or sounds come from the wrong place.** Look for:

    s3d ERROR game HRTF audiodefence_ircam1050 not in use (found=False, status=…)

OpenAL quietly substitutes its own HRTF when the game's is missing. Rebuild it
as above; no such line means the game's own HRTF is loaded.

**"the game's data is not where the port looks for it".** `game/` is empty or
in the wrong shape: it needs `meta/` and `sounds/` at its top level. Point
`--game` at another copy if it lives elsewhere.

**Nothing is spoken.** With NVDA running the port talks to it through
`vendor/nvda/nvdaControllerClient64.dll`; with another screen reader it goes
through Prism, which needs `prismatoid`; with none it falls back to SAPI 5,
which needs `comtypes`. The log says which one it took ("speech: JAWS, through
Prism", or "Prism not available" when it could not load it).

**A screen reads in an odd order.** The reading order is reconstructed from the
NIB frames (`audiodefence/ui/accessibility.py`), so it approximates VoiceOver's
rather than copying it. Check that screen's frames with
`tools/nib_layout.py --all`.

## Credits

*Audio Defence: Zombie Arena* was made by **Somethin' Else**, and everything
worth hearing in this port is theirs. The Papa Engine that carries it announces
itself as "Somethin' Else Papa Engine" when it starts, and the source paths
still inside the binary point at Papa Sangre, which is a nice thing to find at
two in the morning.

The game's own Credits screen, under Info, says so too: the nib lists everyone
who made it but never names the studio, so the port puts **Audio Defence:
Zombie Arena, by Somethin' Else** above that list, and adds the port's own
credits and this repository's address in a section after it.

This port, on the other hand:

**Claude — Opus 5, highest effort.** Wrote every line of the port. Read the
disassembly, ported it method by method, argued about tail calls, and was wrong
twice in one evening about an ambience loop before a human with working ears
put it right. Without it this would have stayed an idea. Occasionally
over-confident, reliably apologetic.

**Loh Boon Keat** — the prompter. Directed the whole thing, made every
judgement call about what to fix and what to leave alone, held the line on
"compare it with the original, don't rely on your memory" until it stuck, and
play-tested a game he was building at the same time.

**Wong Wee Xiang** — the tester, and the reason this list of fixes is as long as
it is. Found the Tactical Rifle cutting itself off, the death screen that would
not let go, the Chainsaw ambience that outlived the game, the rewards paid
twice, and the quiet round after pressing Try again. If you enjoy a bug being
fixed before you meet it, thank him.

**Muhammad Hajjar** — who inspired the project and worked out how to point an AI
at a shipped iOS binary and get a Windows game back out of it. The concept is
his; the rest is bookkeeping. He now writes the port as well, with the same
Claude Opus 5 at the same highest effort, so from here there are two people
directing it and two sets of commits.

## Licence

The port's own code — everything in `audiodefence/`, `tools/`, `compiler.py` and
the documentation — is the author's to license.

`game/` is the original game: Somethin' Else's data, audio and layouts. It is
not ours and it is not covered by the port's licence. `analysis/` is derived
from their binary and is in the same position. A build produced by `compiler.py`
contains all of it.

This project is not affiliated with Somethin' Else, and no claim is made to
their work.
