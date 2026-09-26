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

* One entry per line, no wrapping, no bullets, no "Fixed:", no version numbers, no addresses.
* Plain sentences about what a player notices, not what the code does.
* **Name a screen or a tab in words, not as a path.**  "The Speech tab in Settings", not "Settings,
  Speech": a comma standing for a step only reads as one to somebody who already knows the way, and read
  aloud it is two nouns and a pause.
* **A sentence or two, and stop.**  Say what is different now; leave out what it used to do, why it did
  that, how it was measured, and every number that is not the point.  The reasoning, the measurements and
  the addresses belong in `docs/PORTING_NOTES.md`, where they can be looked up by whoever wants them - a
  player reading the list wants to know what changed, not to be walked through it.  If an entry needs a
  "which used to" or a semicolon to hold it together, it is two entries or it is too long.  Thirty words
  is long; the whole file is under thirty for every entry, so a new one that runs past it is a rewrite,
  not an exception.
* **Only the `unrelease:` block is edited.**  The released sections were cut down once, on 2026-09-24,
  because they had been written the long way; that is done and they are left alone now.  A version that
  has shipped is what its players were told at the time, and rewriting it changes the record for no one's
  benefit.
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
