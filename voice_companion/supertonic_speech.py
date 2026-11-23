"""Supertonic 3 voices: studio-quality speech made on this computer (Will, November 23, 2026).

Supertonic 3 (Supertone, https://huggingface.co/Supertone/supertonic-3) makes 44.1 kHz speech
with four ONNX models and ONNX Runtime, which Companion already ships. Will asked for voices of at
least 44 kHz: Companion plays this sound at 44.1 kHz from start to finish, never through the
24 kHz path the other voices use.

The model is under the BigScience Open RAIL-M license (LICENSE in the supertonic folder). It may be
shipped free; its use rules travel with it.

Trial (November 2026): Companion uses these voices when the model is in the "supertonic" folder of
Companion's data folder (or SUPERTONIC_FOLDER, or the supertonic folder next to Companion). Without
it this module offers no voices and changes nothing.

How it is tuned for a screen reader, as ReadSpeaker was:
- The models load once, on a thread, at start, and speak one short phrase to warm up.
- Long text is made a sentence at a time, and each sentence goes to the speaker as soon as it is
  made, so speech starts after the first sentence instead of after the whole text.
- Short phrases (keys, letters, menu items) are kept once made, so they speak at once next time.
- The same words always sound the same: the model's starting noise comes from the words.
- Silence at the start and end of a phrase is trimmed, so keys and sentences follow at once.
"""
import hashlib
import json
import os
import re
import sys
import threading
from collections import OrderedDict
from pathlib import Path

PREFIX = 'supertonic:'
FOLDER_NAME = 'supertonic'
SAMPLE_RATE = 44100
MODELS = ('duration_predictor', 'text_encoder', 'vector_estimator', 'vocoder')
# Official files of Supertone/supertonic-3 at commit 3cadd1ee6394adea1bd021217a0e650ede09a323
# (Hugging Face's own SHA-256 for each). A file that does not match is never loaded.
MODEL_SHA256 = {
    'duration_predictor': 'c3eb91414d5ff8a7a239b7fe9e34e7e2bf8a8140d8375ffb14718b1c639325db',
    'text_encoder': 'c7befd5ea8c3119769e8a6c1486c4edc6a3bc8365c67621c881bbb774b9902ff',
    'vector_estimator': '883ac868ea0275ef0e991524dc64f16b3c0376efd7c320af6b53f5b780d7c61c',
    'vocoder': '085de76dd8e8d5836d6ca66826601f615939218f90e519f70ee8a36ed2a4c4ba',
}
MODEL_REVISION = '3cadd1ee6394adea1bd021217a0e650ede09a323'

# Quality against speed. Each step runs the largest model once more. Supertone's default is 8;
# fewer steps start speech sooner. Short phrases (keys, menu items) use fewer steps than reading.
STEPS = 8
SHORT_STEPS = 5
SHORT_PHRASE = 40       # characters: phrases this short use SHORT_STEPS and are kept once made
REMEMBERED = 300        # how many short phrases are kept (about 25 MB at most)
SENTENCE_CHARS = 300    # the longest piece made at once (Supertone's own limit)
SENTENCE_PAUSE_MS = 120 # silence between sentences of one text
QUIET = 120             # samples quieter than this at the start or end count as silence
KEEP_END_MS = 40
NORMAL_SPEED = 1.05     # Supertone's natural speed


class SupertonicError(Exception):
    """A Supertonic failure, in plain words."""


class Stopped(Exception):
    """Speech was interrupted while a sentence was being made."""


def data_folder():
    return Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'VoiceCompanion' / FOLDER_NAME


def model_folder(folder=None):
    """The folder holding onnx/ and voice_styles/, or None. SUPERTONIC_FOLDER can point elsewhere."""
    beside = Path(getattr(sys, 'executable', '')).parent / FOLDER_NAME if getattr(sys, 'frozen', False) else None
    for place in ([folder] if folder else [os.getenv('SUPERTONIC_FOLDER'), data_folder(), beside]):
        if not place:
            continue
        place = Path(place)
        if all((place / 'onnx' / (name + '.onnx')).is_file() for name in MODELS) and (place / 'voice_styles').is_dir():
            return place
    return None


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def check_files(folder):
    """[(model, problem)] for model files that are not Supertone's own; empty when all match.
    Checked once and remembered in verified.json, so later starts do not read 400 MB again."""
    folder = Path(folder)
    stamp = folder / 'verified.json'
    try:
        known = json.loads(stamp.read_text(encoding='utf-8'))
    except Exception:
        known = {}
    problems, changed = [], False
    for name, expected in MODEL_SHA256.items():
        path = folder / 'onnx' / (name + '.onnx')
        stat = path.stat()
        key = '%s:%d:%d' % (name, stat.st_size, int(stat.st_mtime))
        if known.get(name) == key:
            continue
        if file_sha256(path) != expected:
            problems.append((name, 'does not match Supertone\'s file'))
            continue
        known[name] = key; changed = True
    if changed:
        try: stamp.write_text(json.dumps(known), encoding='utf-8')
        except OSError: pass
    return problems


