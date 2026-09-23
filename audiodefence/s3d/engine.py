"""S3D ("Papa Engine") port: S3DEngine, S3DPlayList, S3DSound and S3DEngineDispatcher on OpenAL Soft.

The original runs the engine on two GCD serial queues and a CoreAudio render thread.  The port is
single-threaded: work the original dispatches asynchronously is queued and run by ``S3DEngine.pump``
(called by the main loop), and the dispatcher tick runs every 10 ms of wall time like
``-[S3DEngineDispatcher dispatch_pump]`` (dispatch_after 9,999,999 ns).  Rendering (HRTF, mixing,
HRTF) is OpenAL Soft's, the reverb is the original Freeverb (reverb.py); everything the S3D objects decide
is ported from the methods quoted below.

Signal path of the original (docs/GAME_STRUCTURE.md section 17) and its OpenAL mapping:

    spatialised: file(mono) -> DistanceSimulator (gain min(1/d, maxSpatialGain), air low-pass when d > 10)
                 -> BinauralPanner (IRCAM horizontal HRTF, front gain 1..1.5) -> gainControl
                 => mono buffer, source-relative position, OpenAL HRTF (assets/hrtf), AL_GAIN = product
    plain mono:  file -> csl::Panner (pan 0: 0.5 per channel) -> gainControl
                 => stereo buffer holding 0.5 * sample in both channels, AL_DIRECT_CHANNELS_SOFT
    plain stereo: file -> gainControl        => stereo buffer, AL_DIRECT_CHANNELS_SOFT
    sendToReverb: gainControl -> FanOut -> dryMixer (dryGain) / wetMixer (wetGain) -> Stereoverb
                 => the source plays on the reverb bus device; its render + Stereoverb reach the output
                    through the bus's callback source (reverb.py)
    masterMixer scale = masterGain         => listener AL_GAIN
"""
from __future__ import annotations

import ctypes
import logging
import math
import os
import time
from collections import OrderedDict

import numpy as np

from .. import paths
from ..platform import crand
from . import decoder, model as s3dmodel
from . import openal as oal
from .device import Device
from .reverb import ReverbBus

log = logging.getLogger('s3d')

TWO_PI = 6.28318548                # the float constant the engine compares against
PI_F = 3.14159274
DISPATCH_INTERVAL = 0.009999999    # dispatch_time(0, 0x98967f)


