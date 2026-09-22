"""PORT ADDITION: find, fetch and install a new build of the port.

The iOS game was updated by the App Store, so there is nothing here to port; this is the Windows answer to
the same problem, and it is written to leave a player's progress alone by construction rather than by care.

**Progress cannot be lost.**  Everything the game writes - `save.json`, `settings.json`, `keys.json`,
`alsoft.ini`, the log - lives in `%APPDATA%\\AudioDefence` (``paths.user_dir``).  The installed folder is
read-only once the game is running, so an update replaces program files and never touches a save.  The
updater refuses to write anything outside the folder the executable is in.

**Only what changed is downloaded.**  The release is one zip of around 155 MB, and nearly all of it is the
game's audio, which is the same in every build.  ``remotezip`` reads the archive's index over HTTP, and
each member's CRC-32 is compared with the file already installed; a build that only changes Python
downloads a few megabytes.  If the server will not serve ranges, or the archive turns out to be zip64,
the whole asset is fetched instead and the update still works.

**Locked files.**  A running program holds its own executable and its DLLs open, so the last step cannot
be done from inside the game.  The changed files are staged in `%APPDATA%\\AudioDefence\\updates`, the
files they will overwrite are backed up beside them, and a small PowerShell script waits for the game to
exit, copies the staged files in, and starts the game again.  If the copy fails it puts the backup back.
The script is PowerShell rather than a .cmd because a player's folder can have non-ASCII characters in it
and batch handles those badly.

**The Mac.**  The same, with the Mac's names: the saves are in ``~/Library/Application Support/AudioDefence``,
the release asset is ``AudioDefenceMac-<VERSION>.zip`` (each build takes the zip made for it, off the same
release), what is replaced is ``AudioDefence.app`` beside readme.html and the rest, and the hand-off is a
shell script, which puts the files in with ``ditto`` and opens the app again.  An app is full of symbolic
links, so the zip keeps them as links (with each file's execute bit), and they are compared, fetched and put
in place as links.  An app macOS is running from a private copy (App Translocation, for an app opened where
it was downloaded) cannot be updated, and the player is told to move it first.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import stat
import zipfile
import zlib

from . import host, version
from .. import paths
from .remotezip import RemoteZip, RemoteZipError, USER_AGENT

log = logging.getLogger('platform.updater')

REPOSITORY = 'lbk2907/AudioDefence-Windows'
LATEST_RELEASE = 'https://api.github.com/repos/%s/releases/latest' % REPOSITORY
RELEASES_PAGE = 'https://github.com/%s/releases' % REPOSITORY
TIMEOUT = 20

#: the folders a build owns completely, and so the only ones a file is ever deleted from.  Anything a
#: player has put in the game's folder themselves is left alone.
OWNED_DIRS = ('AudioDefence.app/',) if host.MAC else ('_internal/', 'game/')
#: read and written in whole-megabyte order; small enough that a cancel is noticed quickly
CHUNK = 1 << 20


class UpdateError(Exception):
    """Something went wrong that the player should be told about, in words they can act on."""


class Release:
    def __init__(self, data: dict):
        self.tag = str(data.get('tag_name') or '')
        self.name = str(data.get('name') or self.tag)
        self.notes = str(data.get('body') or '').strip()
        self.url = str(data.get('html_url') or RELEASES_PAGE)
        self.asset_name = ''
        self.asset_url = ''
        self.asset_size = 0
        # the zips' names, and why the Mac's has no dash, are in host.ARCHIVE_PREFIXES
        zips = [asset for asset in data.get('assets') or () if str(asset.get('name', '')).lower().endswith('.zip')]
        for asset in sorted(zips, key=lambda asset: -self.suits(str(asset.get('name', '')))):
            if self.suits(str(asset.get('name', ''))):
                self.asset_name = asset['name']
                self.asset_url = asset['browser_download_url']
                self.asset_size = int(asset.get('size') or 0)
                break

    @staticmethod
    def suits(name: str) -> int:
        """How well a zip on the release fits this build: 2 for this platform's own
        ('AudioDefenceMac-26.09.22-1.zip' on the Mac, host.archive_name), 1 on Windows for a zip that names
        no platform, as the first releases' did, 0 for the other platform's, which is never taken."""
        low = name.lower()
        if low.startswith(host.ARCHIVE_PREFIXES[host.ARCHIVE_TAG].lower()):
            return 2
        others = [prefix.lower() for tag, prefix in host.ARCHIVE_PREFIXES.items() if tag != host.ARCHIVE_TAG]
        others.append('audiodefence-mac-')                # the Mac zip's name before it lost its dash
        return 0 if host.MAC or any(low.startswith(other) for other in others) else 1

    def __repr__(self) -> str:
        return '<Release %s %s>' % (self.tag, self.asset_name or 'no zip')


class Plan:
    """What installing this release would change."""

    def __init__(self, release: Release):
        self.release = release
        self.fetch: list = []                             # (path here, member there) for what differs
        self.remove: list = []                            # files this build has and the new one does not
        self.unchanged = 0
        self.staging = ''
        self.archive = None                               # the remote index, when ranges were served
        self.prefix = ''                                  # the folder inside the zip, if it has one

    @property
    def download_size(self) -> int:
        return sum(entry.compressed_size for _relative, entry in self.fetch)

    @property
    def nothing_to_do(self) -> bool:
        return not self.fetch and not self.remove


# ================================================================================ where we are installed
def install_dir() -> str:
    """The folder a release's zip unpacks over: the one holding AudioDefence.exe, or AudioDefence.app."""
    return paths.EXE_DIR


