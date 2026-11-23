"""Supertonic 3 voices (supertonic_speech.py): 44.1 kHz speech made on this computer.

Will, November 23, 2026: "the voices will need to be at least studio quality at 44 to 48,000 ...
that is essential." Most tests use fake models. RealModelTests run when the model is present
(SUPERTONIC_FOLDER, or Companion's data folder), and check the sound itself.
"""
import array
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import supertonic_speech as st


def make_folder(root, voices=('F1', 'M1')):
    """A model folder with tiny stand-in files (fake sessions are used with it)."""
    root = Path(root)
    (root / 'onnx').mkdir(parents=True)
    (root / 'voice_styles').mkdir()
    for name in st.MODELS:
        (root / 'onnx' / (name + '.onnx')).write_bytes(b'model ' + name.encode())
    (root / 'onnx' / 'tts.json').write_text(json.dumps({'ae': {'sample_rate': 44100, 'base_chunk_size': 512},
                                                         'ttl': {'chunk_compress_factor': 6, 'latent_dim': 24}}))
    indexer = [-1] * 600
    for i, c in enumerate(" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?;:'\"-<>/()&%$"):
        indexer[ord(c)] = i + 1
    (root / 'onnx' / 'unicode_indexer.json').write_text(json.dumps(indexer))
    for voice in voices:
        (root / 'voice_styles' / (voice + '.json')).write_text(json.dumps({
            'style_ttl': {'dims': [1, 2, 2], 'data': [[[0.1, 0.2], [0.3, 0.4]]]},
            'style_dp': {'dims': [1, 2], 'data': [[0.5, 0.6]]}}))
    return root


class FakeSession:
    """Behaves like an ONNX Runtime session: returns arrays of the shapes the real models return."""

    def __init__(self, name, log):
        self.name, self.log = name, log

    def run(self, outputs, feeds):
        self.log.append((self.name, {k: (v.shape if hasattr(v, 'shape') else v) for k, v in feeds.items()}))
        if self.name == 'duration_predictor':
            # About 0.06 seconds a character, like real speech.
            return [np.array([feeds['text_ids'].shape[1] * 0.06], dtype=np.float32)]
        if self.name == 'text_encoder':
            return [np.ones((1, 256, feeds['text_ids'].shape[1]), dtype=np.float32)]
        if self.name == 'vector_estimator':
            return [feeds['noisy_latent'] * 0.5]
        frames = feeds['latent'].shape[2]
        wave = np.sin(np.arange(frames * 3072) / 10.0).astype(np.float32) * 0.5
        wave[:2000] = 0           # silence at the start, as the real model makes
        return [wave[None, :]]


def fake_engine(folder, log=None):
    log = [] if log is None else log
    return st.Engine(folder, sessions={name: FakeSession(name, log) for name in st.MODELS}), log


class TextTests(unittest.TestCase):
    def test_symbols_the_model_cannot_read_are_said(self):
        # Supertone's own code drops them: "will_walsh@va.gov" became "will walsh va.gov".
        self.assertEqual(st.prepare_text('will_walsh@va.gov/health #3'),
                         'will underscore walsh at va.gov slash health number 3.')

    def test_supertones_own_clean_up_is_kept(self):
        self.assertEqual(st.prepare_text('He said “hi” — ok'), 'He said "hi" - ok.')
        self.assertEqual(st.prepare_text('e.g., this'), 'for example, this.')
        self.assertEqual(st.prepare_text('Done!'), 'Done!')
        self.assertEqual(st.prepare_text('Wow \U0001f600 great'), 'Wow great.')

    def test_long_text_is_made_a_sentence_at_a_time(self):
        self.assertEqual(st.sentences('First one. Second one? Third'), ['First one.', 'Second one?', 'Third'])
        long = 'word, ' * 80
        parts = st.sentences(long)
        self.assertTrue(all(len(p) <= st.SENTENCE_CHARS for p in parts))
        self.assertEqual(' '.join(parts).split(), long.split())