# =============================================================================================== engine
class S3DEngine:
    _instance: 'S3DEngine | None' = None
    playlist_meta_path = 'meta'     # +[S3DEngine setPlayListMetaPath:]
    product_name = ''
    master_spatialised_gain = 1.0   # g_1004291b4

    @classmethod
    def engine(cls) -> 'S3DEngine':
        if cls._instance is None:
            cls._instance = S3DEngine()
        return cls._instance

    # -[S3DEngine init] 0x1000faa60
    def __init__(self, device: Device | None = None):
        self.device = device or Device()
        self.al = oal.ContextAL(self.device.al, self.device.context)
        self.al.alDistanceModel(0)                       # AL_NONE: distance gain is computed here
        self.trace_level = 0
        self.head_position = (0.0, 0.0, 0.0)
        self.head_orientation = 0.0
        self.max_spatial_gain = 100.0
        self.distance_scale = 1.0                        # init block_invoke sets 1
        self.master_gain = 1.0
        self._queue: list = []
        self._buffers: dict[tuple, list] = {}            # (path, variant, on bus) -> [al buffer, refcount]
        self._extra_voices: list[int] = []               # PORT ADDITION: one-shot copies (see play_copy_of)
        self.dispatcher = S3DEngineDispatcher(self)
        self._models = None
        self.play_list_cache: dict[str, S3DPlayList] = {}
        # masterMixer <- dryMixer, masterMixer <- Stereoverb(wetMixer); Stereoverb 2.2 / 2 / wet 0 / dry 0
        self.bus = ReverbBus(self.device)
        self.bus_al = oal.ContextAL(self.device.al, self.bus.context) if self.bus.available else None
        self.set_reverb_room_size(1.5)
        self.set_reverb_volume(1.0)
        self.set_reverb_dampening(50.0)
        self.set_master_gain(1.0)

    # --- queues ----------------------------------------------------------------------------------
    def dispatch(self, fn) -> None:
        """-[S3DEngine dispatch:] - run later on the engine queue (here: the next pump)."""
        self._queue.append(fn)

    def pump(self, now: float | None = None) -> None:
        now = time.perf_counter() if now is None else now
        self._drain()
        self.dispatcher.maybe_fire(now)
        self._drain()
        self._reap_extra_voices()

    # --- one-shot copies (PORT ADDITION) ----------------------------------------------------------
    def play_copy_of(self, sound) -> bool:
        """Play a loaded sound again on a second source, so it can overlap itself.

        An S3DSound owns one OpenAL source, so playing it again restarts it - audible as a cut when a
        weapon fires faster than its own fire sounds last.  The original has the same limit and waits on
        the main thread for a free sound instead (see -[ADWeapon playSingleShootSound]).  Here the extra
        shot gets a source of its own, bound to the same buffer, and is reaped when it finishes."""
        buffer = getattr(sound, '_buffer', 0)
        if not buffer or getattr(sound, '_on_bus', False) or len(self._extra_voices) > 32:
            return False
        try:
            src = self.al.gen('alGenSources')
            self.al.alSourcei(src, oal.AL_BUFFER, buffer)
            self.al.alSourcei(src, oal.AL_SOURCE_RELATIVE, 1)
            self.al.alSource3f(src, oal.AL_POSITION, 0.0, 0.0, 0.0)
            self.al.alSourcei(src, oal.AL_DIRECT_CHANNELS_SOFT, 1)
            self.al.alSourcei(src, oal.AL_SOURCE_SPATIALIZE_SOFT, 0)
            # the same gain the sound itself would use: dry sounds are gain * fade_gain * volume (_apply_gain)
            gain = float(sound.gain) * float(sound.fade_gain) * float(getattr(sound, 'volume', 1.0))
            self.al.alSourcef(src, oal.AL_GAIN, max(0.0, gain))
            skip = float(getattr(sound, 'skip_to', 0.0))  # PORT ADDITION: and it starts where the sound does
            if skip > 0.0 and float(getattr(sound, 'duration_s', 0.0)) > skip:
                self.al.alSourcef(src, oal.AL_SEC_OFFSET, skip)
            self.al.alSourcePlay(src)
        except Exception:
            log.exception('could not play a copy of %s', getattr(sound, 'path', '?'))
            return False
        self._extra_voices.append(src)
        return True

    def _reap_extra_voices(self) -> None:
        if not self._extra_voices:
            return
        state = ctypes.c_int(0)
        for src in list(self._extra_voices):
            self.al.alGetSourcei(src, oal.AL_SOURCE_STATE, ctypes.byref(state))
            if state.value != oal.AL_PLAYING:
                self.al.alSourceStop(src)
                self.al.alSourcei(src, oal.AL_BUFFER, 0)
                self.al.delete('alDeleteSources', src)
                self._extra_voices.remove(src)

    def _drain(self) -> None:
        guard = 0
        while self._queue and guard < 10000:
            batch, self._queue = self._queue, []
            for fn in batch:
                try:
                    fn()
                except Exception:                        # a failing callback must not stop the engine
                    log.exception('S3D queued action failed')
            guard += 1

    # --- head ------------------------------------------------------------------------------------
    def set_head_position(self, pos) -> None:            # 0x1000fa340
        x, y, z = (float(v) for v in pos)
        if any(math.isinf(v) and v < 0 for v in (x, y, z)) or any(math.isnan(v) for v in (x, y, z)):
            return
        if (x, y, z) != self.head_position:
            self.head_position = (x, y, z)
            self.dispatcher.needs_position_update = True

    def set_distance_scale(self, scale: float) -> None:  # 0x1000fa460
        self.distance_scale = float(scale)
        self.dispatcher.needs_position_update = True

    def set_head_orientation(self, value: float) -> None:  # 0x1000fa4d4
        value = float(np.float32(value))
        if self.head_orientation == value:
            return
        while value > TWO_PI:
            value -= TWO_PI
        while value < 0.0:
            value += TWO_PI
        self.head_orientation = value
        self.dispatcher.needs_position_update = True

    def set_max_spatial_gain(self, gain: float) -> None:
        self.max_spatial_gain = float(gain)

    def normalize_to_head_position(self, planar):        # 0x1000fa5a8
        hx, hy, hz = self.head_position
        rx, ry, rz = planar[0] - hx, planar[1] - hy, planar[2] - hz
        if math.sqrt(rx * rx + ry * ry + rz * rz) < 0.01:
            ry = 0.05
        h = -self.head_orientation
        s, c = math.sin(h), math.cos(h)
        x = (rx * c - ry * s) * self.distance_scale
        y = -((ry * c + rx * s) * self.distance_scale)
        return x, y, rz

    # --- gains / reverb --------------------------------------------------------------------------
    def set_master_gain(self, gain: float) -> None:      # 0x1000fa76c
        self.master_gain = float(gain)
        self.al.alListenerf(oal.AL_GAIN, max(0.0, self.master_gain))

    @classmethod
    def set_master_spatialised_gain(cls, gain: float) -> None:
        cls.master_spatialised_gain = float(gain)

    def set_reverb_room_size(self, size: float) -> None:     # 0x1000fc79c
        size = 2.3 if size > 2.3 else size
        if self.bus.available:
            self.bus.reverb.set_room_size(0.01 if size < 0.01 else size)

    def set_reverb_dampening(self, value: float) -> None:    # 0x1000fc818
        value = 0.0 if value < 0.0 else value
        if self.bus.available:
            self.bus.reverb.set_dampening(100.0 if value > 100.0 else value)

    def set_reverb_volume(self, value: float) -> None:       # 0x1000fc890
        value = 0.0 if value < 0.0 else value
        if self.bus.available:
            self.bus.reverb.set_wet_level(8.0 if value > 8.0 else value)

    # --- playlists -------------------------------------------------------------------------------
    def _load_models(self) -> None:
        if self._models is None:
            self._models = s3dmodel.load_all()
            for name, m in self._models.items():
                self.play_list_cache[name] = S3DPlayList(self, m)

    def play_list_with_name(self, name: str) -> 'S3DPlayList | None':   # 0x1000fc050
        self._load_models()
        pl = self.play_list_cache.get(name)
        if pl is None:
            log.info('playlist for %s not found, returning nil.', name)
        return pl

    def stop_all(self) -> None:                                         # 0x1000fc628
        self._load_models()
        for pl in list(self.play_list_cache.values()):
            pl.stop_all()

    # --- OpenAL buffers --------------------------------------------------------------------------
    def acquire_buffer(self, path: str, variant: str, on_bus: bool = False) -> tuple[int, float, int]:
        """Returns (al buffer, duration seconds, file channel count).  Buffers belong to a device: sounds on
        the reverb bus get their own copy."""
        al = self.bus_al if on_bus else self.al
        key = (path, variant, on_bus)
        entry = self._buffers.get(key)
        data, rate = decoder.decode(path)
        channels = data.shape[1]
        duration = data.shape[0] / float(rate) if rate else 0.0
        if entry is None:
            if variant == 'mono':
                pcm = data.mean(axis=1) if channels > 1 else data[:, 0]
                fmt = oal.AL_FORMAT_MONO_FLOAT32
            elif variant == 'center':
                mono = data[:, 0] * 0.5
                pcm = np.repeat(mono, 2)
                fmt = oal.AL_FORMAT_STEREO_FLOAT32
            else:
                pcm = data[:, :2].reshape(-1)
                fmt = oal.AL_FORMAT_STEREO_FLOAT32
            pcm = np.ascontiguousarray(pcm, dtype=np.float32)
            buf = al.gen('alGenBuffers')
            al.alBufferData(buf, fmt, pcm.ctypes.data, pcm.nbytes, int(rate))
            al.check(f'alBufferData {os.path.basename(path)}')
            entry = [buf, 0]
            self._buffers[key] = entry
        entry[1] += 1
        return entry[0], duration, channels

    def release_buffer(self, path: str, variant: str, on_bus: bool = False) -> None:
        key = (path, variant, on_bus)
        entry = self._buffers.get(key)
        if entry is None:
            return
        entry[1] -= 1
        if entry[1] <= 0:
            al = self.bus_al if on_bus else self.al
            al.delete('alDeleteBuffers', entry[0])
            al.alGetError()
            del self._buffers[key]

    def shutdown(self) -> None:
        if self.device is None:                           # already down: closing OpenAL twice is undefined
            return
        for src in self._extra_voices:
            self.al.alSourceStop(src)
            self.al.delete('alDeleteSources', src)
        self._extra_voices.clear()
        self.stop_all()
        self.bus.close()
        self.device.close()
        self.device = None
        S3DEngine._instance = None