def restart_target() -> str:
    """What the hand-off starts again once the files are in: the executable, or the Mac app."""
    if host.MAC:
        return getattr(paths, 'APP_BUNDLE', os.path.join(install_dir(), 'AudioDefence.app'))
    return sys.executable if paths.FROZEN else os.path.join(install_dir(), 'AudioDefence.exe')


def updates_dir() -> str:
    path = os.path.join(paths.user_dir(), 'updates')
    os.makedirs(path, exist_ok=True)
    return path


#: written into a staging folder once everything in it has been downloaded and checked.  Without it a
#: folder is a half-finished download and can be thrown away; with it, an update is waiting to be put in
#: place and must survive until it has been.
READY_MARKER = 'ready.json'


def mark_ready(plan: 'Plan') -> None:
    """Say that this staging folder is complete, and what applying it still has to remove."""
    with open(os.path.join(plan.staging, READY_MARKER), 'w', encoding='utf-8') as fh:
        json.dump({'tag': plan.release.tag, 'remove': list(plan.remove)}, fh)


def pending_update():
    """An update already downloaded and waiting to be put in place: (folder, tag, removals).

    A player who answers "Not yet" has the files on disk already; the next start offers to finish the job
    rather than downloading them again."""
    root = os.path.join(paths.user_dir(), 'updates')
    best = (None, '', [])
    if not os.path.isdir(root):
        return best
    here = version.current()
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        marker = os.path.join(folder, READY_MARKER)
        if not os.path.isfile(marker) or not os.path.isdir(os.path.join(folder, 'payload')):
            continue
        try:
            with open(marker, encoding='utf-8') as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            continue
        tag = str(saved.get('tag') or '')
        # A marker whose version we are already running is one that has been applied: its folder is
        # rubbish the hand-off could not delete, not an update waiting to happen.
        if tag and version.is_newer(tag, here) and (not best[1] or version.is_newer(tag, best[1])):
            best = (folder, tag, [str(r) for r in saved.get('remove') or ()])
    return best