# Display names for Supertone's ten preset voices.
VOICE_NAMES = {'F': 'Female', 'M': 'Male'}


def voice_name(style):
    kind, number = style[:1], style[1:]
    return 'Supertonic ' + VOICE_NAMES.get(kind, style) + ' ' + number if number.isdigit() else 'Supertonic ' + style


def voice_code(style):
    return PREFIX + style


def split_code(code):
    if not str(code).startswith(PREFIX):
        raise ValueError('Not a Supertonic voice')
    return str(code)[len(PREFIX):]


def speed_for(rate):
    """Companion's rate (-10 to 10, 0 is normal) as Supertonic speed. Each step is about 12
    percent, so 10 is about three times as fast and -10 half speed, like the other voices."""
    rate = max(-10, min(10, int(rate or 0)))
    return NORMAL_SPEED * (3 ** (rate / 10) if rate >= 0 else 2 ** (rate / 10))


_SENTENCE = re.compile(r'(?<=[.!?;:])\s+(?=\S)')


def sentences(text, limit=SENTENCE_CHARS):
    """Text in pieces made one at a time: sentences, and long sentences split at commas or spaces."""
    text = ' '.join(str(text).split())
    out = []
    for sentence in _SENTENCE.split(text):
        while len(sentence) > limit:
            cut = max(sentence.rfind(', ', 0, limit), sentence.rfind(' ', 0, limit))
            cut = cut + 1 if cut > limit // 3 else limit
            out.append(sentence[:cut].strip()); sentence = sentence[cut:].strip()
        if sentence:
            out.append(sentence)
    return out