# =========================================================================================== dispatcher
class S3DEngineDispatcher:
    """Tracks playing sounds, delivers end-of-file / progress events to monitors (0x100108a4c)."""

    def __init__(self, engine: S3DEngine):
        self.engine = engine
        self.agents: 'OrderedDict[S3DSound, None]' = OrderedDict()
        self.play_lists: set = set()
        self.monitors: dict = {}
        self.needs_position_update = False
        self._next = 0.0

    def start_tracking(self, sound: 'S3DSound') -> None:
        self.agents[sound] = None

    def stop_tracking(self, sound: 'S3DSound') -> None:     # 0x1001084e4
        if sound in self.agents:
            del self.agents[sound]
            sound.stop()

    def add_monitor(self, block, sound: 'S3DSound') -> None:  # 0x100109c7c: replaces existing monitors
        self.monitors[sound] = [block]

    def maybe_fire(self, now: float) -> None:
        if now < self._next:
            return
        self._next = now + DISPATCH_INTERVAL
        self.fire()

    def fire(self) -> None:
        update = self.needs_position_update
        self.needs_position_update = False
        for sound in list(self.agents):
            if not sound.loaded:
                continue
            if update or sound.planar_needs_updating:
                sound.update_position()
            for kind, elapsed in sound.poll_events():
                blocks = self.monitors.get(sound)
                if blocks:
                    for block in list(blocks):
                        stop = block(sound, elapsed, sound.duration)
                        if stop:
                            self.monitors.pop(sound, None)
                            break
                if kind == 2 and not sound.looping_flag and sound in self.agents:
                    gen = sound.generation
                    self.engine.dispatch(lambda s=sound, g=gen: self._end_stop(s, g))

    def _end_stop(self, sound: 'S3DSound', gen: int) -> None:
        """dispatched_fired_block_invoke_3: lingering + stopTracking -> [sound stop]."""
        if sound.generation == gen and sound in self.agents:
            self.stop_tracking(sound)


