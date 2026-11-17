"""ReadSpeaker speechEngine voices (VTAPI SDK), on a computer that has them.

Evaluation only (November 2026): ReadSpeaker gave Will an evaluation license, so nothing of
ReadSpeaker is shipped with Companion. Companion uses these voices only when a helper has put the
SDK files and a license file in the "readspeaker" folder of Companion's data folder, and the
voices are installed. Without them this module offers no voices and changes nothing.

The folder holds the SDK's bin/windows/x64 files (libvtapi.dll and the rest) and verification.txt.
Speech comes back as 16-bit PCM in pieces (VTAPI_BufferOpen and VTAPI_GetBuffer), then is resampled
to the 24 kHz that Companion's speech player uses, like eSpeak.
"""
import ctypes
import os
import threading
from pathlib import Path

from audio_resample import PCM16Resampler

PREFIX = 'readspeaker:'
FOLDER_NAME = 'readspeaker'
DLL = 'libvtapi.dll'
OUTPUT_RATE = 24000
FORMAT_16PCM = 0
TEXT_FORMAT_UTF8 = 2
ATTR_PITCH, ATTR_SPEED = 0, 1
DEFAULT_BUFFER = -1


class ReadSpeakerError(Exception):
    """A ReadSpeaker failure, in plain words where the SDK gives a reason."""


def data_folder():
    return Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'VoiceCompanion' / FOLDER_NAME


def sdk_folder(folder=None):
    """The folder with libvtapi.dll, or None. VC_READSPEAKER can point somewhere else."""
    for place in (os.getenv('VC_READSPEAKER'), folder, data_folder()):
        if not place:
            continue
        place = Path(place)
        for candidate in (place, place / 'bin' / 'windows' / 'x64'):
            if (candidate / DLL).is_file():
                return candidate
    return None


def speed_percent(rate):
    """Companion's rate (-10 to 10, 0 is normal) as ReadSpeaker speed (50 to 400 percent).

    Each step is about 12 percent, so 10 is three times as fast and -10 is half speed (the slowest
    ReadSpeaker allows), close to how Windows voices change."""
    rate = max(-10, min(10, int(rate or 0)))
    return max(50, min(400, round(100 * 3 ** (rate / 10)))) if rate >= 0 else max(50, round(100 * 2 ** (rate / 10)))


def pitch_percent(pitch):
    """Companion's pitch steps (each about 5 percent) as ReadSpeaker pitch (50 to 200 percent)."""
    return max(50, min(200, 100 + int(pitch or 0) * 5))


def voice_code(speaker, kind):
    return PREFIX + speaker + ':' + kind


def split_code(code):
    if not str(code).startswith(PREFIX):
        raise ValueError('Not a ReadSpeaker voice')
    speaker, _, kind = str(code)[len(PREFIX):].partition(':')
    return speaker, kind