def clean_up_staging() -> None:
    """Throw away half-finished downloads, and folders from updates that have already been applied.

    The hand-off script deletes its own staging folder, but PowerShell holds the script file open while it
    runs it, so the last delete can fail and leave the folder there.  What must *not* be swept is an
    update that has been downloaded and not yet put in place, so anything ``pending_update`` would offer
    is left alone.  A folder that cannot be removed is left and tried again next time."""
    root = os.path.join(paths.user_dir(), 'updates')
    if not os.path.isdir(root):
        return
    keep, _tag, _remove = pending_update()
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isdir(path) or path == keep:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if os.path.isdir(path):
            log.info('%s is still there; it will be cleared next time', path)


def can_update() -> tuple:
    """(allowed, why not).  Updating replaces the built files, which a checkout does not have."""
    if not paths.FROZEN:
        return False, 'this is the source version, so it updates with git rather than from a release'
    root = install_dir()
    if host.MAC and '/AppTranslocation/' in restart_target():
        return False, ('macOS is running the game from a temporary copy, as it does for an app opened where '
                       'it was downloaded. Move the AudioDefence folder somewhere else with Finder, your '
                       'Applications folder for one, and open the game from there')
    try:
        probe = os.path.join(root, '.update-probe')
        with open(probe, 'w') as fh:
            fh.write('')
        os.remove(probe)
    except OSError:
        return False, ('the game is installed somewhere it cannot write to. Move it out of Program Files, '
                       'or run the update as an administrator' if not host.MAC else
                       'the game is in a folder it cannot write to. Move the AudioDefence folder somewhere '
                       'you can write to, such as your Applications or Documents folder')
    return True, ''


# ============================================================================================ the check
def _api(url: str) -> dict:
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
                                                   'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError('there are no releases to update to yet') from exc
        if exc.code in (403, 429):
            raise UpdateError('GitHub is asking us to wait before checking again. Try later') from exc
        raise UpdateError('GitHub answered with an error, number %d' % exc.code) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateError('could not reach GitHub. Check your internet connection') from exc
    except json.JSONDecodeError as exc:
        raise UpdateError('GitHub sent something we could not read') from exc


def check() -> Release | None:
    """The newest release when it is newer than this build, else None.  Runs on a worker thread."""
    release = Release(_api(LATEST_RELEASE))
    if not release.tag:
        raise UpdateError('the newest release has no version number')
    here = version.current()
    if not here:
        log.info('this build has no version, so %s is not offered', release.tag)
        return None
    if not version.is_newer(release.tag, here):
        log.info('%s is the newest release and this build is %s', release.tag, here)
        return None
    if not release.asset_url:
        raise UpdateError('release %s has no zip to download for %s' % (release.tag, 'the Mac' if host.MAC
                                                                             else 'Windows'))
    return release


# ============================================================================================= the plan
def _crc(path: str) -> int | None:
    """The CRC-32 of a file already installed, or None when there is no such file."""
    try:
        crc = 0
        with open(path, 'rb') as fh:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    break
                crc = zlib.crc32(block, crc)
        return crc
    except OSError:
        return None


def _installed_crc(path: str, link: bool) -> int | None:
    """What an installed file is to compare with a member of the zip: its contents' CRC-32, or - for a
    symbolic link, whose member holds where it points - the CRC-32 of where it points.  A file where the
    release has a link, or a link where it has a file, matches nothing, so it is replaced."""
    if os.path.islink(path) != link:
        return None
    if link:
        try:
            return zlib.crc32(os.readlink(path).encode('utf-8'))
        except OSError:
            return None
    return _crc(path)