# ============================================================================================= playlist
class S3DPlayList:
    def __init__(self, engine: S3DEngine, model: s3dmodel.PlayListModel):
        self.engine = engine
        self.model = model
        self.name = model.xid.split('.')[0]
        self.active = False
        self.activating = False
        self.agent_cache: 'OrderedDict[str, S3DSound | None]' = OrderedDict()
        self.cycle_index = 0

    def __repr__(self) -> str:
        return f'<S3DPlayList {self.name}>'

    @property
    def range_length(self) -> int:
        return len(self.model.sounds)

    def each(self, block) -> None:                                  # 0x1000ffeb8
        for entry in self.model.sounds:
            key = entry.key
            if key not in self.agent_cache:
                self.agent_cache[key] = S3DSound.agent_with_entry(self.engine, entry)
            agent = self.agent_cache[key]
            if agent is None:            # the original would throw on a nil agent; such playlists are unused
                continue
            if block(agent):
                return

    def sound(self, key: str) -> 'S3DSound | None':                 # -[S3DPlayList S3DSound:] 0x100100304
        self.each(lambda s: False)
        for agent in self.agent_cache.values():
            if agent is not None and agent.key == key:
                return agent
        log.info('sound %s not found in playlist %s', key, self.name)
        return None

    def sounds_matching(self, predicate) -> list:
        found = []
        self.each(lambda s: (found.append(s) if predicate(s.key) else None) and False)
        return found

    def any_sound_matching(self, predicate) -> 'S3DSound | None':   # 0x1000fd3f4
        matches = self.sounds_matching(predicate)
        count = len(matches)
        if count == 0:
            return None
        r = crand.arc4random()
        index = r % max(1, self.range_length)
        if index >= count:
            index %= count
        return matches[index]

    def any_sound(self):
        return self.any_sound_matching(lambda k: True)

    def any_sound_with_prefix(self, prefix: str):                   # anySoundWihPrefix:
        return self.any_sound_matching(lambda k: k.startswith(prefix))

    def any_sound_with_suffix(self, suffix: str):                   # anySoundWihSuffix:
        return self.any_sound_matching(lambda k: k.endswith(suffix))

    def any_sound_containing(self, text: str):                      # anySoundContaining:
        return self.any_sound_matching(lambda k: text in k)

    def activate(self, completion=None) -> None:                    # 0x1000fe9c0
        if completion is None:
            completion = _NOOP_COMPLETION                            # -[S3DPlayList activate] passes a block
        self._activate(completion)

    def activate_nil(self) -> None:
        self._activate(None)

    def _activate(self, completion) -> None:
        if self.activating:
            return
        self.activating = True

        def block():
            if self.active:
                # DIVERGENCE: -[S3DPlayList activate:]_block_invoke 0x1000fed40 clears `activating` only on
                # the no-completion path (loc_1000ff1c0, the store at 0x0ff1c8).  Asked to activate a
                # playlist that is already active *with* a completion, it dispatches the completion and
                # branches to the epilogue at loc_1000ff198 without clearing the flag - so `activating`
                # stays 1 for good, and every later activate: returns at the guard in 0x1000fe9c0 with the
                # completion never run.  For `main_menu` that is silence until the game is restarted, which
                # is what it sounds like: the music stops and no menu or replay brings it back.  The flag is
                # cleared on both paths here.  Nothing else changes: the completion still runs either way.
                self.activating = False
                if completion is not None:
                    self.engine.dispatch(lambda: completion(self))
                return
            self.active = True
            self.engine.dispatcher.play_lists.add(self)
            self.each(lambda s: (s.activate() if s.preload else None) and False)
            decoder.prewarm([a.path for a in self.agent_cache.values() if a is not None and not a.loaded])
            if completion is None:
                self.activating = False
            else:
                def finish():
                    completion(self)
                    self.activating = False
                self.engine.dispatch(finish)
        self.engine.dispatch(block)

    def deactivate(self, completion=None) -> None:                  # 0x1000fe140
        if not self.active:
            return
        self.active = False
        self.each(lambda s: s.deactivate() and False)
        for twin in self._copies():                                 # PORT ADDITION: see S3DSound.copy
            twin.deactivate()
        if completion is not None:
            self.engine.dispatch(lambda: completion(self))

    def stop_all(self) -> None:                                     # 0x1001005cc
        self.each(lambda s: (s.stop() if s.playing else None) and False)
        for twin in self._copies():                                 # PORT ADDITION: see S3DSound.copy
            if twin.playing:
                twin.stop()

    def _copies(self) -> list:
        return [twin for agent in self.agent_cache.values() if agent is not None for twin in agent.copies]


def _NOOP_COMPLETION(_playlist) -> None:
    return None