class Engine:
    """One loaded VTAPI library. `lib` can be given for tests; otherwise libvtapi.dll is loaded."""

    def __init__(self, folder=None, lib=None, license_folder=None):
        self.folder = Path(folder) if folder else sdk_folder()
        if lib is None:
            if self.folder is None:
                raise ReadSpeakerError('ReadSpeaker is not set up on this computer.')
            if hasattr(os, 'add_dll_directory'):
                self._dll_dir = os.add_dll_directory(str(self.folder))
            lib = ctypes.CDLL(str(self.folder / DLL))
        self.lib = lib
        self.lock = threading.Lock()
        self.engines = {}
        self._declare()
        self.lib.VTAPI_Init(str(self.folder or '').encode('utf-8') or None)
        licenses = Path(license_folder) if license_folder else (self.folder.parent if self.folder and (self.folder.parent / 'verification.txt').is_file() else self.folder)
        if licenses:
            self.lib.VTAPI_SetLicenseFolder(str(licenses).encode('utf-8'))
        self.handle = self.lib.VTAPI_CreateHandle()
        if not self.handle:
            raise ReadSpeakerError('ReadSpeaker could not start. ' + self.last_error())

    def _declare(self):
        lib, p, i, c = self.lib, ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
        table = {
            'VTAPI_Init': ([c], i), 'VTAPI_SetLicenseFolder': ([c], None), 'VTAPI_CreateHandle': ([], p),
            'VTAPI_ReleaseHandle': ([p], None), 'VTAPI_Exit': ([], None),
            'VTAPI_GetFirstInstalledEngine': ([], p), 'VTAPI_GetNextInstalledEngine': ([p], p),
            'VTAPI_GetEngineInfoField': ([p, c, c], i), 'VTAPI_GetEngine': ([c, c], p),
            'VTAPI_GetEngineInfoFieldEx': ([p, c, c, c, c, c, c, c, ctypes.POINTER(i), ctypes.POINTER(i), c], i),
            'VTAPI_SetEngineHandle': ([p, p], i), 'VTAPI_SetAttr': ([p, i, i], i),
            'VTAPI_SetOutputBuffer': ([p, i], i), 'VTAPI_BufferOpen': ([p, c, i, i, i], i),
            'VTAPI_GetBuffer': ([p, ctypes.POINTER(ctypes.c_void_p)], i), 'VTAPI_FreeBuffer': ([p], None),
            'VTAPI_BufferClose': ([p], i), 'VTAPI_GetLastErrorInfo': ([p], p),
        }
        for name, (args, result) in table.items():
            function = getattr(lib, name, None)
            if function is not None and hasattr(function, 'argtypes'):
                function.argtypes, function.restype = args, result

    def last_error(self):
        try:
            info = self.lib.VTAPI_GetLastErrorInfo(self.handle if getattr(self, 'handle', None) else None)
            if not info:
                return ''
            # VTAPI_ERRS_INFO: int nErr, then char szMsg[512].
            message = ctypes.string_at(info + ctypes.sizeof(ctypes.c_int), 512) if isinstance(info, int) else b''
            return message.split(b'\0', 1)[0].decode('utf-8', 'replace').strip()
        except Exception:
            return ''

    def voices(self):
        """Installed voices: [(display name, code, sampling rate)]."""
        found, engine = [], self.lib.VTAPI_GetFirstInstalledEngine()
        seen = 0
        while engine and seen < 100:
            seen += 1
            speaker, kind = ctypes.create_string_buffer(256), ctypes.create_string_buffer(256)
            rate = ctypes.c_int(0)
            try:
                blank = [ctypes.create_string_buffer(1024) for _ in range(5)]
                channels = ctypes.c_int(0)
                self.lib.VTAPI_GetEngineInfoFieldEx(engine, speaker, kind, blank[0], blank[1], blank[2], blank[3], blank[4],
                                                    ctypes.byref(rate), ctypes.byref(channels), ctypes.create_string_buffer(64))
            except Exception:
                self.lib.VTAPI_GetEngineInfoField(engine, speaker, kind)
            name = speaker.value.decode('utf-8', 'replace')
            if name:
                code = voice_code(name, kind.value.decode('utf-8', 'replace'))
                self.engines[code] = (engine, rate.value or 22050)
                found.append(('ReadSpeaker ' + name.title(), code, rate.value or 22050))
            engine = self.lib.VTAPI_GetNextInstalledEngine(engine)
        return found

    def _engine(self, code):
        if code not in self.engines:
            speaker, kind = split_code(code)
            engine = self.lib.VTAPI_GetEngine(speaker.encode('utf-8'), kind.encode('utf-8'))
            if not engine:
                raise ReadSpeakerError('The ReadSpeaker voice ' + speaker.title() + ' is not installed. ' + self.last_error())
            self.engines[code] = (engine, 22050)
        return self.engines[code]

    def synthesize(self, text, rate=0, voice='', pitch=0):
        """Speech for `text` as 24 kHz mono 16-bit PCM."""
        if not str(text).strip():
            raise ValueError('Nothing to say')
        engine, sampling = self._engine(voice)
        with self.lock:
            lib, handle = self.lib, self.handle
            if lib.VTAPI_SetEngineHandle(handle, engine) != 0:
                raise ReadSpeakerError('ReadSpeaker could not use that voice. ' + self.last_error())
            lib.VTAPI_SetAttr(handle, ATTR_SPEED, speed_percent(rate))
            lib.VTAPI_SetAttr(handle, ATTR_PITCH, pitch_percent(pitch))
            if lib.VTAPI_SetOutputBuffer(handle, FORMAT_16PCM) != 0:
                raise ReadSpeakerError('ReadSpeaker could not make sound. ' + self.last_error())
            data = str(text).encode('utf-8')
            code = lib.VTAPI_BufferOpen(handle, data, len(data), TEXT_FORMAT_UTF8, DEFAULT_BUFFER)
            if code != 0:
                raise ReadSpeakerError(problem(code, self.last_error()))
            pieces = []
            try:
                for _ in range(100000):
                    frame = ctypes.c_void_p()
                    size = lib.VTAPI_GetBuffer(handle, ctypes.byref(frame))
                    if size < 0:
                        raise ReadSpeakerError(problem(size, self.last_error()))
                    if size == 0:
                        break
                    if frame.value:
                        pieces.append(ctypes.string_at(frame.value, size))
                        lib.VTAPI_FreeBuffer(frame)
            finally:
                lib.VTAPI_BufferClose(handle)
        pcm = b''.join(pieces)
        if not pcm:
            raise ReadSpeakerError('ReadSpeaker made no sound.')
        if len(pcm) % 2:
            pcm = pcm[:-1]
        return pcm if sampling == OUTPUT_RATE else PCM16Resampler(sampling, OUTPUT_RATE).convert(pcm)

    def close(self):
        with self.lock:
            if getattr(self, 'handle', None):
                self.lib.VTAPI_ReleaseHandle(self.handle)
                self.handle = None
            self.lib.VTAPI_Exit()


