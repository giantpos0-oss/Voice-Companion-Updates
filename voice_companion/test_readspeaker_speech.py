"""ReadSpeaker voices (readspeaker_speech.py) with a stand-in for libvtapi.dll that acts like the SDK."""
import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import readspeaker_speech as rs


class FakeVTAPI:
    """Behaves like VTAPI 4.5: installed engines, attributes, and PCM handed out in pieces."""

    def __init__(self, sampling=22050, pieces=3, piece_size=4410, open_error=0, voices=(('sophie', 'd22'), ('julie', 'd22')),
                 sample=1, reads_markup=True, reads_entities=True, by_length=False):
        self.sampling, self.pieces, self.piece_size, self.open_error = sampling, pieces, piece_size, open_error
        # sample: the value of every sample made (1 is quieter than QUIET, so it counts as silence).
        # reads_markup/reads_entities: whether tags and &amp; are read as markup or spoken as text.
        self.sample, self.reads_markup, self.reads_entities, self.by_length = sample, reads_markup, reads_entities, by_length
        self.given = 0
        self.installed = list(voices)
        self.attrs, self.freed, self.closed, self.opened, self.license = {}, 0, 0, [], None
        self._buffers = []
        self.left = 0

    def VTAPI_Init(self, folder): return 0
    def VTAPI_SetLicenseFolder(self, folder): self.license = folder
    def VTAPI_CreateHandle(self): return 1000
    def VTAPI_ReleaseHandle(self, handle): pass
    def VTAPI_Exit(self): pass
    def VTAPI_GetLastErrorInfo(self, handle): return None
    def VTAPI_GetFirstInstalledEngine(self): return 1 if self.installed else None
    def VTAPI_GetNextInstalledEngine(self, engine): return engine + 1 if engine < len(self.installed) else None

    def VTAPI_GetEngineInfoFieldEx(self, engine, speaker, kind, *rest):
        name, voice_type = self.installed[engine - 1]
        speaker.value, kind.value = name.encode(), voice_type.encode()
        rest[5]._obj.value = self.sampling

    def VTAPI_GetEngine(self, speaker, kind):
        return next((i + 1 for i, voice in enumerate(self.installed) if voice == (speaker.decode(), kind.decode())), None)

    def VTAPI_SetEngineHandle(self, handle, engine): return 0
    def VTAPI_SetAttr(self, handle, flag, value): self.attrs[flag] = value; return 0
    def VTAPI_SetOutputBuffer(self, handle, kind): return 0

    def VTAPI_BufferOpen(self, handle, text, length, kind, size):
        self.opened.append((text, length, kind))
        self.buffer_size = size
        # by_length: the number of pieces follows what is spoken, so markup the engine does not
        # read (spoken as words) makes more sound than markup it reads.
        spoken = text.decode('utf-8')
        if self.by_length:
            import re
            if self.reads_markup:
                spoken = re.sub(r'<[^>]+>', '', spoken)
            spoken = spoken.replace('&amp;', 'and' if self.reads_entities else 'and ampersand ')
            self.left = max(1, len(spoken) // 6)
        else:
            self.left = self.pieces
        return self.open_error

    def VTAPI_GetBuffer(self, handle, frame):
        if self.left <= 0:
            return 0
        self.left -= 1
        self.given += 1
        from array import array
        buffer = ctypes.create_string_buffer(array('h', [self.sample] * (self.piece_size // 2)).tobytes(), self.piece_size)
        self._buffers.append(buffer)
        frame._obj.value = ctypes.addressof(buffer)
        return self.piece_size

    def VTAPI_FreeBuffer(self, frame): self.freed += 1
    def VTAPI_BufferClose(self, handle): self.closed += 1; return 0


class SilenceTests(unittest.TestCase):
    def test_silence_before_and_after_is_cut_to_a_moment(self):
        from array import array
        quiet, sound = [0] * 4800, [3000, -3000] * 2400        # 0.2 s of silence, 0.2 s of sound
        pcm = array('h', quiet + sound + quiet).tobytes()
        trimmed = array('h', rs.trim_silence(pcm))
        self.assertEqual(trimmed[0], 3000)
        self.assertEqual(len(trimmed), len(sound) + 24000 * rs.KEEP_END_MS // 1000)

    def test_all_silence_is_left_alone(self):
        pcm = b'\x00\x00' * 100
        self.assertEqual(rs.trim_silence(pcm), pcm)


class MappingTests(unittest.TestCase):
    def test_rate_and_pitch_stay_inside_what_readspeaker_allows(self):
        self.assertEqual(rs.speed_percent(0), 100)
        self.assertEqual(rs.speed_percent(10), 300)
        self.assertEqual(rs.speed_percent(-10), 50)
        self.assertLess(rs.speed_percent(-3), 100)
        self.assertGreater(rs.speed_percent(3), 100)
        self.assertEqual(rs.speed_percent(99), 300)
        self.assertEqual(rs.pitch_percent(0), 100)
        self.assertEqual(rs.pitch_percent(-99), 50)
        self.assertEqual(rs.pitch_percent(99), 200)

    def test_voice_codes_round_trip(self):
        code = rs.voice_code('sophie', 'd22')
        self.assertEqual(code, 'readspeaker:sophie:d22')
        self.assertEqual(rs.split_code(code), ('sophie', 'd22'))
        with self.assertRaises(ValueError):
            rs.split_code('en-us')


class SetupTests(unittest.TestCase):
    def test_no_readspeaker_folder_means_no_voices_and_no_change(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict('os.environ', {'LOCALAPPDATA': folder, 'VC_READSPEAKER': ''}):
            self.assertIsNone(rs.sdk_folder())
            with mock.patch.object(rs, '_ENGINE', None):
                self.assertEqual(rs.available_voices(), [])

    def test_the_sdk_is_found_in_the_data_folder_or_its_bin_folder(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict('os.environ', {'LOCALAPPDATA': folder, 'VC_READSPEAKER': ''}):
            flat = Path(folder) / 'VoiceCompanion' / 'readspeaker'
            flat.mkdir(parents=True)
            (flat / 'libvtapi.dll').write_bytes(b'')
            self.assertEqual(rs.sdk_folder(), flat)
            (flat / 'libvtapi.dll').unlink()
            nested = flat / 'bin' / 'windows' / 'x64'
            nested.mkdir(parents=True)
            (nested / 'libvtapi.dll').write_bytes(b'')
            self.assertEqual(rs.sdk_folder(), nested)


class EngineTests(unittest.TestCase):
    def engine(self, **options):
        self.fake = FakeVTAPI(**options)
        return rs.Engine(folder=Path(tempfile.gettempdir()), lib=self.fake)

    def test_installed_voices_are_listed_by_name(self):
        voices = self.engine().voices()
        self.assertEqual([(name, code) for name, code, _ in voices],
                         [('ReadSpeaker Sophie', 'readspeaker:sophie:d22'), ('ReadSpeaker Julie', 'readspeaker:julie:d22')])

    def test_speech_is_24_khz_pcm_with_rate_and_pitch_set(self):
        engine = self.engine(sampling=22050, pieces=3, piece_size=4410)
        engine.voices()
        pcm = engine.synthesize('Hello there.', rate=3, voice='readspeaker:sophie:d22', pitch=2)
        seconds_in = 3 * 4410 / 2 / 22050
        self.assertAlmostEqual(len(pcm) / 2 / 24000, seconds_in, delta=0.01)
        self.assertEqual(self.fake.attrs[rs.ATTR_SPEED], rs.speed_percent(3))
        self.assertEqual(self.fake.attrs[rs.ATTR_PITCH], 110)
        self.assertEqual(self.fake.attrs[rs.ATTR_FRONT_MARGIN], 0)
        self.assertEqual(self.fake.attrs[rs.ATTR_REAR_MARGIN], 0)
        self.assertEqual(self.fake.attrs[rs.ATTR_PAUSE], rs.SENTENCE_PAUSE_MS)
        self.assertEqual(self.fake.freed, 3)
        self.assertEqual(self.fake.closed, 1)
        self.assertEqual(self.fake.opened[0][2], rs.TEXT_FORMAT_UTF8)

    def test_a_short_phrase_said_again_is_not_made_again(self):
        # Key names and letters repeat all the time; the second time must not wait for the SDK.
        engine = self.engine()
        first = engine.synthesize('Backspace', voice='readspeaker:sophie:d22')
        again = engine.synthesize('Backspace', voice='readspeaker:sophie:d22')
        self.assertEqual(first, again)
        self.assertEqual(len(self.fake.opened), 1)
        engine.synthesize('Backspace', rate=4, voice='readspeaker:sophie:d22')
        engine.synthesize('Backspace', voice='readspeaker:julie:d22')
        self.assertEqual(len(self.fake.opened), 3, 'another speed or voice is made fresh')
        engine.synthesize('A long sentence that is well over forty characters in length.', voice='readspeaker:sophie:d22')
        engine.synthesize('A long sentence that is well over forty characters in length.', voice='readspeaker:sophie:d22')
        self.assertEqual(len(self.fake.opened), 5, 'long text is not kept')

    def test_the_kept_phrases_have_a_limit(self):
        engine = self.engine(pieces=1, piece_size=4)
        for number in range(rs.REMEMBERED + 50):
            engine.synthesize(str(number), voice='readspeaker:sophie:d22')
        self.assertEqual(len(engine.recent), rs.REMEMBERED)
        self.assertNotIn(('0', 100, 'readspeaker:sophie:d22', 100), engine.recent)

    def test_non_english_letters_go_in_as_utf8(self):
        engine = self.engine()
        engine.synthesize('Café, naïve.', voice='readspeaker:julie:d22')
        text, length, _ = self.fake.opened[0]
        self.assertEqual(text, 'Café, naïve.'.encode('utf-8'))
        self.assertEqual(length, len(text))

    def test_a_license_problem_is_said_plainly_and_the_buffer_is_closed(self):
        engine = self.engine(open_error=-54)
        with self.assertRaises(rs.ReadSpeakerError) as caught:
            engine.synthesize('Hello.', voice='readspeaker:sophie:d22')
        self.assertIn('license is for another computer', str(caught.exception))

    def test_a_voice_that_is_not_installed_says_so(self):
        engine = self.engine()
        with self.assertRaises(rs.ReadSpeakerError) as caught:
            engine.synthesize('Hello.', voice='readspeaker:ashley:p16')
        self.assertIn('Ashley is not installed', str(caught.exception))

    def test_no_sound_is_an_error_not_silence(self):
        engine = self.engine(pieces=0)
        with self.assertRaises(rs.ReadSpeakerError):
            engine.synthesize('Hello.', voice='readspeaker:sophie:d22')
        self.assertEqual(self.fake.closed, 1)

    def test_empty_text_is_refused_before_the_sdk(self):
        engine = self.engine()
        with self.assertRaises(ValueError):
            engine.synthesize('   ', voice='readspeaker:sophie:d22')
        self.assertEqual(self.fake.opened, [])

    def test_the_license_folder_is_beside_the_sdk_when_verification_txt_is_there(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            sdk = base / 'bin'
            sdk.mkdir()
            (base / 'verification.txt').write_text('license')
            fake = FakeVTAPI()
            rs.Engine(folder=sdk, lib=fake)
            self.assertEqual(fake.license, str(base).encode())


class PiecesTests(unittest.TestCase):
    """Will, November 17, 2026: quick key presses lagged. Speech starts with ReadSpeaker's first piece."""

    def engine(self, **options):
        self.fake = FakeVTAPI(**options)
        engine = rs.Engine(folder=Path('.'), lib=self.fake)
        engine.voices()
        return engine

    def test_the_first_piece_comes_before_the_rest_is_made(self):
        engine = self.engine(sample=3000, pieces=6)
        pieces = engine.pieces('Ready for you.', voice='readspeaker:sophie:d22')
        next(pieces)
        self.assertLess(self.fake.given, 6, 'speaking waited for the whole phrase')
        self.assertEqual(self.fake.buffer_size, rs.PIECE_BYTES)
        list(pieces)
        self.assertEqual(self.fake.closed, 1)

    def test_stopping_early_closes_the_request_and_keeps_nothing(self):
        engine = self.engine(sample=3000, pieces=6)
        pieces = engine.pieces('Shut', voice='readspeaker:sophie:d22')
        next(pieces)
        pieces.close()                         # a key press
        self.assertEqual(self.fake.closed, 1)
        self.assertEqual(len(engine.recent), 0, 'part of a word must never be kept as the whole word')
        self.assertTrue(engine.lock.acquire(timeout=1)); engine.lock.release()

    def test_a_quiet_piece_after_sound_is_not_an_error(self):
        # Will, November 17, 2026: "eSpeak unavailable" on every few phrases. A piece of silence
        # after speech (the pause inside a sentence) stopped the phrase with "generator raised
        # StopIteration", and Companion fell back to the Windows voice.
        from array import array
        engine = self.engine()
        # Real speech: a piece ends quietly, and the next piece is all quiet.
        loud = array('h', [3000] * 2000 + [0] * 205).tobytes()
        quiet = array('h', [0] * 2205).tobytes()
        given = [loud, quiet, quiet, loud, quiet]
        def give(handle, frame):
            if not given:
                return 0
            piece = given.pop(0)
            buffer = ctypes.create_string_buffer(piece, len(piece)); self.fake._buffers.append(buffer)
            frame._obj.value = ctypes.addressof(buffer); return len(piece)
        self.fake.VTAPI_GetBuffer = give
        pcm = engine.synthesize('List. Shut down.', voice='readspeaker:sophie:d22')
        samples = array('h', pcm)
        self.assertGreater(len(samples), 2 * 2205, 'both sounds and the pause between them are kept')
        self.assertEqual(samples[-1 - 24000 * rs.KEEP_END_MS // 1000 + 1:], array('h', [0] * (24000 * rs.KEEP_END_MS // 1000)))

    def test_pieces_join_to_the_same_sound_as_the_whole_phrase(self):
        from array import array
        engine = self.engine()
        quiet, sound = [0] * 2205, [3000, -3000] * 2205
        made = array('h', quiet + sound + quiet + sound + quiet * 3).tobytes()
        engine._stream_source = made
        def give(handle, frame, _made=[made]):
            if not _made[0]:
                return 0
            piece, _made[0] = _made[0][:882], _made[0][882:]
            buffer = ctypes.create_string_buffer(piece, len(piece)); self.fake._buffers.append(buffer)
            frame._obj.value = ctypes.addressof(buffer); return len(piece)
        self.fake.VTAPI_GetBuffer = give
        whole = engine.synthesize('Hello there, again.', voice='readspeaker:sophie:d22', rate=0)
        expected = rs.trim_silence(rs.PCM16Resampler(22050, 24000).convert(made))
        self.assertEqual(len(whole), len(expected))
        # Resampling piece by piece may round a sample one step differently: not audible.
        self.assertLessEqual(max(abs(a - b) for a, b in zip(array('h', whole), array('h', expected))), 1)


class PronunciationTests(unittest.TestCase):
    # Will, November 17, 2026: Sophie said "lest", "shet down" and "fer".
    def test_the_words_get_their_sounds_when_the_engine_reads_markup(self):
        said = rs.prepare('List, then Shut down for now.', {'tags': True, 'entities': True})
        self.assertIn('<vtml_phoneme alphabet="x-sapi" ph="l ih 1 s t">List</vtml_phoneme>', said)
        self.assertIn('ph="sh ah 1 t">Shut</vtml_phoneme>', said)
        self.assertIn('ph="f ao 1 r">for</vtml_phoneme>', said)

    def test_other_words_and_parts_of_words_are_left_alone(self):
        for text in ('Forward the message.', 'Listen.', 'Shutter speed', 'Ready.', "for's"):
            self.assertEqual(rs.prepare(text, {'tags': True, 'entities': True}), text)

    def test_nothing_changes_when_the_engine_does_not_read_markup(self):
        self.assertEqual(rs.prepare('List for me.', None), 'List for me.')
        self.assertEqual(rs.prepare('List for me.', {'tags': False, 'entities': False}), 'List for me.')

    def test_special_characters_are_kept_as_characters(self):
        self.assertEqual(rs.prepare('Salt & pepper <for> two', {'tags': True, 'entities': True}).count('&amp;'), 1)
        self.assertIn('&lt;', rs.prepare('a < b for c', {'tags': True, 'entities': True}))
        # Without entity support, marking text with & or < could change what is read: left plain.
        self.assertEqual(rs.prepare('Salt & pepper for two', {'tags': True, 'entities': False}), 'Salt & pepper for two')

    def test_the_check_finds_what_the_engine_reads(self):
        for markup, entities in ((True, True), (True, False), (False, False)):
            fake = FakeVTAPI(sample=3000, by_length=True, reads_markup=markup, reads_entities=entities)
            engine = rs.Engine(folder=Path('.'), lib=fake)
            engine.voices()
            found = engine.check_markup('readspeaker:sophie:d22')
            self.assertEqual(found, {'tags': markup, 'entities': entities}, (markup, entities))

    def test_spoken_text_uses_the_fixes_after_the_check(self):
        fake = FakeVTAPI(sample=3000, by_length=True)
        engine = rs.Engine(folder=Path('.'), lib=fake)
        engine.voices()
        engine.synthesize('Shut down', voice='readspeaker:sophie:d22')
        self.assertNotIn(b'vtml', fake.opened[-1][0], 'no markup before the check')
        engine.check_markup('readspeaker:sophie:d22')
        engine.synthesize('Shut down now', voice='readspeaker:julie:d22')
        self.assertIn(b'ph="sh ah 1 t"', fake.opened[-1][0])


class SelfCheckTests(unittest.TestCase):
    def test_the_check_lists_voices_and_timings_without_user_text(self):
        fake = FakeVTAPI()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'readspeaker-check.txt'
            with mock.patch.object(rs, '_ENGINE', rs.Engine(folder=Path(folder), lib=fake)):
                rs.self_check(out)
            text = out.read_text()
        self.assertIn('ReadSpeaker Sophie (readspeaker:sophie:d22, 22050 Hz)', text)
        self.assertIn('Julie: 8 words, first sound in', text)
        self.assertIn('Pronunciation fixes: on', text)

    def test_samples_of_the_fixed_words_are_saved_at_the_users_speed(self):
        fake = FakeVTAPI(sample=3000, by_length=True)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'readspeaker-check.txt'
            with mock.patch.object(rs, '_ENGINE', rs.Engine(folder=Path(folder), lib=fake)):
                rs.self_check(out, rate=5)
            names = sorted(p.name for p in (Path(folder) / 'readspeaker' / 'samples').iterdir())
            text = out.read_text()
        self.assertIn('sophie-rate5-fixed.wav', names)
        self.assertIn('julie-rate0-plain.wav', names)
        self.assertIn('samples saved at rate 0, 5', text)
        fixed = [o[0].decode() for o in fake.opened if b'vtml_phoneme' in o[0]]
        self.assertTrue(fixed, 'the fixed samples used the pronunciation markup')

    def test_a_problem_is_written_not_raised(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'readspeaker-check.txt'
            with mock.patch.object(rs, 'engine', side_effect=rs.ReadSpeakerError('The ReadSpeaker license has expired.')):
                rs.self_check(out)
            self.assertIn('Problem: ReadSpeakerError: The ReadSpeaker license has expired.', out.read_text())


class CompanionTests(unittest.TestCase):
    """The voice picker and the local speech player use ReadSpeaker voices only when they exist."""

    def setUp(self):
        import companion
        self.app = companion
        self.saved = (companion.ESPEAK_SPEECH, companion.ESPEAK_VOICE_NAME)
        companion.ESPEAK_SPEECH = mock.Mock(enabled=False)
        self.addCleanup(self.restore)

    def restore(self):
        self.app.ESPEAK_SPEECH, self.app.ESPEAK_VOICE_NAME = self.saved

    def test_no_readspeaker_means_no_readspeaker_choice(self):
        with mock.patch('readspeaker_speech.available_voices', return_value=[]):
            self.assertNotIn('readspeaker', [kind for kind, _ in self.app.synthesizers()])

    def test_readspeaker_voices_are_a_synthesizer_and_can_be_chosen(self):
        voices = [('ReadSpeaker Sophie', 'readspeaker:sophie:d22')]
        with mock.patch('readspeaker_speech.available_voices', return_value=voices), mock.patch.object(self.app, 'interrupt_speech'), \
                mock.patch.object(self.app, 'PREFERENCES', {}):
            self.assertIn(('readspeaker', 'ReadSpeaker'), self.app.synthesizers())
            name = self.app.choose_voice(('readspeaker', 'ReadSpeaker Sophie', 'readspeaker:sophie:d22'))
        self.assertEqual(name, 'ReadSpeaker Sophie')
        self.assertTrue(self.app.ESPEAK_SPEECH.enabled)
        self.assertEqual(self.app.ESPEAK_VOICE_NAME, 'readspeaker:sophie:d22')

    def test_choosing_espeak_or_ai_leaves_the_windows_voice_alone(self):
        windows = mock.Mock()
        windows_voice = windows.Voice
        with mock.patch.object(self.app, 'interrupt_speech'), mock.patch.object(self.app, 'PREFERENCES', {}), \
                mock.patch.object(self.app, 'voice', windows, create=True), mock.patch.object(self.app, 'AI_SPEECH', mock.Mock()):
            self.app.choose_voice(('espeak', 'eSpeak US English', 'en-us'))
            self.app.choose_voice(('ai', 'AI voice Alloy', 'alloy'))
            self.assertIs(windows.Voice, windows_voice)        # was set to 'en-us', then 'alloy'
            token = object()
            self.app.choose_voice(('windows', 'Microsoft David', token))
            self.assertIs(windows.Voice, token)

    def test_use_readspeaker_by_voice(self):
        voices = [('ReadSpeaker Julie', 'readspeaker:julie:d22')]
        said = []
        with mock.patch('readspeaker_speech.available_voices', return_value=voices), \
                mock.patch.object(self.app, 'interrupt_speech'), mock.patch.object(self.app, 'speak', said.append), \
                mock.patch.object(self.app, 'save_speech_settings', return_value=True), mock.patch.object(self.app, 'TEXT_MODE', False), \
                mock.patch.object(self.app, 'PREFERENCES', {}):
            self.assertTrue(self.app.use_synthesizer('Use ReadSpeaker.'))
        self.assertTrue(said[-1].startswith('Using ReadSpeaker Julie.'))
        self.assertEqual(self.app.ESPEAK_VOICE_NAME, 'readspeaker:julie:d22')

    def test_use_readspeaker_returns_to_the_last_readspeaker_voice_and_says_how_to_change(self):
        voices = [('ReadSpeaker Julie', 'readspeaker:julie:g22'), ('ReadSpeaker Sophie', 'readspeaker:sophie:g22')]
        said = []
        with mock.patch('readspeaker_speech.available_voices', return_value=voices), \
                mock.patch.object(self.app, 'interrupt_speech'), mock.patch.object(self.app, 'speak', said.append), \
                mock.patch.object(self.app, 'save_speech_settings', return_value=True), mock.patch.object(self.app, 'TEXT_MODE', False), \
                mock.patch.object(self.app, 'PREFERENCES', {}):
            self.app.choose_voice(('readspeaker', 'ReadSpeaker Sophie', 'readspeaker:sophie:g22'))
            self.app.ESPEAK_VOICE_NAME = 'en-us'          # back on eSpeak
            self.app.use_synthesizer('Use ReadSpeaker.')
        self.assertTrue(said[-1].startswith('Using ReadSpeaker Sophie.'), said[-1])
        self.assertTrue(said[-1].endswith('To choose another ReadSpeaker voice, say select voice.'))


class OptionsTests(unittest.TestCase):
    """Synthesizer options and Voice options (Alt+O) offer ReadSpeaker and each of its voices.

    Will, November 17, 2026: the first test copy only switched by voice ("Use ReadSpeaker"),
    with no ReadSpeaker in Synthesizer options and no way to pick Sophie or Julie."""
    VOICES = [('windows', 'Microsoft David', None), ('espeak', 'eSpeak US English', 'en-us'),
              ('readspeaker', 'ReadSpeaker Julie', 'readspeaker:julie:g22'),
              ('readspeaker', 'ReadSpeaker Sophie', 'readspeaker:sophie:g22')]

    def patches(self, folder, voice_name='readspeaker:sophie:g22'):
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

    def test_options_list_readspeaker_and_both_voices(self):
        import app_settings
        from settings_model import fields, voice_field
        with tempfile.TemporaryDirectory() as folder:
            companion = self.patches(folder)
            values, context = app_settings.snapshot(companion)
        self.assertIn('readspeaker', context['engines'])
        self.assertEqual(values['engine'], 'readspeaker')
        self.assertEqual(values['readspeaker_voice'], 'ReadSpeaker Sophie')
        engine = next(f for f in fields('Synthesizer', context) if f.key == 'engine')
        self.assertIn('readspeaker', engine.choices)
        from settings_model import SettingsSession
        session = SettingsSession(values, context)   # as Alt+O opens it
        shown = voice_field(session.context)
        self.assertEqual((shown.key, shown.label), ('readspeaker_voice', 'ReadSpeaker voice'))
        self.assertEqual(shown.choices, ('ReadSpeaker Julie', 'ReadSpeaker Sophie'))

    def test_choosing_sophie_in_options_saves_and_uses_sophie(self):
        import app_settings
        with tempfile.TemporaryDirectory() as folder:
            companion = self.patches(folder, voice_name='en-us')
            values, _ = app_settings.snapshot(companion)
            values.update(engine='readspeaker', readspeaker_voice='ReadSpeaker Sophie')
            app_settings.apply_settings(companion, values)
            self.assertEqual(companion.ESPEAK_VOICE_NAME, 'readspeaker:sophie:g22')
            self.assertTrue(companion.ESPEAK_SPEECH.enabled)

    def test_no_readspeaker_on_this_computer_means_no_choice_and_a_plain_refusal(self):
        import app_settings
        self.VOICES = [v for v in self.VOICES if v[0] != 'readspeaker']
        with tempfile.TemporaryDirectory() as folder:
            companion = self.patches(folder, voice_name='en-us')
            values, context = app_settings.snapshot(companion)
            self.assertNotIn('readspeaker', context['engines'])
            values['engine'] = 'readspeaker'
            with self.assertRaises(ValueError) as caught:
                app_settings.apply_settings(companion, values)
        self.assertIn('ReadSpeaker is not set up', str(caught.exception))

    def test_saying_use_readspeaker_in_options_picks_the_synthesizer(self):
        from settings_model import SettingsSession
        session = SettingsSession({'engine': 'SAPI'}, {'engines': ('SAPI', 'espeak', 'readspeaker', 'ai')})
        for said in ('Use ReadSpeaker.', 'use read speaker', 'Choose synthesizer ReadSpeaker'):
            with self.subTest(said=said):
                self.assertEqual(session.voice_setting(said), ('engine', 'readspeaker'))


if __name__ == '__main__':
    unittest.main()
