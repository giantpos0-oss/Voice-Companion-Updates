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
ATTR_PITCH, ATTR_SPEED, ATTR_PAUSE = 0, 1, 3
ATTR_FRONT_MARGIN, ATTR_REAR_MARGIN = 9, 10
# Will, November 17, 2026: pauses between sentences were too long. ReadSpeaker adds 200 ms of
# silence after every request by default, plus its own pause between sentences.
SENTENCE_PAUSE_MS = 250
QUIET = 150            # samples quieter than this at the start or end count as silence
KEEP_END_MS = 30
DEFAULT_BUFFER = -1
PIECE_BYTES = 2205 * 2  # ReadSpeaker hands out 50 ms of its 22 kHz sound at a time
PIECE_SAMPLES = 1200    # pieces of at least 50 ms go to the speaker as soon as they are made
SHORT_PHRASE = 40      # characters: phrases this short are kept once made
REMEMBERED = 400       # how many short phrases are kept (about 12 MB at most)


# Will, November 17, 2026: Sophie said "list" like "lest", "shut down" like "shet down" and "for"
# like "fer". These words are given their sounds (SAPI phonemes, a stressed vowel) for every
# ReadSpeaker voice. Add a word here when a voice says it wrong.
PRONUNCIATIONS = {
    'list': 'l ih 1 s t', 'lists': 'l ih 1 s t s', 'listed': 'l ih 1 s t ih d', 'listing': 'l ih 1 s t ih ng',
    'shut': 'sh ah 1 t', 'shuts': 'sh ah 1 t s',
    'for': 'f ao 1 r',
}
_WORD = None


def prepare(text, markup):
    """Text as ReadSpeaker should read it: the words in PRONUNCIATIONS get their sounds, when the
    engine reads markup (check_markup). Text it cannot mark safely is left as it is."""
    global _WORD
    text = str(text)
    if not markup or not markup.get('tags'):
        return text
    import re
    if _WORD is None:
        _WORD = re.compile(r"\b(" + '|'.join(sorted(PRONUNCIATIONS, key=len, reverse=True)) + r")\b(?!')", re.I)
    if not _WORD.search(text):
        return text
    if markup.get('entities'):
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    elif any(mark in text for mark in '&<>'):
        return text
    return _WORD.sub(lambda m: '<vtml_phoneme alphabet="x-sapi" ph="%s">%s</vtml_phoneme>' % (PRONUNCIATIONS[m.group(1).lower()], m.group(1)), text)


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


