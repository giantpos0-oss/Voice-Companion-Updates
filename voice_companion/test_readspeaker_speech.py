"""ReadSpeaker voices (readspeaker_speech.py) with a stand-in for libvtapi.dll that acts like the SDK."""
import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import readspeaker_speech as rs


class FakeVTAPI:
    """Behaves like VTAPI 4.5: installed engines, attributes, and PCM handed out in pieces."""

    def __init__(self, sampling=22050, pieces=3, piece_size=4410, open_error=0, voices=(('sophie', 'd22'), ('julie', 'd22'))):
        self.sampling, self.pieces, self.piece_size, self.open_error = sampling, pieces, piece_size, open_error
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
        self.left = self.pieces
        return self.open_error

    def VTAPI_GetBuffer(self, handle, frame):
        if self.left <= 0:
            return 0
        self.left -= 1
        buffer = ctypes.create_string_buffer(b'\x01\x00' * (self.piece_size // 2), self.piece_size)
        self._buffers.append(buffer)
        frame._obj.value = ctypes.addressof(buffer)
        return self.piece_size

    def VTAPI_FreeBuffer(self, frame): self.freed += 1
    def VTAPI_BufferClose(self, handle): self.closed += 1; return 0


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


class SelfCheckTests(unittest.TestCase):
    def test_the_check_lists_voices_and_timings_without_user_text(self):
        fake = FakeVTAPI()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'readspeaker-check.txt'
            with mock.patch.object(rs, '_ENGINE', rs.Engine(folder=Path(folder), lib=fake)):
                rs.self_check(out)
            text = out.read_text()
        self.assertIn('ReadSpeaker Sophie (readspeaker:sophie:d22, 22050 Hz)', text)
        self.assertIn('Julie: 8 words made in', text)

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