class MappingTests(unittest.TestCase):
    def test_rate_maps_like_the_other_voices(self):
        self.assertAlmostEqual(st.speed_for(0), st.NORMAL_SPEED)
        self.assertAlmostEqual(st.speed_for(10), st.NORMAL_SPEED * 3)
        self.assertAlmostEqual(st.speed_for(-10), st.NORMAL_SPEED / 2)
        self.assertEqual(st.speed_for(50), st.speed_for(10))
        self.assertGreater(st.speed_for(1), st.speed_for(0))

    def test_voice_names_and_codes(self):
        self.assertEqual(st.voice_name('F3'), 'Supertonic Female 3')
        self.assertEqual(st.voice_name('M1'), 'Supertonic Male 1')
        self.assertEqual(st.split_code(st.voice_code('M2')), 'M2')
        with self.assertRaises(ValueError):
            st.split_code('readspeaker:sophie:d22')


class SetupTests(unittest.TestCase):
    def test_no_model_means_no_voices_and_no_change(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch.dict(os.environ, {'SUPERTONIC_FOLDER': '', 'LOCALAPPDATA': empty}):
            self.assertIsNone(st.model_folder())
            self.assertEqual(st.available_voices(), [])

    def test_an_incomplete_folder_is_not_used(self):
        with tempfile.TemporaryDirectory() as root:
            folder = make_folder(Path(root) / 'supertonic')
            (folder / 'onnx' / 'vocoder.onnx').unlink()
            self.assertIsNone(st.model_folder(folder))

    def test_voices_are_listed_from_the_folder_without_loading_models(self):
        with tempfile.TemporaryDirectory() as root:
            folder = make_folder(Path(root) / 'supertonic', voices=('M1', 'F1', 'F2'))
            with mock.patch.dict(os.environ, {'SUPERTONIC_FOLDER': str(folder)}), mock.patch.object(st, 'Engine') as engine:
                voices = st.available_voices()
            engine.assert_not_called()
        self.assertEqual(voices, [('Supertonic Female 1', 'supertonic:F1'), ('Supertonic Female 2', 'supertonic:F2'),
                                  ('Supertonic Male 1', 'supertonic:M1')])

    def test_files_that_are_not_supertones_are_refused_and_good_ones_remembered(self):
        with tempfile.TemporaryDirectory() as root:
            folder = make_folder(Path(root) / 'supertonic')
            expected = {name: hashlib.sha256(b'model ' + name.encode()).hexdigest() for name in st.MODELS}
            with mock.patch.dict(st.MODEL_SHA256, expected):
                self.assertEqual(st.check_files(folder), [])
                self.assertTrue((folder / 'verified.json').is_file())
                with mock.patch.object(st, 'file_sha256', side_effect=AssertionError('read again')):
                    self.assertEqual(st.check_files(folder), [])       # remembered: not read again
                (folder / 'onnx' / 'vocoder.onnx').write_bytes(b'something else, longer')
                self.assertEqual([name for name, _ in st.check_files(folder)], ['vocoder'])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.folder = make_folder(Path(self.root.name) / 'supertonic')

    def test_speech_is_16_bit_pcm_without_leading_silence(self):
        engine, _ = fake_engine(self.folder)
        pcm = engine.synthesize('Hello there.', 0, 'supertonic:F1')
        samples = array.array('h', pcm)
        self.assertGreater(len(samples), 1000)
        self.assertGreater(abs(samples[0]), st.QUIET)

    def test_each_sentence_is_handed_out_as_soon_as_it_is_made(self):
        engine, log = fake_engine(self.folder)
        pieces = engine.pieces('First sentence here. Second sentence here. Third one here.', 0, 'supertonic:F1')
        next(pieces)
        self.assertEqual(sum(1 for name, _ in log if name == 'vocoder'), 1)   # only the first made yet
        pieces.close()                                                       # a key press: no more made
        self.assertEqual(sum(1 for name, _ in log if name == 'vocoder'), 1)

    def test_sentences_are_joined_by_a_short_pause(self):
        engine, _ = fake_engine(self.folder)
        first, second = list(engine.pieces('One sentence here. Another one here.', 0, 'supertonic:F1'))
        pause = st.SAMPLE_RATE * st.SENTENCE_PAUSE_MS // 1000 * 2
        self.assertEqual(first[-pause:], bytes(pause))
        self.assertNotEqual(second[-pause:], bytes(pause))

    def test_short_phrases_use_fewer_steps_and_reading_uses_more(self):
        engine, log = fake_engine(self.folder)
        engine.synthesize('Enter.', 0, 'supertonic:F1')
        short = sum(1 for name, _ in log if name == 'vector_estimator')
        log.clear()
        engine.synthesize('This is a much longer sentence that is read aloud from a document.', 0, 'supertonic:F1')
        self.assertEqual((short, sum(1 for name, _ in log if name == 'vector_estimator')), (st.SHORT_STEPS, st.STEPS))

    def test_a_short_phrase_said_again_is_not_made_again(self):
        engine, log = fake_engine(self.folder)
        first = engine.synthesize('Enter.', 0, 'supertonic:F1')
        made = len(log)
        self.assertEqual(engine.synthesize('Enter.', 0, 'supertonic:F1'), first)
        self.assertEqual(len(log), made)
        engine.synthesize('Enter.', 3, 'supertonic:F1')         # another speed is made fresh
        self.assertGreater(len(log), made)

    def test_the_same_words_always_sound_the_same(self):
        engine, _ = fake_engine(self.folder)
        engine.recent.clear()
        long = 'This sentence is long enough that it is never kept as a short phrase.'
        self.assertEqual(engine.synthesize(long, 0, 'supertonic:F1'), engine.synthesize(long, 0, 'supertonic:F1'))

    def test_faster_rate_makes_shorter_speech(self):
        engine, _ = fake_engine(self.folder)
        long = 'This sentence is long enough that it is never kept as a short phrase.'
        self.assertLess(len(engine.synthesize(long, 8, 'supertonic:F1')), len(engine.synthesize(long, 0, 'supertonic:F1')))

    def test_a_capital_letter_can_be_raised_in_pitch(self):
        engine, _ = fake_engine(self.folder)
        plain = engine.synthesize('B', 0, 'supertonic:F1')
        raised = b''.join(engine.pieces('B', 0, 'supertonic:F1', shift=4))
        self.assertNotEqual(plain, raised)
        self.assertLess(len(raised), len(plain))          # played faster, so higher

    def test_a_key_press_stops_the_sentence_being_made_between_steps(self):
        # A key press during a long sentence waited for the whole sentence to be made.
        engine, log = fake_engine(self.folder)
        real_run = FakeSession.run

        def run(session, outputs, feeds):
            if session.name == 'vector_estimator' and feeds['current_step'][0] == 2:
                with mock.patch.object(st, '_ENGINE', engine):
                    st.interrupt()                       # the key press, while step 3 is made
            return real_run(session, outputs, feeds)

        with mock.patch.object(FakeSession, 'run', run):
            pieces = list(engine.pieces('This is a long sentence that would take a while to make. And another.', 0, 'supertonic:F1'))
        self.assertEqual(pieces, [])
        self.assertEqual(sum(1 for name, _ in log if name == 'vector_estimator'), 3)
        self.assertFalse(any(name == 'vocoder' for name, _ in log))
        self.assertTrue(engine.synthesize('Next phrase is made at once.', 0, 'supertonic:F1'))   # nothing left stuck

    def test_interrupting_before_the_models_load_does_nothing(self):
        with mock.patch.object(st, '_ENGINE', None):
            st.interrupt()

    def test_a_missing_voice_says_so(self):
        engine, _ = fake_engine(self.folder)
        with self.assertRaises(st.SupertonicError) as caught:
            engine.synthesize('Hello.', 0, 'supertonic:F9')
        self.assertIn('F9', str(caught.exception))

    def test_empty_text_makes_no_sound_and_no_error(self):
        engine, log = fake_engine(self.folder)
        self.assertEqual(engine.synthesize('   ', 0, 'supertonic:F1'), b'')
        self.assertEqual(log, [])

    def test_sound_says_its_rate_so_the_player_opens_the_speaker_at_44_khz(self):
        engine, _ = fake_engine(self.folder)
        with mock.patch.object(st, 'engine', return_value=engine):
            audio = st.synthesize('Hello there.', 0, voice='supertonic:F1', pieces=True)
            from capital_feedback import CharacterSpeech
            capital = st.synthesize(CharacterSpeech('B', True, 4), 0, voice='supertonic:F1')
        self.assertEqual(audio.sample_rate, 44100)
        self.assertTrue(b''.join(audio))
        self.assertEqual(capital.sample_rate, 44100)

    def test_warm_up_makes_letters_and_keys_for_the_chosen_voice(self):
        engine, _ = fake_engine(self.folder)
        with mock.patch.object(st, 'engine', return_value=engine):
            st.warm_up(lambda: ('supertonic:M1', 0))
        self.assertIn(('supertonic:M1', round(st.speed_for(0), 3), 0, 'a'), engine.recent)
        self.assertIn(('supertonic:M1', round(st.speed_for(0), 3), 0, 'enter'), engine.recent)

    def test_the_speed_check_runs_once_and_saves_samples(self):
        engine, _ = fake_engine(self.folder)
        out = Path(self.root.name) / 'supertonic-check.txt'
        with mock.patch.object(st, 'engine', return_value=engine), mock.patch.object(st, 'model_folder', return_value=self.folder):
            lines = st.self_check(out)
            self.assertIsNone(st.self_check(out))          # done once on this computer
        text = out.read_text()
        self.assertTrue(text.startswith(st.CHECK_VERSION + '\n'))
        self.assertIn('Supertonic Female 1: 6 characters, first sound in', text)
        self.assertTrue((self.folder / 'samples' / 'F1-rate0.wav').is_file())
        self.assertNotIn('Problem', '\n'.join(lines))


class PlayerTests(unittest.TestCase):
    """Companion's speech player plays Supertonic at 44.1 kHz, and the other voices at 24 kHz."""

    class Stream:
        continuous = True
        made = []

        def __init__(self, callback=None, **options):
            self.callback, self.options, self.active, self.calls = callback, options, False, []
            type(self).made.append(self)

        def start(self): self.active = True
        def abort(self): self.active = False; self.calls.append('abort')
        def close(self): self.calls.append('close')

    def engine(self):
        import ai_speech
        self.Stream.made = []
        player = ai_speech.AISpeech(mock.Mock(), output_factory=self.Stream)
        self.addCleanup(player.close)
        return player

    def test_supertonic_sound_opens_the_speaker_at_44_khz(self):
        player = self.engine()
        player._play(st.Audio([b'\x01\x00' * 100]), player.generation, 100)
        self.assertEqual(self.Stream.made[0].options['samplerate'], 44100)
        self.assertEqual(self.Stream.made[0].options['blocksize'], 882)      # 20 ms

    def test_changing_voice_family_reopens_the_speaker_at_the_new_rate_once(self):
        player = self.engine()
        player._play(b'\x01\x00' * 100, player.generation, 100)                 # eSpeak: 24 kHz
        player._play(st.Audio([b'\x01\x00' * 100]), player.generation, 100)     # Supertonic
        player._play(st.Audio([b'\x01\x00' * 100]), player.generation, 100)
        self.assertEqual([s.options['samplerate'] for s in self.Stream.made], [24000, 44100])
        self.assertIn('close', self.Stream.made[0].calls)

    def test_a_key_press_tells_the_synthesizer_to_stop_making_sound(self):
        player = self.engine()
        player.on_interrupt = mock.Mock()
        player.interrupt()
        player.on_interrupt.assert_called_once_with()
        player.on_interrupt.side_effect = RuntimeError('broken')
        player.interrupt()                             # a failing hook never stops the player

    def test_a_phrase_made_ahead_keeps_its_rate(self):
        import ai_speech
        made = ai_speech.whole(st.Audio([b'\x01\x00', b'\x02\x00']))
        self.assertEqual((bytes(made), ai_speech.rate_of(made)), (b'\x01\x00\x02\x00', 44100))
        plain = ai_speech.whole(b'\x01\x00')
        self.assertEqual(ai_speech.rate_of(plain), 24000)

    def test_a_stream_written_directly_uses_the_rate_too(self):
        import ai_speech
        written = []

        class Direct:
            def __init__(self, **options):
                self.options = options; Direct.made = self
            def start(self): pass
            def write(self, data): written.append(len(data))
            def close(self): pass

        player = ai_speech.AISpeech(mock.Mock(), output_factory=Direct)
        self.addCleanup(player.close)
        player._play(st.Audio([b'\x00\x00' * 44100]), player.generation, 100)    # one second
        self.assertEqual(Direct.made.options['samplerate'], 44100)
        self.assertEqual(max(written), 44100 // 25 * 2)                          # 40 ms a write


class CompanionTests(unittest.TestCase):
    """The voice picker, voice commands and Voice options offer Supertonic only where it is set up."""

    def setUp(self):
        import companion
        self.app = companion
        self.saved = (companion.ESPEAK_SPEECH, companion.ESPEAK_VOICE_NAME)
        companion.ESPEAK_SPEECH = mock.Mock(enabled=False)
        self.addCleanup(self.restore)

    def restore(self):
        self.app.ESPEAK_SPEECH, self.app.ESPEAK_VOICE_NAME = self.saved

    VOICES = [('Supertonic Female 1', 'supertonic:F1'), ('Supertonic Male 2', 'supertonic:M2')]

    def test_no_model_means_no_supertonic_choice(self):
        with mock.patch('supertonic_speech.available_voices', return_value=[]):
            self.assertNotIn('supertonic', [kind for kind, _ in self.app.synthesizers()])

    def test_supertonic_voices_can_be_chosen_without_touching_the_windows_voice(self):
        windows = mock.Mock()
        with mock.patch('supertonic_speech.available_voices', return_value=self.VOICES), \
                mock.patch.object(self.app, 'interrupt_speech'), mock.patch.object(self.app, 'PREFERENCES', {}), \
                mock.patch.object(self.app, 'voice', windows, create=True):
            self.assertIn(('supertonic', 'Supertonic'), self.app.synthesizers())
            name = self.app.choose_voice(('supertonic', 'Supertonic Male 2', 'supertonic:M2'))
            # The ReadSpeaker copy also handed eSpeak's voice name to the Windows voice.
            self.app.choose_voice(('espeak', 'eSpeak US English', 'en-us'))
        self.assertEqual(name, 'Supertonic Male 2')
        self.assertTrue(self.app.ESPEAK_SPEECH.enabled)
        self.assertIsInstance(windows.Voice, mock.Mock)        # never set to 'supertonic:M2' or 'en-us'

    def test_use_supertonic_returns_to_the_last_supertonic_voice(self):
        said = []
        with mock.patch('supertonic_speech.available_voices', return_value=self.VOICES), \
                mock.patch.object(self.app, 'interrupt_speech'), mock.patch.object(self.app, 'speak', said.append), \
                mock.patch.object(self.app, 'save_speech_settings', return_value=True), mock.patch.object(self.app, 'TEXT_MODE', False), \
                mock.patch.object(self.app, 'PREFERENCES', {}):
            self.app.choose_voice(('supertonic', 'Supertonic Male 2', 'supertonic:M2'))
            self.app.ESPEAK_VOICE_NAME = 'en-us'
            for said_text in ('Use Supertonic.', 'use super tonic voice'):
                self.assertTrue(self.app.use_synthesizer(said_text))
        self.assertTrue(said[-1].startswith('Using Supertonic Male 2.'), said[-1])
        self.assertTrue(said[-1].endswith('To choose another Supertonic voice, say select voice.'))
        self.assertEqual(self.app.ESPEAK_VOICE_NAME, 'supertonic:M2')

    def test_the_local_player_uses_supertonic_for_its_voices(self):
        import ai_speech
        with mock.patch.object(ai_speech, 'AISpeech') as player, mock.patch('espeak_speech.executable', return_value='espeak'):
            self.app.configure_espeak_speech()
        synthesizer, engine_name = player.call_args[0][1], player.call_args[1]['engine_name']
        self.app.ESPEAK_VOICE_NAME = 'supertonic:F1'
        with mock.patch('supertonic_speech.synthesize', return_value='made') as made:
            self.assertEqual(synthesizer('Hello.', 2), 'made')
        made.assert_called_once_with('Hello.', 2, voice='supertonic:F1', pieces=True)
        self.assertEqual(engine_name(), 'Supertonic')


class OptionsTests(unittest.TestCase):
    """Synthesizer options and Voice options (Alt+O) offer Supertonic and each of its voices."""
    VOICES = [('windows', 'Microsoft David', None), ('espeak', 'eSpeak US English', 'en-us'),
              ('supertonic', 'Supertonic Female 1', 'supertonic:F1'),
              ('supertonic', 'Supertonic Male 2', 'supertonic:M2')]

    def patches(self, folder, voice_name='supertonic:M2'):
        import companion
        from settings_model import DEFAULTS
        windows = mock.Mock()
        windows.Voice.GetDescription.return_value = 'Microsoft David'
        stack = [mock.patch.object(companion, 'APP', Path(folder)), mock.patch.object(companion, 'TEXT_MODE', False),
                 mock.patch.object(companion, 'voice', windows, create=True),
                 mock.patch.object(companion, 'voice_choices', lambda engine=None: [v for v in self.VOICES if engine in (None, v[0])]),
                 mock.patch.object(companion, 'ESPEAK_SPEECH', mock.Mock(enabled=True)),
                 mock.patch.object(companion, 'AI_SPEECH', None), mock.patch.object(companion, 'ESPEAK_VOICE_NAME', voice_name),
                 mock.patch.object(companion, 'PREFERENCES', dict(DEFAULTS)), mock.patch.object(companion, 'mail_session', None),
                 mock.patch.object(companion, 'save_speech_settings'), mock.patch.object(companion, 'apply_transcript'),
                 mock.patch.object(companion, 'interrupt_speech'), mock.patch('windows_actions.startup_enabled', return_value=False)]
        for item in stack:
            item.start()
            self.addCleanup(item.stop)
        return companion

    def test_options_list_supertonic_and_its_voices(self):
        import app_settings
        from settings_model import SettingsSession, fields, voice_field
        with tempfile.TemporaryDirectory() as folder:
            companion = self.patches(folder)
            values, context = app_settings.snapshot(companion)
        self.assertIn('supertonic', context['engines'])
        self.assertEqual((values['engine'], values['supertonic_voice']), ('supertonic', 'Supertonic Male 2'))
        self.assertIn('supertonic', next(f for f in fields('Synthesizer', context) if f.key == 'engine').choices)
        shown = voice_field(SettingsSession(values, context).context)
        self.assertEqual((shown.key, shown.label), ('supertonic_voice', 'Supertonic voice'))
        self.assertEqual(shown.choices, ('Supertonic Female 1', 'Supertonic Male 2'))

    def test_choosing_a_voice_in_options_saves_and_uses_it(self):
        import app_settings
        with tempfile.TemporaryDirectory() as folder:
            companion = self.patches(folder, voice_name='en-us')
            values, _ = app_settings.snapshot(companion)
            values.update(engine='supertonic', supertonic_voice='Supertonic Female 1')
            app_settings.apply_settings(companion, values)
            self.assertEqual(companion.ESPEAK_VOICE_NAME, 'supertonic:F1')
            self.assertTrue(companion.ESPEAK_SPEECH.enabled)

    def test_no_model_means_no_choice_and_a_plain_refusal(self):
        import app_settings
        self.VOICES = [v for v in self.VOICES if v[0] != 'supertonic']
        with tempfile.TemporaryDirectory() as folder:
            companion = self.patches(folder, voice_name='en-us')
            values, context = app_settings.snapshot(companion)
            self.assertNotIn('supertonic', context['engines'])
            values['engine'] = 'supertonic'
            with self.assertRaises(ValueError) as caught:
                app_settings.apply_settings(companion, values)
        self.assertIn('Supertonic is not set up', str(caught.exception))

    def test_saying_use_supertonic_in_options_picks_the_synthesizer(self):
        from settings_model import SettingsSession
        session = SettingsSession({'engine': 'SAPI'}, {'engines': ('SAPI', 'espeak', 'supertonic', 'ai')})
        for said in ('Use Supertonic.', 'use super tonic', 'Choose synthesizer Supertonic'):
            with self.subTest(said=said):
                self.assertEqual(session.voice_setting(said), ('engine', 'supertonic'))


def real_folder():
    try:
        return st.model_folder()
    except Exception:
        return None


@unittest.skipUnless(real_folder(), 'The Supertonic model is not on this computer.')
class RealModelTests(unittest.TestCase):
    """The real model: genuine 44.1 kHz sound, the same each time, and fast enough to speak keys."""

    @classmethod
    def setUpClass(cls):
        cls.engine = st.Engine(real_folder())

    def test_the_sound_reaches_above_12_khz_as_studio_speech_does(self):
        pcm = self.engine.synthesize('She sells seashells by the seashore, crisp and sharp sounds.', 0, 'supertonic:F1')
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        power = np.abs(np.fft.rfft(x)) ** 2
        freq = np.fft.rfftfreq(len(x), 1 / 44100)
        # A 24 kHz voice has nothing above 12 kHz. Studio speech has a little, from s and sh sounds.
        self.assertGreater(power[freq > 12000].sum() / power.sum(), 0.0005)

    def test_the_same_words_sound_the_same_each_time(self):
        long = 'This sentence is long enough that it is never kept as a short phrase.'
        self.engine.recent.clear()
        self.assertEqual(self.engine.synthesize(long, 0, 'supertonic:M1'), self.engine.synthesize(long, 0, 'supertonic:M1'))

    def test_every_voice_speaks(self):
        for name, code in self.engine.voices():
            with self.subTest(voice=name):
                self.assertGreater(len(self.engine.synthesize('Ready.', 0, code)), 44100 // 4 * 2)


if __name__ == '__main__':
    unittest.main()