def trim_silence(pcm, rate=OUTPUT_RATE):
    """Drops silence before the first sound and all but a moment after the last, so one phrase
    runs straight into the next (key echo, and sentence after sentence)."""
    from array import array
    samples = array('h')
    samples.frombytes(pcm)
    first = next((i for i, v in enumerate(samples) if abs(v) > QUIET), None)
    if first is None:
        return pcm
    last = next(i for i in range(len(samples) - 1, -1, -1) if abs(samples[i]) > QUIET)
    end = min(len(samples), last + 1 + rate * KEEP_END_MS // 1000)
    return samples[first:end].tobytes()


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
        # Short phrases (key names, letters, menu items) are said again and again: keep their sound,
        # so a key press speaks at once instead of waiting for ReadSpeaker each time.
        from collections import OrderedDict
        self.recent = OrderedDict()
        self.markup = None      # what check_markup() found: None until checked
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
        return b''.join(self.pieces(text, rate, voice, pitch))

    def pieces(self, text, rate=0, voice='', pitch=0):
        """Speech for `text` as 24 kHz PCM, handed out piece by piece while ReadSpeaker makes it,
        so speaking starts with the first piece (Will, November 17, 2026: quick keys lagged).

        Silence before the first sound is dropped, and silence after the last is cut to a moment
        (trim_silence), the same as for a whole phrase. Stopping early (a key press) closes the
        request at once."""
        if not str(text).strip():
            raise ValueError('Nothing to say')
        engine, sampling = self._engine(voice)
        remember = len(str(text)) <= SHORT_PHRASE
        key = (str(text), speed_percent(rate), voice, pitch_percent(pitch))
        if remember:
            with self.lock:
                cached = self.recent.get(key)
                if cached is not None:
                    self.recent.move_to_end(key)
            if cached is not None:
                yield cached
                return
        given = []
        for piece in self._stream(prepare(text, self.markup), rate, pitch, engine, sampling):
            given.append(piece)
            yield piece
        if not given:
            raise ReadSpeakerError('ReadSpeaker made no sound.')
        if remember:
            with self.lock:
                self.recent[key] = b''.join(given)
                while len(self.recent) > REMEMBERED:
                    self.recent.popitem(last=False)

    def _stream(self, text, rate, pitch, engine, sampling):
        from array import array
        resampler = PCM16Resampler(sampling, OUTPUT_RATE) if sampling != OUTPUT_RATE else None
        keep = OUTPUT_RATE * KEEP_END_MS // 1000
        held, odd, started = array('h'), b'', False
        with self.lock:
            lib, handle = self.lib, self.handle
            if lib.VTAPI_SetEngineHandle(handle, engine) != 0:
                raise ReadSpeakerError('ReadSpeaker could not use that voice. ' + self.last_error())
            lib.VTAPI_SetAttr(handle, ATTR_SPEED, speed_percent(rate))
            lib.VTAPI_SetAttr(handle, ATTR_PITCH, pitch_percent(pitch))
            lib.VTAPI_SetAttr(handle, ATTR_FRONT_MARGIN, 0)
            lib.VTAPI_SetAttr(handle, ATTR_REAR_MARGIN, 0)
            lib.VTAPI_SetAttr(handle, ATTR_PAUSE, SENTENCE_PAUSE_MS)
            if lib.VTAPI_SetOutputBuffer(handle, FORMAT_16PCM) != 0:
                raise ReadSpeakerError('ReadSpeaker could not make sound. ' + self.last_error())
            data = str(text).encode('utf-8')
            code = lib.VTAPI_BufferOpen(handle, data, len(data), TEXT_FORMAT_UTF8, PIECE_BYTES)
            if code != 0:
                raise ReadSpeakerError(problem(code, self.last_error()))
            try:
                for _ in range(100000):
                    frame = ctypes.c_void_p()
                    size = lib.VTAPI_GetBuffer(handle, ctypes.byref(frame))
                    if size < 0:
                        raise ReadSpeakerError(problem(size, self.last_error()))
                    if size == 0:
                        break
                    if not frame.value:
                        continue
                    raw = odd + ctypes.string_at(frame.value, size)
                    lib.VTAPI_FreeBuffer(frame)
                    raw, odd = (raw[:-1], raw[-1:]) if len(raw) % 2 else (raw, b'')
                    if resampler is not None:
                        raw = resampler.convert(raw)
                    held.frombytes(raw)
                    if not started:
                        first = next((i for i, v in enumerate(held) if abs(v) > QUIET), None)
                        if first is None:
                            continue
                        del held[:first]
                        started = True
                    # Hand out everything up to the last sound; silence after it waits until
                    # more sound follows or the phrase ends.
                    # A piece may be all silence (a pause inside a sentence): then nothing is
                    # ready yet (Will, November 17, 2026: this stopped phrases with an error).
                    last = next((i for i in range(len(held) - 1, -1, -1) if abs(held[i]) > QUIET), -1)
                    if last >= 0 and last + 1 >= PIECE_SAMPLES:
                        ready = held[:last + 1].tobytes()
                        del held[:last + 1]
                        yield ready
            finally:
                lib.VTAPI_BufferClose(handle)
        if not started:
            if held:
                yield held.tobytes()            # all quiet: left alone, as trim_silence does
            return
        last = next((i for i in range(len(held) - 1, -1, -1) if abs(held[i]) > QUIET), -1)
        tail = held[:min(len(held), last + 1 + keep)].tobytes()
        if tail:
            yield tail

    def check_markup(self, voice):
        """Finds out, by length of sound alone, whether this engine reads VTML tags and &amp;-style
        characters, so pronunciation fixes are used only where they work."""
        def length(text):
            return len(b''.join(self._stream(text, 0, 0, *self._engine(voice))))
        plain = length('Ready.')
        tags = length('<vtml_pause time="1"/>Ready.') < plain * 1.5
        entities = False
        if tags:
            spelled, sign = length('Salt and pepper.'), length('Salt &amp; pepper.')
            entities = abs(sign - spelled) < spelled * 0.25
        self.markup = {'tags': tags, 'entities': entities}
        return self.markup

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


def synthesize(text, rate=0, voice='', pitch=0, pieces=False):
    """Speech as 24 kHz PCM; with pieces=True, as pieces handed out while they are made."""
    current = engine()
    if current is None:
        raise ReadSpeakerError('ReadSpeaker is not set up on this computer.')
    from capital_feedback import pitch_for
    if pieces:
        return current.pieces(text, rate, voice, pitch_for(text, pitch))
    return current.synthesize(text, rate, voice, pitch_for(text, pitch))


SAMPLE_PHRASE = 'List. Shut down. Ready for you.'


def write_wave(path, pcm, rate=OUTPUT_RATE):
    import wave
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate); out.writeframes(pcm)


