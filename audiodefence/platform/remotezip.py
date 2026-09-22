"""PORT ADDITION: read single files out of a zip on a web server, without downloading the zip.

A release archive is around 155 MB and almost all of it is the game's own audio, which does not change
between builds.  Downloading all of it to replace a few hundred kilobytes of Python would be the usual
way, and the wrong one on a metered or slow connection.

A zip is a container whose index sits at the *end*: the central directory lists every member with its
CRC-32, its compressed size and where its data starts.  GitHub serves release assets with
`Accept-Ranges: bytes`, so the index can be fetched on its own - a few hundred kilobytes - and then only
the members whose CRC-32 differs from the copy already installed need to be fetched at all.

Nothing here is specific to the game, and nothing is cached on disk: this is a file-like view of a remote
archive.  ``updater.py`` decides what to do with it.

Zip64 archives (over 4 GB, or over 65,535 members) are detected and refused rather than half-supported,
so the caller can fall back to downloading the whole file.  The port's releases are far below both limits.
"""
from __future__ import annotations

import logging
import stat
import struct
import urllib.error
import urllib.request
import zlib

log = logging.getLogger('platform.remotezip')

USER_AGENT = 'AudioDefence-Updater'
TIMEOUT = 30

#: the four signatures this reads
END_OF_CENTRAL_DIRECTORY = b'PK\x05\x06'
CENTRAL_FILE_HEADER = b'PK\x01\x02'
LOCAL_FILE_HEADER = b'PK\x03\x04'
ZIP64_END_LOCATOR = b'PK\x06\x07'

#: the end record is 22 bytes plus a comment of up to 65,535; read enough to hold one with a short comment
TAIL = 65536 + 22
STORED, DEFLATED = 0, 8


class RemoteZipError(Exception):
    """The archive cannot be read a piece at a time; download the whole thing instead."""


class Entry:
    __slots__ = ('name', 'crc', 'compressed_size', 'size', 'method', 'header_offset', 'mode')

    def __init__(self, name, crc, compressed_size, size, method, header_offset, mode=0):
        self.name = name
        self.crc = crc
        self.compressed_size = compressed_size
        self.size = size
        self.method = method
        self.header_offset = header_offset
        self.mode = mode                                  # the Unix mode a Mac archive keeps, else 0

    @property
    def is_link(self) -> bool:
        """A symbolic link, whose data is where it points: what a Mac app is full of."""
        return stat.S_ISLNK(self.mode)

    @property
    def is_dir(self) -> bool:
        return self.name.endswith('/')

    def __repr__(self) -> str:
        return '<Entry %s %d bytes crc %08x>' % (self.name, self.size, self.crc)


def _request(url: str, headers: dict):
    head = {'User-Agent': USER_AGENT}
    head.update(headers)
    return urllib.request.Request(url, headers=head)


def get_range(url: str, start: int, length: int) -> bytes:
    """The bytes [start, start+length).  A server that ignores the range gives us the whole file, which
    would be the very thing this exists to avoid, so that is an error rather than a slow success."""
    if length <= 0:
        return b''
    end = start + length - 1
    try:
        with urllib.request.urlopen(_request(url, {'Range': 'bytes=%d-%d' % (start, end)}),
                                    timeout=TIMEOUT) as response:
            if response.status != 206:
                raise RemoteZipError('the server sent the whole file instead of the range asked for')
            data = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 416:                               # asked past the end of the file
            raise RemoteZipError('asked for bytes the file does not have') from exc
        raise
    return data


def content_length(url: str) -> int:
    """How big the file is, learned from a one-byte range so a HEAD that redirects is not needed."""
    with urllib.request.urlopen(_request(url, {'Range': 'bytes=0-0'}), timeout=TIMEOUT) as response:
        if response.status == 206:
            total = response.headers.get('Content-Range', '').rsplit('/', 1)[-1]
            if total.isdigit():
                return int(total)
        length = response.headers.get('Content-Length')
        if response.status == 200 and length and length.isdigit():
            return int(length)
    raise RemoteZipError('the server did not say how big the file is')