def trim_silence(samples, rate=SAMPLE_RATE, keep_end_ms=KEEP_END_MS):
    """int16 samples without silence before the first sound, and with only a moment after the last."""
    import numpy as np
    loud = np.flatnonzero(np.abs(samples.astype(np.int32)) > QUIET)
    if not loud.size:
        return samples[:0]
    end = min(len(samples), int(loud[-1]) + 1 + rate * keep_end_ms // 1000)
    return samples[int(loud[0]):end]


# Symbols the model does not read are said as a screen reader says them (Supertone's own code
# drops them, so "will_walsh@va.gov" became "will walsh va.gov"). CLAUDE.md: people say
# "underscore", "forward slash" and "dash", and expect to hear them.
SAID = {'@': ' at ', '_': ' underscore ', '/': ' slash ', '\\': ' backslash ', '#': ' number ', '|': ' bar '}
# Supertone's own clean-up (supertonic package, MIT license, Supertone Inc.), in the same order.
_SYMBOLS = {'\u2013': '-', '\u2011': '-', '\u2014': '-', '\u00af': ' ', '\u201c': '"', '\u201d': '"',
            '\u2018': "'", '\u2019': "'", '\u00b4': "'", '`': "'", '[': ' ', ']': ' ', '\u2192': ' ', '\u2190': ' '}
_EMOJI = re.compile('[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f700-\U0001f77f'
                    '\U0001f780-\U0001f7ff\U0001f800-\U0001f8ff\U0001f900-\U0001f9ff\U0001fa00-\U0001fa6f'
                    '\U0001fa70-\U0001faff\u2600-\u26ff\u2700-\u27bf\U0001f1e6-\U0001f1ff]+')
_SPACING = [(re.compile(r' ' + re.escape(mark)), mark) for mark in ",.!?;:'"]
_ENDING = re.compile(r'[.!?;:,\'")\]}\u2026\u3002\u300d\u300f\u3011\u3009\u300b\u203a\u00bb]$')


def prepare_text(text):
    from unicodedata import normalize
    text = normalize('NFKD', str(text))
    for mark, words in SAID.items():
        text = text.replace(mark, words)
    text = _EMOJI.sub('', text)
    for old, new in _SYMBOLS.items():
        text = text.replace(old, new)
    text = re.sub(r'[\u2665\u2606\u2661\u00a9\\\\]', '', text)
    text = text.replace('e.g.,', 'for example, ').replace('i.e.,', 'that is, ')
    for pattern, mark in _SPACING:
        text = pattern.sub(mark, text)
    text = re.sub(r'(["\'`])\1+', r'\1', text)
    text = ' '.join(text.split())
    if not _ENDING.search(text):
        text += '.'
    return text


def pitch_shift(samples, steps):
    """A short sound played higher or lower: each of Companion's pitch steps is about 5 percent.
    Used only for single letters and short phrases, where the small change in length is not heard."""
    import numpy as np
    factor = max(0.5, min(2.0, 1 + 0.05 * steps))
    if factor == 1 or not len(samples):
        return samples
    positions = np.arange(0, len(samples) - 1, factor)
    return np.interp(positions, np.arange(len(samples)), samples.astype(np.float32)).astype(np.int16)


class Engine:
    """The four Supertonic models, loaded once. `sessions` can be given for tests."""

    def __init__(self, folder=None, sessions=None, threads=None):
        import numpy as np
        self.np = np
        self.folder = Path(folder) if folder else model_folder()
        if self.folder is None:
            raise SupertonicError('Supertonic is not set up on this computer.')
        self.config = json.loads((self.folder / 'onnx' / 'tts.json').read_text(encoding='utf-8'))
        self.indexer = json.loads((self.folder / 'onnx' / 'unicode_indexer.json').read_text(encoding='utf-8'))
        self.sample_rate = int(self.config['ae']['sample_rate'])
        self.chunk = int(self.config['ae']['base_chunk_size']) * int(self.config['ttl']['chunk_compress_factor'])
        self.latent_dim = int(self.config['ttl']['latent_dim']) * int(self.config['ttl']['chunk_compress_factor'])
        if sessions is None:
            problems = check_files(self.folder)
            if problems:
                raise SupertonicError('Supertonic files are damaged: ' + ', '.join(name for name, _ in problems) + '. Install Companion again.')
            sessions = self._load(threads)
        self.dp, self.encoder, self.estimator, self.vocoder = (sessions[name] for name in MODELS)
        self.threads = getattr(self, 'threads', None)
        self.epoch = 0          # raised by interrupt(): sentences being made stop between steps
        self.styles = {}
        self.lock = threading.Lock()
        self.recent = OrderedDict()

    def _load(self, threads):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # Leave cores for the rest of Companion and the screen: a fast start without a stall.
        self.threads = options.intra_op_num_threads = threads or max(1, min(4, (os.cpu_count() or 2) // 2))
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        return {name: ort.InferenceSession(str(self.folder / 'onnx' / (name + '.onnx')), sess_options=options,
                                           providers=['CPUExecutionProvider']) for name in MODELS}

    def voices(self):
        """[(display name, code)] for Supertone's preset voices, female first."""
        names = sorted(p.stem for p in (self.folder / 'voice_styles').glob('*.json'))
        return [(voice_name(style), voice_code(style)) for style in names]

    def _style(self, code):
        style = split_code(code) if str(code).startswith(PREFIX) else str(code or '')
        if not style:
            style = self.voices()[0][1][len(PREFIX):]
        if style not in self.styles:
            path = self.folder / 'voice_styles' / (style + '.json')
            if not path.is_file():
                raise SupertonicError('The Supertonic voice ' + style + ' is not installed.')
            data = json.loads(path.read_text(encoding='utf-8'))
            np = self.np
            self.styles[style] = tuple(np.array(data[key]['data'], dtype=np.float32).reshape(data[key]['dims'])
                                       for key in ('style_ttl', 'style_dp'))
        return self.styles[style]

    def _ids(self, text):
        """The text as Supertone's model reads it: one number per character, after the same clean-up
        as Supertone's own code (prepare_text)."""
        size = len(self.indexer)
        ids = [self.indexer[ord(c)] if ord(c) < size else -1 for c in '<en>' + prepare_text(text) + '</en>']
        ids = [i for i in ids if i >= 0]          # characters the model does not know are left out
        return self.np.array([ids], dtype=self.np.int64)

    def _make(self, text, speed, code, steps, epoch=None):
        """One piece of text as int16 samples at 44.1 kHz. Stops (Stopped) between model steps once
        interrupt() is called, if `epoch` is given."""
        np = self.np
        def check():
            if epoch is not None and self.epoch != epoch:
                raise Stopped()
        ttl, dp = self._style(code)
        ids = self._ids(text)
        if ids.shape[1] <= len('<en></en>') - 2:
            return np.zeros(0, dtype=np.int16)
        mask = np.ones((1, 1, ids.shape[1]), dtype=np.float32)
        duration, *_ = self.dp.run(None, {'text_ids': ids, 'style_dp': dp, 'text_mask': mask})
        duration = duration / speed
        embedded, *_ = self.encoder.run(None, {'text_ids': ids, 'style_ttl': ttl, 'text_mask': mask})
        length = int(duration.max() * self.sample_rate)
        frames = max(1, (length + self.chunk - 1) // self.chunk)
        # The same words always start from the same noise, so they always sound the same.
        seed = int.from_bytes(hashlib.blake2b((code + '|' + text).encode('utf-8'), digest_size=8).digest(), 'little')
        latent = np.random.default_rng(seed).standard_normal((1, self.latent_dim, frames)).astype(np.float32)
        latent_mask = np.ones((1, 1, frames), dtype=np.float32)
        total = np.array([steps], dtype=np.float32)
        for step in range(steps):
            check()
            latent, *_ = self.estimator.run(None, {
                'noisy_latent': latent, 'text_emb': embedded, 'style_ttl': ttl, 'text_mask': mask,
                'latent_mask': latent_mask, 'current_step': np.array([step], dtype=np.float32), 'total_step': total})
        check()
        wave, *_ = self.vocoder.run(None, {'latent': latent})
        wave = np.asarray(wave, dtype=np.float32).reshape(-1)[:length]
        return (np.clip(wave, -1.0, 1.0) * 32767.0).astype(np.int16)

    def pieces(self, text, rate=0, voice='', shift=0):
        """Speech for text as 16-bit PCM pieces at 44.1 kHz, one per sentence, each handed out as
        soon as it is made (closing the generator stops making the rest). `shift` raises or lowers
        a short phrase's pitch in Companion's pitch steps (capital letters, "with a higher pitch")."""
        np = self.np
        text = ' '.join(str(text).split())
        if not text:
            return
        speed = speed_for(rate)
        code = voice if str(voice).startswith(PREFIX) else voice_code(voice) if voice else self.voices()[0][1]
        short = len(text) <= SHORT_PHRASE
        shift = int(shift or 0) if short else 0
        key = (code, round(speed, 3), shift, text)
        if short and key in self.recent:
            self.recent.move_to_end(key)
            yield self.recent[key]
            return
        epoch = self.epoch
        pause = np.zeros(self.sample_rate * SENTENCE_PAUSE_MS // 1000, dtype=np.int16).tobytes()
        parts = sentences(text)
        for index, part in enumerate(parts):
            try:
                with self.lock:
                    samples = trim_silence(self._make(part, speed, code, SHORT_STEPS if short else STEPS, epoch), self.sample_rate)
            except Stopped:
                return
            if shift:
                samples = pitch_shift(samples, shift)
            pcm = samples.tobytes() + (pause if index < len(parts) - 1 else b'')
            if short:
                self.recent[key] = pcm
                while len(self.recent) > REMEMBERED: self.recent.popitem(last=False)
            yield pcm

    def synthesize(self, text, rate=0, voice=''):
        return b''.join(self.pieces(text, rate, voice))


_ENGINE = None
_ENGINE_LOCK = threading.Lock()
_FAILED = None


def engine():
    """The shared engine, loaded once, or None when Supertonic is not set up here."""
    global _ENGINE, _FAILED
    with _ENGINE_LOCK:
        if _ENGINE is None and _FAILED is None and model_folder():
            try:
                _ENGINE = Engine()
            except Exception as exc:
                _FAILED = exc
                raise
        if _FAILED is not None:
            raise _FAILED
        return _ENGINE


def interrupt():
    """Stops the sentence being made (a key press). Does nothing before the models are loaded."""
    if _ENGINE is not None:
        _ENGINE.epoch += 1


def available_voices():
    """[(display name, code)] for the voice picker; empty when Supertonic is not set up.
    Read from the folder alone, so listing voices never waits for the models to load."""
    folder = model_folder()
    if folder is None:
        return []
    return [(voice_name(p.stem), voice_code(p.stem)) for p in sorted((folder / 'voice_styles').glob('*.json'))]


class Audio:
    """Pieces of sound with their sample rate, so Companion's player opens the speaker at 44.1 kHz."""

    sample_rate = SAMPLE_RATE

    def __init__(self, pieces):
        self._pieces = pieces

    def __iter__(self):
        return iter(self._pieces)

    def close(self):
        close = getattr(self._pieces, 'close', None)
        if close: close()


def synthesize(text, rate=0, voice='', pitch=0, pieces=False):
    """Speech as 44.1 kHz PCM. Pitch is not offered by Supertonic; it is ignored."""
    current = engine()
    if current is None:
        raise SupertonicError('Supertonic is not set up on this computer.')
    made = current.pieces(str(text), rate, voice, getattr(text, 'pitch_delta', 0))
    return Audio(made) if pieces else Audio([b''.join(made)])


# Made once at start for the chosen voice, so typing and arrowing speak at once.
WARM_WORDS = ([chr(c) for c in range(ord('a'), ord('z') + 1)] + [str(d) for d in range(10)] +
              ['space', 'enter', 'backspace', 'tab', 'escape', 'delete', 'blank', 'shift', 'control', 'alt',
               'up', 'down', 'left', 'right', 'home', 'end', 'page up', 'page down'])


def warm_up(voice='', rate=0):
    """Loads the models and makes one phrase into nothing, so the first real phrase is quick; with a
    Supertonic voice chosen, also makes the letters, numbers and key names it will say most."""
    current = engine()
    if current is None:
        return
    if callable(voice):
        voice, rate = voice()       # read after loading: Companion sets the saved voice meanwhile
    code = voice if str(voice).startswith(PREFIX) else current.voices()[0][1]
    current.synthesize('Ready. ', rate, code)
    if str(voice).startswith(PREFIX):
        for word in WARM_WORDS:
            current.synthesize(word, rate, code)


SAMPLE_TEXT = ('Voice Companion is ready. Press F1 for help. '
               'On March 3rd, 2026, the V.A. clinic moved to 1450 Main Street, Suite 200.')


def write_wave(path, pcm, rate=SAMPLE_RATE):
    import wave
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate); out.writeframes(pcm)


CHECK_VERSION = 'Supertonic check 1'


def self_check(output, rate=0):
    """Writes supertonic-check.txt: what was found, how fast speech starts and how fast it is made,
    for each voice, and saves a sample of each voice in the supertonic folder's "samples" folder.
    No user text is written."""
    import platform
    import time
    try:
        if Path(output).read_text(encoding='utf-8').startswith(CHECK_VERSION + '\n'):
            return None      # done once on this computer; it costs a minute of the processor
    except OSError:
        pass
    lines = [CHECK_VERSION, 'Model folder: ' + str(model_folder()),
             'Processor: %s, %s cores' % (platform.processor() or platform.machine(), os.cpu_count())]
    try:
        started = time.perf_counter()
        current = engine()
        if current is None:
            lines.append('Not set up.')
        else:
            lines.append('Loaded in %.0f ms, %s processor threads, %d Hz'
                         % ((time.perf_counter() - started) * 1000, current.threads or 'default', current.sample_rate))
            started = time.perf_counter(); current.synthesize('Ready. ', 0, current.voices()[0][1])
            lines.append('Warm-up phrase: %.0f ms' % ((time.perf_counter() - started) * 1000))
            samples = current.folder / 'samples'
            samples.mkdir(parents=True, exist_ok=True)
            for name, code in current.voices():
                for phrase in ('Enter.', 'File manager, 3 of 9.', SAMPLE_TEXT):
                    started = time.perf_counter()
                    made = current.pieces(phrase + ' ', 0, code)
                    first = next(made, b'')
                    first_ms = (time.perf_counter() - started) * 1000
                    pcm = first + b''.join(made)
                    took = time.perf_counter() - started
                    seconds = len(pcm) / 2 / current.sample_rate
                    lines.append('%s: %d characters, first sound in %.0f ms, all made in %.0f ms, %.2f seconds of speech (%.1f times real time)'
                                 % (name, len(phrase), first_ms, took * 1000, seconds, seconds / took if took else 0))
                for speed in sorted({0, int(rate or 0), 6}):
                    write_wave(samples / ('%s-rate%d.wav' % (split_code(code), speed)), current.synthesize(SAMPLE_TEXT, speed, code))
            lines.append('Samples saved at rates ' + ', '.join(str(v) for v in sorted({0, int(rate or 0), 6})))
    except Exception as exc:
        lines.append('Problem: ' + type(exc).__name__ + ': ' + str(exc)[:500])
    Path(output).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return lines
