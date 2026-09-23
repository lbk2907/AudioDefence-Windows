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
* Plain sentences about what a player notices, not what the code does.  Keep it short; the reasoning
  belongs in the porting notes.
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