def _write_member(destination: str, data: bytes, mode: int) -> None:
    """One member into the staging folder, as the link or the file it is, execute bit and all."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.lexists(destination):
        os.remove(destination)
    if stat.S_ISLNK(mode):
        os.symlink(data.decode('utf-8'), destination)
        return
    with open(destination, 'wb') as fh:
        fh.write(data)
    if mode & 0o111:
        os.chmod(destination, stat.S_IMODE(mode))


def _info_mode(info: zipfile.ZipInfo) -> int:
    """The Unix mode a zip member carries, or 0 for one made on Windows."""
    return info.external_attr >> 16 if info.create_system == 3 else 0


def _strip_prefix(names) -> str:
    """A zip made for a person to extract has one folder inside it; the installed files have not."""
    tops = {name.split('/', 1)[0] for name in names if '/' in name}
    if len(tops) == 1 and not any('/' not in name for name in names):
        return tops.pop() + '/'
    return ''


def build_plan(release: Release, cancelled=None) -> Plan:
    """Compare the release's index with what is installed.  Network and disk; worker thread."""
    plan = Plan(release)
    root = install_dir()
    try:
        archive = RemoteZip(release.asset_url, release.asset_size or None)
    except (RemoteZipError, urllib.error.URLError, OSError, TimeoutError) as exc:
        log.info('reading the release index a piece at a time did not work (%s); '
                 'the whole archive will be downloaded', exc)
        plan.fetch = None                                 # the signal to fall back to the whole file
        return plan
    members = archive.files()
    prefix = _strip_prefix(list(archive.entries))
    plan.archive = archive
    plan.prefix = prefix
    wanted = set()
    for name, entry in members.items():
        if cancelled is not None and cancelled():
            raise UpdateError('cancelled')
        relative = name[len(prefix):] if prefix and name.startswith(prefix) else name
        if not relative or relative.endswith('/'):
            continue
        wanted.add(relative)
        local = os.path.join(root, relative.replace('/', os.sep))
        here = _installed_crc(local, entry.is_link)
        if here == entry.crc:
            plan.unchanged += 1
        else:
            plan.fetch.append((relative, entry))
    plan.remove = _stale_files(root, wanted)
    return plan


def _stale_files(root: str, wanted: set) -> list:
    """Files under the folders a build owns that the new release does not have."""
    stale = []
    for owned in OWNED_DIRS:
        base = os.path.join(root, owned.rstrip('/').replace('/', os.sep))
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, files in os.walk(base):
            # a link to a folder is one member of the zip, not a folder to look inside
            for name in files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]:
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, root).replace(os.sep, '/')
                if relative not in wanted:
                    stale.append(relative)
    return stale


# ========================================================================================= the download
def download(plan: Plan, progress=None, cancelled=None) -> str:
    """Fetch what the plan asks for into a staging folder and return it.  Worker thread.

    `progress(done, total, what)` is called as it goes; `cancelled()` is asked often and stops the work."""
    staging = os.path.join(updates_dir(), plan.release.tag)
    shutil.rmtree(staging, ignore_errors=True)
    payload = os.path.join(staging, 'payload')
    os.makedirs(payload, exist_ok=True)
    if plan.fetch is None:
        _download_whole_archive(plan, payload, progress, cancelled)
    else:
        _download_changed_members(plan, payload, progress, cancelled)
    plan.staging = staging
    if not plan.nothing_to_do:
        mark_ready(plan)                                  # from here on the folder must survive a sweep
    return staging


def _report(progress, done, total, what) -> None:
    if progress is not None:
        progress(done, total, what)