LICENSE_PROBLEMS = {
    -51: 'The ReadSpeaker license file is missing.', -53: 'The ReadSpeaker license has expired.',
    -54: 'The ReadSpeaker license is for another computer.', -76: 'The ReadSpeaker license file is not valid.',
    -11: 'The ReadSpeaker license allows no more voices at once.',
}


def problem(code, detail=''):
    """A plain sentence for a VTAPI error code, with the SDK's own words after it."""
    text = LICENSE_PROBLEMS.get(code, 'ReadSpeaker could not speak (error ' + str(code) + ').')
    return (text + ' ' + detail).strip()


_ENGINE = None
_ENGINE_LOCK = threading.Lock()


def engine():
    """The shared engine, started once, or None when ReadSpeaker is not set up here."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None and sdk_folder():
            _ENGINE = Engine()
        return _ENGINE


def available_voices():
    """[(display name, code)] for the voice picker; empty when ReadSpeaker is not set up."""
    try:
        current = engine()
        return [(name, code) for name, code, _ in current.voices()] if current else []
    except Exception:
        return []


def synthesize(text, rate=0, voice='', pitch=0):
    current = engine()
    if current is None:
        raise ReadSpeakerError('ReadSpeaker is not set up on this computer.')
    from capital_feedback import pitch_for
    return current.synthesize(text, rate, voice, pitch_for(text, pitch))


def self_check(output):
    """Writes readspeaker-check.txt: what was found and how fast a short phrase is made.

    Run once at start on a computer that has the readspeaker folder, so a helper (or Claude) can
    see whether the SDK, license and voices work without anyone listening. No user text is written."""
    import time
    lines = ['ReadSpeaker check', 'SDK folder: ' + str(sdk_folder())]
    try:
        current = engine()
        voices = current.voices() if current else []
        lines.append('Voices: ' + (', '.join(name + ' (' + code + ', ' + str(rate) + ' Hz)' for name, code, rate in voices) or 'none found'))
        for name, code, _ in voices:
            for phrase in ('Hello.', 'Voice Companion is ready. Press F1 for help.'):
                started = time.perf_counter()
                pcm = current.synthesize(phrase, 0, code, 0)
                took = time.perf_counter() - started
                lines.append('%s: %d words made in %.0f ms, %.2f seconds of speech' % (name, len(phrase.split()), took * 1000, len(pcm) / 2 / OUTPUT_RATE))
    except Exception as exc:
        lines.append('Problem: ' + type(exc).__name__ + ': ' + str(exc)[:500])
    Path(output).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return lines