class RemoteZip:
    """The central directory of a zip on a web server, and a way to pull one member out of it."""

    def __init__(self, url: str, size: int = None):
        self.url = url
        self.size = content_length(url) if size is None else size
        self.entries = self._read_central_directory()

    # --- the index -------------------------------------------------------------------------------
    def _read_central_directory(self) -> dict:
        tail_length = min(TAIL, self.size)
        tail = get_range(self.url, self.size - tail_length, tail_length)
        at = tail.rfind(END_OF_CENTRAL_DIRECTORY)
        if at < 0:
            raise RemoteZipError('no end-of-central-directory record: not a zip, or a zip64 one')
        (entry_count, directory_size, directory_offset) = struct.unpack('<HII', tail[at + 10:at + 20])
        if 0xFFFFFFFF in (directory_size, directory_offset) or entry_count == 0xFFFF \
                or tail.rfind(ZIP64_END_LOCATOR) >= 0:
            raise RemoteZipError('zip64 archives are not read a piece at a time')
        directory = get_range(self.url, directory_offset, directory_size)
        return self._parse_central_directory(directory, entry_count)

    @staticmethod
    def _parse_central_directory(directory: bytes, entry_count: int) -> dict:
        entries, at = {}, 0
        for _ in range(entry_count):
            if directory[at:at + 4] != CENTRAL_FILE_HEADER:
                raise RemoteZipError('the central directory is not laid out as expected')
            # from +10: method, (time, date), crc, compressed, uncompressed, name, extra and comment
            # lengths, (disk and internal attributes), external attributes, and where the local header
            # sits.  The external attributes hold a Unix mode, links and execute bits, when the archive
            # says it was made on Unix (3, in the high byte of +4)
            (method, crc, compressed_size, size, name_length, extra_length, comment_length,
             attributes, header_offset) = struct.unpack('<H4xIIIHHH4xII', directory[at + 10:at + 46])
            mode = attributes >> 16 if directory[at + 5] == 3 else 0
            name = directory[at + 46:at + 46 + name_length]
            try:
                name = name.decode('utf-8')
            except UnicodeDecodeError:
                name = name.decode('cp437')               # what a zip without the UTF-8 flag uses
            entries[name.replace('\\', '/')] = Entry(name.replace('\\', '/'), crc, compressed_size,
                                                     size, method, header_offset, mode)
            at += 46 + name_length + extra_length + comment_length
        return entries

    # --- one member ------------------------------------------------------------------------------
    def read(self, entry) -> bytes:
        """The member's bytes, fetched and decompressed on their own, with the CRC-32 checked."""
        if isinstance(entry, str):
            entry = self.entries[entry]
        if entry.is_dir:
            return b''
        # The local header repeats the name and may carry a different amount of extra data than the
        # central one, so its length is read rather than assumed.
        header = get_range(self.url, entry.header_offset, 30)
        if header[:4] != LOCAL_FILE_HEADER:
            raise RemoteZipError('%s does not start with a local file header' % entry.name)
        name_length, extra_length = struct.unpack('<HH', header[26:30])
        start = entry.header_offset + 30 + name_length + extra_length
        raw = get_range(self.url, start, entry.compressed_size)
        if entry.method == DEFLATED:
            data = zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw, entry.size)
        elif entry.method == STORED:
            data = raw
        else:
            raise RemoteZipError('%s uses compression method %d' % (entry.name, entry.method))
        if len(data) != entry.size:
            raise RemoteZipError('%s unpacked to %d bytes, not %d' % (entry.name, len(data), entry.size))
        if zlib.crc32(data) != entry.crc:
            raise RemoteZipError('%s did not survive the download intact' % entry.name)
        return data

    def files(self) -> dict:
        """The members that are files, by name; directories carry no data worth fetching."""
        return {name: entry for name, entry in self.entries.items() if not entry.is_dir}