def _stop(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise UpdateError('cancelled')


def _download_changed_members(plan: Plan, payload: str, progress, cancelled) -> None:
    total = plan.download_size
    done = 0
    for relative, entry in plan.fetch:
        _stop(cancelled)
        data = plan.archive.read(entry)                   # CRC checked inside
        _write_member(os.path.join(payload, relative.replace('/', os.sep)), data, entry.mode)
        done += entry.compressed_size
        _report(progress, done, total, relative)


def _download_whole_archive(plan: Plan, payload: str, progress, cancelled) -> None:
    """The fallback: fetch the release asset and unpack the files that differ out of it."""
    release = plan.release
    archive_path = os.path.join(os.path.dirname(payload), release.asset_name or 'update.zip')
    total = release.asset_size
    request = urllib.request.Request(release.asset_url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, \
                open(archive_path, 'wb') as fh:
            done = 0
            while True:
                _stop(cancelled)
                block = response.read(CHUNK)
                if not block:
                    break
                fh.write(block)
                done += len(block)
                _report(progress, done, total or done, release.asset_name)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateError('the download stopped before it finished') from exc

    root = install_dir()
    with zipfile.ZipFile(archive_path) as zf:
        names = zf.namelist()
        prefix = _strip_prefix(names)
        wanted = set()
        for info in zf.infolist():
            _stop(cancelled)
            if info.is_dir():
                continue
            relative = info.filename[len(prefix):] if prefix and info.filename.startswith(prefix) \
                else info.filename
            if not relative:
                continue
            wanted.add(relative)
            mode = _info_mode(info)
            if _installed_crc(os.path.join(root, relative.replace('/', os.sep)), stat.S_ISLNK(mode)) == info.CRC:
                plan.unchanged += 1
                continue
            destination = os.path.join(payload, relative.replace('/', os.sep))
            if stat.S_ISLNK(mode):
                _write_member(destination, zf.read(info), mode)
                continue
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with zf.open(info) as src, open(destination, 'wb') as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            if mode & 0o111:
                os.chmod(destination, stat.S_IMODE(mode))
        plan.remove = _stale_files(root, wanted)
    os.remove(archive_path)
    plan.fetch = []                                       # the payload is built; nothing left to fetch


# ============================================================================== backing up and handing over
def _payload_files(payload: str) -> list:
    out = []
    for dirpath, dirs, files in os.walk(payload):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]:
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, payload).replace(os.sep, '/'))
    return out


def back_up(staging: str, remove) -> str:
    """Copy the files about to be overwritten or removed, so a failed copy can be undone."""
    root = install_dir()
    payload = os.path.join(staging, 'payload')
    backup = os.path.join(staging, 'backup')
    shutil.rmtree(backup, ignore_errors=True)
    for relative in _payload_files(payload) + list(remove):
        source = os.path.join(root, relative.replace('/', os.sep))
        if not (os.path.isfile(source) or os.path.islink(source)):
            continue                                      # a new file has nothing to put back
        destination = os.path.join(backup, relative.replace('/', os.sep))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if os.path.islink(source):                        # a link is put back as the link it was
            os.symlink(os.readlink(source), destination)
        else:
            shutil.copy2(source, destination)
    return backup


def _ps_literal(text: str) -> str:
    """A PowerShell single-quoted string: the only character that needs escaping is the quote."""
    return "'%s'" % str(text).replace("'", "''")


SCRIPT = """\
$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$install   = {install}
$payload   = {payload}
$backup    = {backup}
$staging   = {staging}
$exe       = {exe}
$removals  = {removals}

# Wait for the game to let go of its own executable and DLLs.
for ($i = 0; $i -lt 600; $i++) {{
    if (-not (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 100
}}
Start-Sleep -Milliseconds 300

try {{
    Copy-Item -Path (Join-Path $payload '*') -Destination $install -Recurse -Force
    foreach ($relative in $removals) {{
        $victim = Join-Path $install $relative
        if (Test-Path -LiteralPath $victim) {{ Remove-Item -LiteralPath $victim -Force }}
    }}
}} catch {{
    # Put back exactly what was replaced, then leave the staging folder for a bug report.
    if (Test-Path -LiteralPath $backup) {{
        Copy-Item -Path (Join-Path $backup '*') -Destination $install -Recurse -Force
    }}
    Start-Process -FilePath $exe
    exit 1
}}

Start-Process -FilePath $exe
Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
"""


def write_handoff(staging: str, remove) -> str:
    """Write the script that swaps the files in once the game has quit, and return its path."""
    remove = list(remove)
    removals = '@(%s)' % ', '.join(_ps_literal(r.replace('/', os.sep)) for r in remove) if remove else '@()'
    script = SCRIPT.format(
        pid=os.getpid(),
        install=_ps_literal(install_dir()),
        payload=_ps_literal(os.path.join(staging, 'payload')),
        backup=_ps_literal(os.path.join(staging, 'backup')),
        staging=_ps_literal(staging),
        exe=_ps_literal(restart_target()),
        removals=removals,
    )
    path = os.path.join(staging, 'apply.ps1')
    with open(path, 'w', encoding='utf-8-sig') as fh:     # the BOM is how PowerShell knows it is UTF-8
        fh.write(script)
    return path