# ================================================================================================ sound
class S3DSound:
    @staticmethod
    def agent_with_entry(engine: S3DEngine, entry: s3dmodel.SoundEntry) -> 'S3DSound | None':
        path = os.path.join(paths.BUNDLE, entry.path, f'{entry.name}.{entry.extension}')
        if not os.path.isfile(path):          # URLForResource returns nil -> initWithURL: nil -> nil
            return None
        snd = S3DSound(engine, path)
        snd.spatialized = entry.spatialized
        snd.preload = entry.preload
        snd.unload_on_stop = entry.unloadonstop
        snd.stream = entry.stream
        return snd

    def __init__(self, engine: S3DEngine, path: str):                # -[S3DSound initWithURL:] 0x100104e00
        self.engine = engine
        self.path = path
        self.key = os.path.splitext(os.path.basename(path))[0]
        self.planar = (0.0, 0.0, 0.0)
        self.planar_needs_updating = False
        self.fade_gain = 1.0
        self.gain = 1.0
        self.wet_gain = 0.0
        self.dry_gain = 1.0
        self.send_to_reverb = False
        self.auto_reverb_mix = False
        self.min_reverb_distance = 10.0
        self.max_reverb_distance = 200.0
        self.min_wet_send = 0.2
        self.max_wet_send = 1.0
        self.user_value = 0
        self.looping = False           # ivar looping (requested)
        self.looping_flag = False      # soundFile[+0x191]
        self.active = False
        self.stopping = False
        self.restart = False
        self.restarting = False
        self.stream = False
        self.spatialized = False
        self.preload = False
        self.unload_on_stop = False
        self.setup_done = False
        self.play_when_loaded = False
        self.stored_fade = 0.0
        self.play_rate = 0.0
        self.pan = 0.0
        # port state
        self.loaded = False
        self.duration_s = 0.0
        self.channels = 0
        self._variant = None
        self._buffer = 0
        self._loaded_variant = None
        self._source = 0
        self._direct_filter = 0
        self._on_bus = False           # the source and its buffer live on the reverb bus device
        self._spatial = False
        self._last_offset = 0.0
        #: PORT ADDITION: seconds to start into the file, for a recording that opens with silence
        self.skip_to = 0.0
        self._paused = False
        self.generation = 0
        self._loading = False
        self._load_generation = 0
        self._load_waiters: list = []
        self.copies: list = []         # PORT ADDITION: see copy()
        self.volume = 1.0              # PORT ADDITION: see set_volume()

    def __repr__(self) -> str:
        return f'<S3DSound {self.key}>'

    def copy(self) -> 'S3DSound':
        """PORT ADDITION: a second, independent sound for the same file.

        A playlist holds one S3DSound per file (-[S3DPlayList each:] 0x1000ffeb8 caches the agent by key),
        and every enemy of a type draws from that type's playlist, so two zombies of one type share a
        sound whenever they pick the same file.  The copy has its own source, position, gain, loop and
        end callback, on the same buffer (buffers are shared by file, see acquire_buffer).  It is loaded
        at once if this one is, from the decoder's cache, so its duration is right before it first plays.
        The playlist that owns this sound stops and unloads the copies along with it."""
        twin = S3DSound(self.engine, self.path)
        twin.skip_to = self.skip_to                                 # PORT ADDITION: and starts where it does
        twin.spatialized = self.spatialized
        twin.preload = self.preload
        twin.unload_on_stop = self.unload_on_stop
        twin.stream = self.stream
        self.copies.append(twin)
        if self.loaded:
            twin.activate()
        return twin

    @property
    def al(self):
        return self.engine.bus_al if self._on_bus else self.engine.al

    # --- queries ---------------------------------------------------------------------------------
    @property
    def duration(self) -> float:                                    # 0x1001009fc
        return self.duration_s if self.loaded else 0.0

    @property
    def playing(self) -> bool:                                      # 0x1001009a8
        if not self._source:
            return False
        v = ctypes.c_int(0)
        self.al.alGetSourcei(self._source, oal.AL_SOURCE_STATE, ctypes.byref(v))
        return v.value == oal.AL_PLAYING

    def elapsed_time(self) -> float:
        """Seconds played so far (port helper: AL_SEC_OFFSET of the source, 0 without one)."""
        if not self._source:
            return 0.0
        off = ctypes.c_float(0.0)
        self.al.alGetSourcef(self._source, oal.AL_SEC_OFFSET, ctypes.byref(off))
        return float(off.value)

    # --- loading ---------------------------------------------------------------------------------
    def _wanted_variant(self) -> str:
        if self.spatialized:
            return 'mono'
        return 'stereo' if self.channels == 2 else 'center'

    def activate(self, completion=None) -> None:                    # 0x1001047fc
        if self.loaded:
            if completion is not None:
                completion()
            return
        if self.stream and not decoder.is_cached(self.path):
            # the original opens every file on the engine queue (activate:_block_invoke 0x1001049a8) and a
            # streamed one is read by csl::Fifo's own thread; the port decodes streamed sounds (music and
            # ambience beds, the long files) in the background too, so the game does not wait for them
            if completion is not None:
                self._load_waiters.append(completion)
            if not self._loading:
                self._loading = True
                generation = self._load_generation
                decoder.decode_async(self.path, lambda: self.engine.dispatch(
                    lambda: self._finish_async_load(generation)))
            return
        try:
            data, rate = decoder.decode(self.path)
        except Exception:
            log.exception('cannot open sound file %s', self.path)
            return
        self._opened(data, rate, completion)

    def _finish_async_load(self, generation: int) -> None:
        if generation != self._load_generation:                     # deactivated meanwhile
            return
        self._loading = False
        waiters, self._load_waiters = self._load_waiters, []
        try:
            data, rate = decoder.decode(self.path)
        except Exception:
            log.exception('cannot open sound file %s', self.path)
            return
        self._opened(data, rate, None)
        for completion in waiters:
            self.engine.dispatch(completion)

    def _opened(self, data, rate, completion) -> None:
        self.channels = data.shape[1]
        self.duration_s = data.shape[0] / float(rate)
        self.loaded = True
        self._open_variant = 'mono' if self.spatialized else None   # client format fixed at open time
        if completion is not None:
            self.engine.dispatch(completion)
        if self.play_when_loaded:                                   # soundFileOpen block 0x10010478c
            self.play_when_loaded = False
            self._setup_either()
            self._setup_complete(self.stored_fade, self.looping)

    def deactivate(self) -> None:                                   # 0x100102dc8
        if self._loading:                                           # a background load is dropped
            self._loading = False
            self._load_generation += 1
            self._load_waiters = []
        self.engine.dispatcher.agents.pop(self, None)
        self.stop()
        self._cleanup()
        if self.loaded:
            self._release_buffer()
            self.loaded = False
        self.active = False
        self.stopping = False
        if self.restart:
            self.engine.dispatch(self._restart_play)

    # --- properties ------------------------------------------------------------------------------
    def set_spatialized(self, flag: bool) -> None:                  # 0x100101410
        self.spatialized = bool(flag)

    def set_stream(self, flag: bool) -> None:
        self.stream = bool(flag)

    def set_send_to_reverb(self, flag: bool) -> None:
        self.send_to_reverb = bool(flag)

    def set_gain(self, gain: float) -> None:                        # 0x100100b34
        self.gain = float(gain)
        if self._source:
            self._apply_gain()

    def set_volume(self, volume: float) -> None:
        """PORT ADDITION: a player's volume, on top of the gain the game sets.  It is kept apart from `gain`
        because the game does arithmetic on that - the menu music fades out by taking 0.01 off it every
        0.05 s until it reaches 0 - and scaling it there would change how long the fade lasts."""
        self.volume = float(volume)
        if self._source:
            self._apply_gain()

    def set_wet_gain(self, gain: float) -> None:                    # 0x100106d10
        self.wet_gain = float(gain)
        self._check_bus_gains()

    def set_dry_gain(self, gain: float) -> None:                    # 0x100106ed4
        self.dry_gain = float(gain)
        self._check_bus_gains()

    def _check_bus_gains(self) -> None:
        # the bus carries one signal for both mixers: the game only ever uses dryGain 1 and wetGain 1
        if self.send_to_reverb and (self.wet_gain != 1.0 or self.dry_gain != 1.0):
            log.warning('%s: dryGain %.3f / wetGain %.3f are not supported on the reverb bus (both play at 1)',
                        self.key, self.dry_gain, self.wet_gain)

    def set_planar(self, planar) -> None:                           # 0x100101394
        self.planar = (float(planar[0]), float(planar[1]), float(planar[2]) if len(planar) > 2 else 0.0)
        self.planar_needs_updating = True
        if self._source and self._spatial:
            self.update_position()

    def set_play_rate(self, rate: float) -> None:
        self.play_rate = rate

    # --- playback --------------------------------------------------------------------------------
    def play(self, loop: bool = False, fadein: float = 0.0) -> None:  # -[S3DSound play:fadein:] 0x100105eb8
        if self.active:
            self.restart = True
            self.stop()
            return
        if self.stopping:
            self.restart = True
            return
        self.active = True
        self.looping = bool(loop)
        if self.setup_done or self.loaded:
            if not self.setup_done:
                self._setup_either()
            self._setup_complete(fadein, self.looping)
        else:
            self.stored_fade = fadein
            self.play_when_loaded = True
            self.activate()

    def _setup_either(self) -> None:                                # 0x100105da4
        self._build_source()

    def _setup_complete(self, fade: float, loop: bool) -> None:     # 0x100105a54
        self.setup_done = True
        if not self._source:
            self._build_source()
        self._prepare_for_play(fade)
        self._play_as_is(loop)
        self.looping_flag = loop
        self.al.alSourcei(self._source, oal.AL_LOOPING, 1 if loop else 0)
        self.restarting = False

    def _prepare_for_play(self, fade: float) -> None:               # 0x100106208
        if fade > 0.0:
            step = math.pow(100.0, 1.0 / (fade / 0.01))
            self.fade_gain = 0.01

            def monitor(sound, elapsed, duration, step=step):
                stop = not (elapsed < duration)
                if sound.fade_gain > 1.0:
                    sound.fade_gain = 1.0
                else:
                    sound.set_gain(sound.gain)
                    sound.fade_gain = step * sound.fade_gain
                return stop
            self.add_3d_sound_monitor(monitor)
        else:
            self.fade_gain = 1.0

    def _play_as_is(self, loop: bool) -> None:                      # 0x100105740
        self.play_rate = 1.0
        self.looping_flag = loop
        self.al.alSourcei(self._source, oal.AL_LOOPING, 1 if loop else 0)
        self.al.alSourceRewind(self._source)
        if self.skip_to > 0.0 and self.duration_s > self.skip_to:   # PORT ADDITION: start where it starts
            self.al.alSourcef(self._source, oal.AL_SEC_OFFSET, self.skip_to)
        self._apply_gain()
        if self._spatial:
            self.update_position()
        self.al.alSourcePlay(self._source)
        self._last_offset = 0.0
        self._paused = False
        self.generation += 1
        self.engine.dispatcher.start_tracking(self)

    def stop(self) -> None:                                         # 0x10010690c
        if self.active:
            if self.stopping:
                return
            self.stopping = True
            self._stop_internal()
        elif self.restart:
            self.stopping = True
            self.engine.dispatch(self._stop_internal)

    def _stop_internal(self) -> None:                               # 0x1001067f8
        self.stopping = False
        self.play_rate = 0.0
        self.looping_flag = False
        self._paused = False                                        # a stopped sound is not paused
        if self._source:
            self.al.alSourceStop(self._source)
        self._cleanup_graph()
        self.setup_done = False

    def _cleanup_graph(self) -> None:                               # -[S3DSound cleanup] 0x1001014c4
        if not self.loaded or self.restarting:
            return
        self.play_rate = 0.0
        self.engine.dispatcher.agents.pop(self, None)
        self._cleanup()
        if self.unload_on_stop:
            self.active = False
            self.stopping = False
            self.deactivate()
            return
        self.active = False
        self.stopping = False
        if self.restart:
            self.engine.dispatch(self._restart_play)

    def _restart_play(self) -> None:
        """cleanup block: [self play] (loop NO), restart = NO, restarting = YES."""
        self.play()
        self.restart = False
        self.restarting = True
        if self.setup_done:
            self.restarting = False

    def pause(self) -> None:                                        # 0x100105680
        self.play_rate = 0.0
        if self._source:
            self.al.alSourcePause(self._source)
            self._paused = True

    def resume(self) -> None:                                       # 0x100105694
        # The original's resume is one line - [self setPlayRate:1] - because its engine pauses by rate, so
        # a sound that was stopped meanwhile cannot come back.  The port pauses the OpenAL source, so it
        # only resumes a source that is really paused: alSourcePlay on a stopped one would start it again
        # from the beginning (an enemy's ambience returning over the menus after the game ended).
        self.play_rate = 1.0
        if self._source and self._paused and self._source_state() == oal.AL_PAUSED:
            self.al.alSourcePlay(self._source)
        self._paused = False

    def _source_state(self) -> int:
        state = ctypes.c_int(0)
        self.al.alGetSourcei(self._source, oal.AL_SOURCE_STATE, ctypes.byref(state))
        return state.value

    def fade_out(self, duration: float = 0.3) -> None:              # 0x10010650c: only 0 stops
        def block():
            if duration <= 0.0:
                self._stop_internal()
        self.engine.dispatch(block)

    # --- monitors --------------------------------------------------------------------------------
    def add_3d_sound_monitor(self, block) -> None:                  # 0x100106b44
        """block(sound, elapsed, duration) -> True to stop monitoring."""
        self.engine.dispatcher.add_monitor(block, self)

    def add_3d_sound_end_callback(self, callback) -> None:          # 0x100106be0
        def monitor(sound, elapsed, duration):
            if not (elapsed < duration):
                callback(sound)
            return False
        self.add_3d_sound_monitor(monitor)

    def poll_events(self):
        """End-of-file (2) and progress (3) events for the dispatcher tick."""
        if not self._source or self._paused:
            return []
        state = ctypes.c_int(0)
        self.al.alGetSourcei(self._source, oal.AL_SOURCE_STATE, ctypes.byref(state))
        off = ctypes.c_float(0.0)
        self.al.alGetSourcef(self._source, oal.AL_SEC_OFFSET, ctypes.byref(off))
        offset = float(off.value)
        events = []
        if state.value == oal.AL_STOPPED:
            if self.active:
                events.append((2, self.duration_s))
        elif state.value == oal.AL_PLAYING:
            if self.looping_flag and offset + 1e-4 < self._last_offset:
                events.append((2, self.duration_s))
            else:
                events.append((3, min(offset, self.duration_s - 1e-6)))
        self._last_offset = offset
        return events

    # --- OpenAL graph ----------------------------------------------------------------------------
    def _build_source(self) -> None:
        """setupSpatialized 0x100103b64 / setupPlain 0x10010322c."""
        if not self.loaded:
            return
        variant = 'mono' if self.spatialized else ('stereo' if self.channels == 2 else 'center')
        # sendToReverb connects the FanOut to dryMixer and wetMixer: the port plays such a sound on the bus
        on_bus = self.send_to_reverb and self.engine.bus_al is not None
        if on_bus != self._on_bus:
            self._cleanup()                                          # source and buffer of the other device
            self._release_buffer()
            self._on_bus = on_bus
            if on_bus:
                self._check_bus_gains()
        if self._buffer and self._loaded_variant != variant:
            self._release_buffer()
        if not self._buffer:
            self._buffer, self.duration_s, self.channels = self.engine.acquire_buffer(self.path, variant, on_bus)
            self._loaded_variant = variant
        al = self.al
        if not self._source:
            self._source = al.gen('alGenSources')
        src = self._source
        self._spatial = self.spatialized
        al.alSourcei(src, oal.AL_BUFFER, self._buffer)
        al.alSourcef(src, oal.AL_MAX_GAIN, 1000.0)
        al.alSourcef(src, oal.AL_ROLLOFF_FACTOR, 0.0)
        al.alSourcei(src, oal.AL_SOURCE_RELATIVE, 1)
        if self._spatial:
            al.alSourcei(src, oal.AL_DIRECT_CHANNELS_SOFT, 0)
            al.alSourcei(src, oal.AL_SOURCE_SPATIALIZE_SOFT, 1)
        else:
            al.alSource3f(src, oal.AL_POSITION, 0.0, 0.0, 0.0)
            al.alSourcei(src, oal.AL_DIRECT_CHANNELS_SOFT, 1)
            al.alSourcei(src, oal.AL_SOURCE_SPATIALIZE_SOFT, 0)
        self._apply_filters()
        self._air_hf = 1.0
        al.alGetError()

    def _cleanup(self) -> None:
        if self._source:
            self.al.alSourceStop(self._source)
            self.al.alSourcei(self._source, oal.AL_BUFFER, 0)
            self.al.alSourcei(self._source, oal.AL_DIRECT_FILTER, 0)
            self.al.delete('alDeleteSources', self._source)
            self._source = 0
        if self._direct_filter:
            self.al.delete('alDeleteFilters', self._direct_filter)
            self._direct_filter = 0
        self.al.alGetError()

    def _release_buffer(self) -> None:
        if self._buffer:
            if self._source:
                self.al.alSourcei(self._source, oal.AL_BUFFER, 0)
            self.engine.release_buffer(self.path, self._loaded_variant, self._on_bus)
            self._buffer = 0
            self._loaded_variant = None

    def _apply_filters(self) -> None:
        if not self._source:
            return
        al = self.al
        hf = getattr(self, '_air_hf', 1.0)
        if not self._direct_filter:
            self._direct_filter = al.gen('alGenFilters')
            al.filteri(self._direct_filter, oal.AL_FILTER_TYPE, oal.AL_FILTER_LOWPASS)
        al.filterf(self._direct_filter, oal.AL_LOWPASS_GAIN, 1.0)
        al.filterf(self._direct_filter, oal.AL_LOWPASS_GAINHF, min(1.0, max(0.0, hf)))
        al.alSourcei(self._source, oal.AL_DIRECT_FILTER, self._direct_filter)
        al.alGetError()

    def _apply_gain(self) -> None:
        g = self.gain * self.fade_gain * self.volume
        if self._spatial:
            g *= S3DEngine.master_spatialised_gain * getattr(self, '_distance_gain', 1.0)
        self.al.alSourcef(self._source, oal.AL_GAIN, max(0.0, g))

    def update_position(self) -> None:
        """setPlanarInternalInternal 0x100100f74 + DistanceSimulator + BinauralPanner front gain."""
        self.planar_needs_updating = False
        if not self._source or not self._spatial:
            return
        eng = self.engine
        x, y, z = eng.normalize_to_head_position(self.planar)
        d = math.sqrt(x * x + y * y + z * z)
        if d <= 0.0:
            d = 1e-6
        # csl::IntensityAttenuationCue::vfunc_2 0x1000ef780
        dist = 1.0 / d
        if dist > eng.max_spatial_gain:
            dist = eng.max_spatial_gain
        # BinauralPanner::nextBuffer 0x1000f31bc: unit vector with y negated, gain boost in front
        ux, uy, uz = x / d, -y / d, z / d
        front = 1.0
        if ux > 0.0:
            front = (math.sin((uy + 0.5) * 180.0 * 0.0174532924) * 0.5 + 0.5) * 0.5 + 1.0
        self._distance_gain = dist * front
        # csl::AirAbsorptionCue (bilinear one-pole, fc = 198000 / d) only when d > 10
        hf = 1.0
        if d > 10.0:
            fs = 44100.0
            wc = (198000.0 / d) * 6.28318548
            k = fs + fs
            b = wc / (k + wc)
            a = (k - wc) / (k + wc)
            w = 2.0 * math.pi * 5000.0 / fs
            num = abs(b * (1 + complex(math.cos(-w), math.sin(-w))))
            den = abs(1 - a * complex(math.cos(-w), math.sin(-w)))
            hf = num / den
        if abs(hf - getattr(self, '_air_hf', 1.0)) > 1e-4:
            self._air_hf = hf
            self._apply_filters()
        # OpenAL: +x right, +y up, -z forward.  S3D: +x forward, -y left (IRCAM azimuth = atan2(-y, x)).
        self.al.alSource3f(self._source, oal.AL_POSITION, float(-uy), float(uz), float(-ux))
        self._apply_gain()
