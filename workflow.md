# Working on this port

Audio Defence: Zombie Arena (Somethin' Else / Bitbee, 2015) recovered from the iOS binary and rebuilt in
Python for Windows and the Mac.  There was never any source: everything here was read out of an arm64 app
and written again.  These are the conventions that keeps it honest.  The README says what the game is and
how to build it; `docs/PORTING_NOTES.md` says what was changed and why.

## The port is faithful first

* **Reproduce the original's behaviour, including its bugs.**  A quirk is only worth keeping if it is the
  original's - see the fifteen listed in the notes - and a bug is only worth fixing if somebody asked for it
  to be fixed.
* **Work from the disassembly, not from memory.**  `py tools/query.py digest <regex>` gives the annotated
  pseudo-code of a method, `sel` finds who sends a selector, `callers` who calls what.  Read the method you
  are porting while you port it; the addresses in the comments are how the next person checks your work.
* **Every departure is written down.**  A divergence or a port addition goes in `docs/PORTING_NOTES.md`
  with the address of the original method it departs from, and the count at the top of the README moves
  with it.  If it was asked for, say so: "(user request)".

## The changelog is for players

`changelog.txt` is what a player reads.  New lines go under the `unrelease:` heading at the top of the
file, **at the end of that block** - it reads in the order things were done.

* **Write the line.**  A change a player would notice gets one, and whether the `unrelease:` block is
  empty or already long is not a reason either way.  Nor is "the thing it fixes has not shipped yet":
  that is a judgement about what a player needs to know, and it is not mine to make.  The one reason not
  to write a line is being told, for that change, that it does not need one.
* One entry per line, no wrapping, no bullets, no "Fixed:", no version numbers, no addresses.
* Plain sentences about what a player notices, not what the code does.
* **Name a screen or a tab in words, not as a path.**  "The Speech tab in Settings", not "Settings,
  Speech": a comma standing for a step only reads as one to somebody who already knows the way, and read
  aloud it is two nouns and a pause.
* **Say what the game can now do, not which example arrived with it.**  "The game can be played in
  another language", not "the game can be played in Russian"; "you can turn with buttons on a controller",
  not the two buttons it shipped with.  A changelog line outlives the thing that prompted it, and a
  player reading it later should learn what the game is capable of.  Name the particular language,
  controller or mode in the README, where the list is kept up to date.
* **A sentence or two, and stop.**  Say what is different now; leave out what it used to do, why it did
  that, how it was measured, and every number that is not the point.  The reasoning, the measurements and
  the addresses belong in `docs/PORTING_NOTES.md`, where they can be looked up by whoever wants them - a
  player reading the list wants to know what changed, not to be walked through it.  If an entry needs a
  "which used to" or a semicolon to hold it together, it is two entries or it is too long.  Thirty words
  is long; the whole file is under thirty for every entry, so a new one that runs past it is a rewrite,
  not an exception.
* **A line goes under `unrelease:` and nowhere else.**  The version blocks below it - `26.09.26-1:` and
  every one under that - belong to whoever is writing the game.  Do not add to them, take from them,
  reword them, reorder them or reflow them, and do not move a line between them.  A version that has
  shipped is what its players were told at the time.

  This holds whatever the reason looks like: a line in the wrong place, a fault described in a version
  that has gone out, a phrase that would read better.  Say so and leave it.  Being asked for that change
  is the one thing that opens a released block - not a good reason, not an obvious improvement, and not
  a tidy-up that seems in the same spirit as a past one.  It was set aside once, on
  2026-09-24, when the released sections were cut down because they had been written the long way, and
  once by hand when the updater came out of the preserved copy - both times because the maintainer asked
  for exactly that.
* A plain `py compiler.py` files the unreleased lines under the version it builds, so leave them where
  they are until then.

## Commits

* One piece of work per commit, with a subject line and a body that says **why**, not just what.
* Pull before you start and push when you are done: more than one person works on this, and a change left
  uncommitted blocks the others.
* Never commit what the build leaves behind (`build/`, `dist/`, `*.spec` are ignored); the game's own data
  in `game/` *is* committed, so a clone has everything.

## Two things that break quietly

* `audiodefence/platform/updater.py` holds `REPOSITORY`, the repository the game updates itself from.  It
  belongs to the repository the build is made in.
* The release zips' names decide which one an older build downloads: `AudioDefence-Win-<version>.zip` must
  sort before `AudioDefenceMac-<version>.zip`, because builds from before the Mac port take the first zip
  they find.  Let the compiler name them.

## Testing

Tests are written for the change at hand and are not kept in the repository.  Use a scratch profile - point
`APPDATA` at a temporary folder - so a test never touches a player's save, and silence the listener
(`engine.al.alListenerf(oal.AL_GAIN, 0.0)`) so a test run is not heard.

**Test a thing once.**  A check that has passed for code nobody has touched since will pass again, and
running it again costs the time it takes and says nothing.  So:

* Test what the change touches, and nothing else.  The shield death sound is not evidence about the speech
  card.
* Do not rebuild a check that has just run to prove the same thing again.  Two passes over one change means
  the first one was not trusted, and the answer to that is a better check, not a second one.
* Run it again only when what it covers has changed underneath it - a refactor across the same path, a fix
  on top of the fix.  Say which change made it worth running again.
* A smoke run of the real game is worth one pass at the end of a piece of work, not one per edit.

**Text the player reads or hears has to be translated too.**  The port can be played in another language
(`localization/`), and `py tools/verify_localization.py` fails when a phrase the player can reach is still
English.  Run it after changing or adding anything a screen says, and put the new phrase in each language
file - on 2026-09-26 it caught four that a week of changes had left behind.

**A rule needs all of them, not a handful.**  Whenever a change turns on a threshold, a flag or a test that
will be applied across a whole set - every sound, every screen, every enemy - measure the whole set before
settling it, and say in the commit how many were looked at.  Twice on 2026-09-25 a rule drawn from the few
files in front of me was wrong across the rest: a 20 ms cap on trimming a loop's tail, picked from ten
recordings, had no gap to sit in once all 915 were measured; and `has_escape`, which means the original
implements an escape, was used as though it meant the screen has somewhere to go, which is false for the
main menu.  The first had to be reverted, the second was found by a player.  Checking the set costs one
command and settles it.
