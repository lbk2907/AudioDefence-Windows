"""ctypes binding for the parts of OpenAL Soft the port uses.

The original renders with CSL (CoreAudio); here OpenAL Soft does the mixing,
HRTF convolution and reverb.  Only what S3DEngine needs is bound: devices and
contexts (including loopback rendering for the calibration tools), buffers,
sources, ALC_SOFT_HRTF, AL_SOFT_direct_channels, AL_SOFT_source_spatialize,
AL_SOFT_callback_buffer (the reverb bus, s3d/reverb.py) and the EFX low-pass filter.

The port uses two contexts (the output device and the reverb bus device).  ``ContextAL`` wraps the
library for one context and makes that context current before each call.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, byref, c_char_p, c_float, c_int, c_uint, c_void_p

from .. import paths

# --- core AL ---------------------------------------------------------------
AL_NONE = 0
AL_SOURCE_RELATIVE = 0x0202
AL_PITCH = 0x1003
AL_POSITION = 0x1004
AL_LOOPING = 0x1007
AL_BUFFER = 0x1009
AL_GAIN = 0x100A
AL_MAX_GAIN = 0x100E
AL_SOURCE_STATE = 0x1010
AL_INITIAL = 0x1011
AL_PLAYING = 0x1012
AL_PAUSED = 0x1013
AL_STOPPED = 0x1014
AL_BUFFERS_QUEUED = 0x1015
AL_BUFFERS_PROCESSED = 0x1016
AL_REFERENCE_DISTANCE = 0x1020
AL_ROLLOFF_FACTOR = 0x1021
AL_SEC_OFFSET = 0x1024
AL_SAMPLE_OFFSET = 0x1025
AL_FORMAT_MONO16 = 0x1101
AL_FORMAT_STEREO16 = 0x1103
AL_FORMAT_MONO_FLOAT32 = 0x10010
AL_FORMAT_STEREO_FLOAT32 = 0x10011
AL_FREQUENCY = 0x2001
AL_SIZE = 0x2004
AL_NO_ERROR = 0
AL_VERSION = 0xB002
AL_RENDERER = 0xB003
AL_DISTANCE_MODEL = 0xD000

# --- ALC ---------------------------------------------------------------------
ALC_FREQUENCY = 0x1007
ALC_MONO_SOURCES = 0x1010
ALC_STEREO_SOURCES = 0x1011
ALC_DEVICE_SPECIFIER = 0x1005
ALC_ALL_DEVICES_SPECIFIER = 0x1013

# ALC_SOFT_HRTF
ALC_HRTF_SOFT = 0x1992
ALC_HRTF_STATUS_SOFT = 0x1993
ALC_NUM_HRTF_SPECIFIERS_SOFT = 0x1994
ALC_HRTF_SPECIFIER_SOFT = 0x1995
ALC_HRTF_ID_SOFT = 0x1996
ALC_TRUE = 1
ALC_FALSE = 0

# ALC_SOFT_output_mode
ALC_OUTPUT_MODE_SOFT = 0x19AC
ALC_STEREO_HRTF_SOFT = 0x19B2

# ALC_SOFT_output_limiter
ALC_OUTPUT_LIMITER_SOFT = 0x199A

# ALC_SOFT_loopback
ALC_FORMAT_CHANNELS_SOFT = 0x1990
ALC_FORMAT_TYPE_SOFT = 0x1991
ALC_STEREO_SOFT = 0x1501
ALC_FLOAT_SOFT = 0x1406

# AL_SOFT_direct_channels, AL_SOFT_source_spatialize
AL_DIRECT_CHANNELS_SOFT = 0x1033
AL_SOURCE_SPATIALIZE_SOFT = 0x1214

# ALC_EXT_EFX
ALC_MAX_AUXILIARY_SENDS = 0x20003
AL_DIRECT_FILTER = 0x20005
AL_AUXILIARY_SEND_FILTER = 0x20006
AL_AIR_ABSORPTION_FACTOR = 0x20007
AL_DIRECT_FILTER_GAINHF_AUTO = 0x2000A
AL_AUXILIARY_SEND_FILTER_GAIN_AUTO = 0x2000B
AL_AUXILIARY_SEND_FILTER_GAINHF_AUTO = 0x2000C

AL_EFFECT_TYPE = 0x8001
AL_EFFECT_REVERB = 0x0001
AL_REVERB_DENSITY = 0x0001
AL_REVERB_DIFFUSION = 0x0002
AL_REVERB_GAIN = 0x0003
AL_REVERB_GAINHF = 0x0004
AL_REVERB_DECAY_TIME = 0x0005
AL_REVERB_DECAY_HFRATIO = 0x0006
AL_REVERB_REFLECTIONS_GAIN = 0x0007
AL_REVERB_REFLECTIONS_DELAY = 0x0008
AL_REVERB_LATE_REVERB_GAIN = 0x0009
AL_REVERB_LATE_REVERB_DELAY = 0x000A
AL_REVERB_AIR_ABSORPTION_GAINHF = 0x000B
AL_REVERB_ROOM_ROLLOFF_FACTOR = 0x000C
AL_REVERB_DECAY_HFLIMIT = 0x000D

AL_FILTER_TYPE = 0x8001
AL_FILTER_LOWPASS = 0x0001
AL_LOWPASS_GAIN = 0x0001
AL_LOWPASS_GAINHF = 0x0002

AL_EFFECTSLOT_EFFECT = 0x0001
AL_EFFECTSLOT_GAIN = 0x0002
AL_EFFECTSLOT_AUXILIARY_SEND_AUTO = 0x0003

# AL_SOFT_callback_buffer: ALsizei (*)(ALvoid *userptr, ALvoid *sampledata, ALsizei numbytes)
BUFFER_CALLBACK = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p, c_int)

AL_ERRORS = {0xA001: 'AL_INVALID_NAME', 0xA002: 'AL_INVALID_ENUM', 0xA003: 'AL_INVALID_VALUE',
             0xA004: 'AL_INVALID_OPERATION', 0xA005: 'AL_OUT_OF_MEMORY'}


class OpenALError(RuntimeError):
    pass


class AL:
    """The loaded library.  Functions are exposed as attributes with argtypes set."""

    _SIGNATURES = [
        ('alcOpenDevice', c_void_p, [c_char_p]),
        ('alcCloseDevice', c_int, [c_void_p]),
        ('alcCreateContext', c_void_p, [c_void_p, POINTER(c_int)]),
        ('alcMakeContextCurrent', c_int, [c_void_p]),
        ('alcDestroyContext', None, [c_void_p]),
        ('alcGetError', c_int, [c_void_p]),
        ('alcGetString', c_char_p, [c_void_p, c_int]),
        ('alcGetIntegerv', None, [c_void_p, c_int, c_int, POINTER(c_int)]),
        ('alcIsExtensionPresent', c_int, [c_void_p, c_char_p]),
        ('alGetError', c_int, []),
        ('alIsExtensionPresent', ctypes.c_byte, [c_char_p]),
        ('alGetString', c_char_p, [c_int]),
        ('alGetProcAddress', c_void_p, [c_char_p]),
        ('alDistanceModel', None, [c_int]),
        ('alGenBuffers', None, [c_int, POINTER(c_uint)]),
        ('alDeleteBuffers', None, [c_int, POINTER(c_uint)]),
        ('alBufferData', None, [c_uint, c_int, c_void_p, c_int, c_int]),
        ('alGenSources', None, [c_int, POINTER(c_uint)]),
        ('alDeleteSources', None, [c_int, POINTER(c_uint)]),
        ('alSourcei', None, [c_uint, c_int, c_int]),
        ('alSource3i', None, [c_uint, c_int, c_int, c_int, c_int]),
        ('alSourcef', None, [c_uint, c_int, c_float]),
        ('alSource3f', None, [c_uint, c_int, c_float, c_float, c_float]),
        ('alGetSourcei', None, [c_uint, c_int, POINTER(c_int)]),
        ('alGetSourcef', None, [c_uint, c_int, POINTER(c_float)]),
        ('alSourcePlay', None, [c_uint]),
        ('alSourceStop', None, [c_uint]),
        ('alSourcePause', None, [c_uint]),
        ('alSourceRewind', None, [c_uint]),
        ('alSourceQueueBuffers', None, [c_uint, c_int, POINTER(c_uint)]),
        ('alSourceUnqueueBuffers', None, [c_uint, c_int, POINTER(c_uint)]),
        ('alListenerf', None, [c_int, c_float]),
        ('alListener3f', None, [c_int, c_float, c_float, c_float]),
    ]

    def __init__(self, dll_path: str | None = None):
        path = dll_path or paths.OPENAL_DLL
        if not os.path.exists(path):
            raise OpenALError(f'OpenAL Soft not found: {path}')
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(os.path.dirname(os.path.abspath(path)))
            except OSError:
                pass
        self.lib = ctypes.CDLL(path)
        for name, restype, argtypes in self._SIGNATURES:
            fn = getattr(self.lib, name)
            fn.restype = restype
            fn.argtypes = argtypes
            setattr(self, name, fn)
        self._ext: dict[str, object] = {}
        self.current_context = None

    def make_current(self, context) -> None:
        """alcMakeContextCurrent, remembering the current context for ContextAL."""
        self.alcMakeContextCurrent(context)
        self.current_context = context

    # extension entry points are resolved through alGetProcAddress / GetProcAddress
    def ext(self, name: str, restype, argtypes):
        fn = self._ext.get(name)
        if fn is None:
            raw = getattr(self.lib, name, None)
            if raw is None:
                addr = self.alGetProcAddress(name.encode())
                if not addr:
                    raise OpenALError(f'{name} unavailable')
                fn = ctypes.CFUNCTYPE(restype, *argtypes)(addr)
            else:
                raw.restype = restype
                raw.argtypes = argtypes
                fn = raw
            self._ext[name] = fn
        return fn

    def check(self, where: str) -> None:
        err = self.alGetError()
        if err != AL_NO_ERROR:
            raise OpenALError(f'{AL_ERRORS.get(err, hex(err))} in {where}')

    # --- small helpers -----------------------------------------------------
    def gen(self, fn_name: str) -> int:
        v = c_uint(0)
        if fn_name in ('alGenBuffers', 'alGenSources'):
            getattr(self, fn_name)(1, byref(v))
        else:
            self.ext(fn_name, None, [c_int, POINTER(c_uint)])(1, byref(v))
        return v.value

    def delete(self, fn_name: str, name: int) -> None:
        v = c_uint(name)
        if fn_name in ('alDeleteBuffers', 'alDeleteSources'):
            getattr(self, fn_name)(1, byref(v))
        else:
            self.ext(fn_name, None, [c_int, POINTER(c_uint)])(1, byref(v))

    def filteri(self, f, p, v): self.ext('alFilteri', None, [c_uint, c_int, c_int])(f, p, v)
    def filterf(self, f, p, v): self.ext('alFilterf', None, [c_uint, c_int, c_float])(f, p, v)

    def get_int(self, device, param: int) -> int:
        v = c_int(0)
        self.alcGetIntegerv(device, param, 1, byref(v))
        return v.value

    def hrtf_names(self, device) -> list[str]:
        fn = self.ext('alcGetStringiSOFT', c_char_p, [c_void_p, c_int, c_int])
        n = self.get_int(device, ALC_NUM_HRTF_SPECIFIERS_SOFT)
        return [(fn(device, ALC_HRTF_SPECIFIER_SOFT, i) or b'').decode('utf-8', 'replace') for i in range(n)]

    def reset_device(self, device, attrs: list[int]) -> bool:
        fn = self.ext('alcResetDeviceSOFT', c_int, [c_void_p, POINTER(c_int)])
        arr = (c_int * (len(attrs) + 1))(*attrs, 0)
        return bool(fn(device, arr))

    # --- loopback (used by tools/build_hrtf.py and the tests) --------------
    def loopback_open(self):
        return self.ext('alcLoopbackOpenDeviceSOFT', c_void_p, [c_char_p])(None)

    def loopback_render(self, device, frames: int):
        buf = (c_float * (frames * 2))()
        self.ext('alcRenderSamplesSOFT', None, [c_void_p, c_void_p, c_int])(device, buf, frames)
        return buf

    def render_into(self, device, address: int, frames: int) -> None:
        self.ext('alcRenderSamplesSOFT', None, [c_void_p, c_void_p, c_int])(device, address, frames)

    def buffer_callback(self, buffer: int, fmt: int, freq: int, callback) -> None:
        self.ext('alBufferCallbackSOFT', None, [c_uint, c_int, c_int, c_void_p, c_void_p])(
            buffer, fmt, freq, ctypes.cast(callback, c_void_p), None)


class ContextAL:
    """The AL library bound to one context: every call first makes that context current."""

    def __init__(self, al: AL, context):
        self._al = al
        self._context = context

    @property
    def raw(self) -> AL:
        return self._al

    def __getattr__(self, name: str):
        attr = getattr(self._al, name)
        if not callable(attr):
            return attr
        al, context = self._al, self._context

        def call(*args, **kwargs):
            if al.current_context != context:
                al.make_current(context)
            return attr(*args, **kwargs)
        self.__dict__[name] = call
        return call


def attr_list(pairs: dict[int, int]) -> ctypes.Array:
    flat: list[int] = []
    for k, v in pairs.items():
        flat += [k, v]
    return (c_int * (len(flat) + 1))(*flat, 0)
