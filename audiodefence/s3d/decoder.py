"""Decoding of the bundle's .m4a/.mp3 sounds (the CASoundFile / ExtAudioFile role).

``csl::CASoundFile`` (0x1000e6154) opens files through ExtAudioFile with a 44.1 kHz float client format;
files opened for a spatialised sound get a single client channel (``a0[+0x60] = flag ? 1 : channels``).
The port decodes with PyAV and leaves resampling to OpenAL.  Stereo files used as spatialised sounds
are mixed to mono by averaging the channels (the CoreAudio converter's mixdown).
"""
from __future__ import annotations

import os
import threading

import numpy as np

_lock = threading.Lock()
_cache: dict[str, tuple[np.ndarray, int]] = {}
_pending: dict[str, threading.Event] = {}       # files being decoded by the background thread
_queue: list[str] = []
_wake = threading.Condition(_lock)
_worker: threading.Thread | None = None
_callbacks: dict[str, list] = {}                 # decode_async callbacks, called by the background thread


def decode(path: str) -> tuple[np.ndarray, int]:
    """(samples float32 [frames, channels], sample_rate); cached per file."""
    with _lock:
        hit = _cache.get(path)
        event = _pending.get(path)
        if hit is None and event is not None and path in _queue and path not in _callbacks:
            _queue.remove(path)                 # not started yet: decode it here, right now
            _pending.pop(path, None)
            event.set()
            event = None
    if hit is not None:
        return hit
    if event is not None:                       # the background thread is decoding it: wait for that
        event.wait()
        with _lock:
            hit = _cache.get(path)
        if hit is not None:
            return hit
    return _decode_now(path)


def prewarm(paths) -> None:
    """Decode files ahead of their first play, on a background thread.

    PORT: the original loads a sound off the main thread (-[S3DSound activate:] 0x1001047fc dispatches the
    CASoundFile creation to the engine queue); the port decodes in S3DSound.activate on the main thread, so
    the files of a playlist are decoded here as soon as the playlist is activated.  Nothing the game sees
    changes: a file that is not ready yet is still decoded (or waited for) when it is needed.
    """
    global _worker
    with _lock:
        added = False
        for path in paths:
            if path in _cache or path in _pending:
                continue
            _pending[path] = threading.Event()
            _queue.append(path)
            added = True
        if not added:
            return
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name='sound-prewarm', daemon=True)
            _worker.start()
        _wake.notify()


def is_cached(path: str) -> bool:
    with _lock:
        return path in _cache


def decode_async(path: str, done) -> None:
    """Decode on the background thread (ahead of queued prewarm work) and call done() from that thread."""
    global _worker
    with _lock:
        if path in _cache:
            ready = True
        else:
            ready = False
            _callbacks.setdefault(path, []).append(done)
            if path not in _pending:
                _pending[path] = threading.Event()
                _queue.insert(0, path)
            elif path in _queue:
                _queue.remove(path)
                _queue.insert(0, path)
            if _worker is None or not _worker.is_alive():
                _worker = threading.Thread(target=_work, name='sound-prewarm', daemon=True)
                _worker.start()
            _wake.notify()
    if ready:
        done()


def _work() -> None:
    while True:
        with _lock:
            while not _queue:
                _wake.wait()
            path = _queue.pop(0)
        try:
            _decode_now(path)
        except Exception:                        # a bad file is reported again when it is played
            pass
        finally:
            with _lock:
                event = _pending.pop(path, None)
                callbacks = _callbacks.pop(path, [])
            if event is not None:
                event.set()
            for done in callbacks:
                done()


def _decode_now(path: str) -> tuple[np.ndarray, int]:
    import av
    chunks = []
    rate = 44100
    channels = 1
    with av.open(path) as container:
        stream = container.streams.audio[0]
        rate = stream.codec_context.sample_rate or rate
        channels = stream.codec_context.channels or channels
        for frame in container.decode(stream):
            arr = frame.to_ndarray()
            if arr.dtype != np.float32:
                if np.issubdtype(arr.dtype, np.integer):
                    arr = arr.astype(np.float32) / float(np.iinfo(arr.dtype).max)
                else:
                    arr = arr.astype(np.float32)
            if frame.format.is_planar:
                arr = arr.T                         # (channels, n) -> (n, channels)
            else:
                arr = arr.reshape(-1, channels)
            chunks.append(arr)
    data = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, channels), np.float32)
    data = np.ascontiguousarray(data, dtype=np.float32)
    with _lock:
        hit = _cache.setdefault(path, (data, rate))
    return hit


def lead_in(path: str, floor: float = 0.002, most: float = 0.25) -> float:
    """PORT ADDITION: how long a file is silent before it starts, in seconds.

    Some of the game's own recordings begin with a moment of nothing - the Machine Gun's shot has 133
    milliseconds of it, the Grenade Launcher's 109 - which is heard as a gap between the trigger and the
    bang.  Only a file the decoder already holds is measured; nothing is decoded here, since this is asked
    on the way to playing a sound.  `most` is a cap: a file that is quiet for longer than that is left
    alone, in case what looks like silence is the sound itself.
    """
    with _lock:
        hit = _cache.get(path)
    if hit is None:
        return 0.0
    data, rate = hit
    if not rate or not len(data):
        return 0.0
    mono = data.mean(axis=1) if data.ndim > 1 else data
    loud = np.abs(mono) > floor
    if not loud.any():
        return 0.0
    return min(float(np.argmax(loud)) / float(rate), most)


def forget(path: str) -> None:
    with _lock:
        _cache.pop(path, None)


def exists(path: str) -> bool:
    return os.path.isfile(path)