def self_check(output, rate=0):
    """Writes readspeaker-check.txt: what was found, how fast speech starts, and whether
    pronunciation fixes can be used. Also saves short samples of the words Will found said wrong
    (in the readspeaker folder's "samples" folder), plain and fixed, so they can be measured.

    Run once at start on a computer that has the readspeaker folder, so a helper (or Claude) can
    see whether the SDK, license and voices work without anyone listening. No user text is written."""
    import time
    lines = ['ReadSpeaker check', 'SDK folder: ' + str(sdk_folder())]
    try:
        current = engine()
        voices = current.voices() if current else []
        lines.append('Voices: ' + (', '.join(name + ' (' + code + ', ' + str(rate_hz) + ' Hz)' for name, code, rate_hz in voices) or 'none found'))
        if voices:
            found = current.check_markup(voices[0][1])
            lines.append('Pronunciation fixes: ' + ('on' if found['tags'] else 'off, this engine does not read markup')
                         + ('' if not found['tags'] else ', special characters ' + ('marked' if found['entities'] else 'left plain')))
        samples = Path(output).parent / FOLDER_NAME / 'samples'
        for name, code, _ in voices:
            for phrase in ('Hello.', 'Voice Companion is ready. Press F1 for help.'):
                started = time.perf_counter()
                pieces = current.pieces(phrase + ' ', 0, code, 0)      # the space: never from the cache
                first = next(pieces)
                first_ms = (time.perf_counter() - started) * 1000
                pcm = first + b''.join(pieces)
                took = time.perf_counter() - started
                lines.append('%s: %d words, first sound in %.0f ms, made in %.0f ms, %.2f seconds of speech'
                             % (name, len(phrase.split()), first_ms, took * 1000, len(pcm) / 2 / OUTPUT_RATE))
            try:
                samples.mkdir(parents=True, exist_ok=True)
                speaker = split_code(code)[0]
                for speed in sorted({0, int(rate or 0)}):
                    engine_handle = current._engine(code)
                    plain = b''.join(current._stream(SAMPLE_PHRASE, speed, 0, *engine_handle))
                    fixed = b''.join(current._stream(prepare(SAMPLE_PHRASE, current.markup), speed, 0, *engine_handle))
                    write_wave(samples / ('%s-rate%d-plain.wav' % (speaker, speed)), plain)
                    write_wave(samples / ('%s-rate%d-fixed.wav' % (speaker, speed)), fixed)
                lines.append('%s: samples saved at rate %s' % (name, ', '.join(str(v) for v in sorted({0, int(rate or 0)}))))
            except Exception as exc:
                lines.append('%s: samples not saved: %s' % (name, type(exc).__name__))
    except Exception as exc:
        lines.append('Problem: ' + type(exc).__name__ + ': ' + str(exc)[:500])
    Path(output).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return lines