def _sh_literal(text: str) -> str:
    """A shell single-quoted string: a quote ends it, is escaped, and starts it again."""
    return "'%s'" % str(text).replace("'", "'\\''")


#: the Mac's hand-off, the same steps as SCRIPT.  ditto merges the staged files into the installed ones,
#: links as links; `open` starts the app the way Finder would.
SH_SCRIPT = """\
#!/bin/bash
pid={pid}
install={install}
payload={payload}
backup={backup}
staging={staging}
app={app}
removals=({removals})

# Wait for the game to let go of its files.
for i in $(seq 600); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
done
sleep 0.3

put_in() {{
    ditto "$payload" "$install" || return 1
    for relative in "${{removals[@]}}"; do
        rm -f "$install/$relative" || return 1
    done
}}

if ! put_in; then
    # Put back exactly what was replaced, then leave the staging folder for a bug report.
    if [ -d "$backup" ]; then ditto "$backup" "$install"; fi
    open "$app"
    exit 1
fi

open "$app"
rm -rf "$staging"
"""


def write_handoff_sh(staging: str, remove) -> str:
    """The Mac's hand-off script, and its path."""
    script = SH_SCRIPT.format(
        pid=os.getpid(),
        install=_sh_literal(install_dir()),
        payload=_sh_literal(os.path.join(staging, 'payload')),
        backup=_sh_literal(os.path.join(staging, 'backup')),
        staging=_sh_literal(staging),
        app=_sh_literal(restart_target()),
        removals=' '.join(_sh_literal(r) for r in remove),
    )
    path = os.path.join(staging, 'apply.sh')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(script)
    os.chmod(path, 0o755)
    return path


def apply(staging: str, remove) -> None:
    """Start the hand-off and return.  The caller quits the game straight afterwards."""
    remove = list(remove)
    back_up(staging, remove)
    if host.MAC:
        script = write_handoff_sh(staging, remove)
        try:
            # a session of its own, so it is not taken down with the game; not cwd=staging, which it deletes
            subprocess.Popen(['/bin/bash', script], cwd=paths.user_dir(), start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise UpdateError('the update could not be started: %s' % exc) from exc
        log.info('hand-off started; %d files to copy, %d to remove',
                 len(_payload_files(os.path.join(staging, 'payload'))), len(remove))
        return
    script = write_handoff(staging, remove)
    # CREATE_NO_WINDOW and nothing else.  DETACHED_PROCESS looks like the right flag for something that
    # has to outlive us, and it is not: it gives the child no console, and powershell.exe with no console
    # exits immediately without running the script.  CreateProcess still succeeds, so the failure is
    # silent - the game quits and the update is simply never installed.  A child survives its parent on
    # Windows anyway; DETACHED_PROCESS is about consoles, not lifetimes.
    creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    try:
        # not cwd=staging: a process cannot delete the folder it is sitting in, and the last thing the
        # script does is delete that folder
        subprocess.Popen(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                          '-WindowStyle', 'Hidden', '-File', script],
                         cwd=paths.user_dir(), creationflags=creation, close_fds=True)
    except OSError as exc:
        raise UpdateError('the update could not be started: %s' % exc) from exc
    log.info('hand-off started; %d files to copy, %d to remove',
             len(_payload_files(os.path.join(staging, 'payload'))), len(remove))


def size_text(byte_count: int) -> str:
    """'4.2 megabytes' - what a screen reader should say, not '4.2 MB'."""
    if byte_count >= 1 << 20:
        return '%.1f megabytes' % (byte_count / float(1 << 20))
    if byte_count >= 1 << 10:
        return '%.0f kilobytes' % (byte_count / float(1 << 10))
    return '%d bytes' % byte_count
