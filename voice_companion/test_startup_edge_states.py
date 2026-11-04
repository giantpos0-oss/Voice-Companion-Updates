"""Startup, settings and updates in empty and edge states (bug sweep, November 4, 2026)."""
import json
from pathlib import Path
import tempfile
import unittest

import companion


class DamagedSpeechSettingsTests(unittest.TestCase):
    """speech-settings.json holding a list, null or text stopped startup with "Voice Companion
    could not start speech": the startup code called settings.get on something that was not a
    set of settings, and that error was not one it expected."""

    def test_settings_of_the_wrong_shape_read_as_none_saved(self):
        for text in ('[]', 'null', '"rate"', '5', '{"rate":', ''):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as folder:
                (Path(folder) / 'speech-settings.json').write_text(text, encoding='utf-8')
                self.assertEqual(companion.read_speech_settings(folder), {})

    def test_a_missing_file_is_the_first_start(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(companion.read_speech_settings(folder), {})

    def test_saved_settings_are_read_even_after_notepad_saved_them(self):
        saved = {'rate': 3, 'volume': 80, 'voice': 'Microsoft Zira'}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'speech-settings.json').write_text(json.dumps(saved), encoding='utf-8-sig')
            self.assertEqual(companion.read_speech_settings(folder), saved)

    def test_startup_reads_speech_settings_through_the_safe_reader(self):
        source = (Path(__file__).resolve().parent / 'companion.py').read_text(encoding='utf-8')
        main = source[source.index("if __name__ == '__main__':"):]
        self.assertTrue('settings = read_speech_settings(APP)' in main, 'startup must use read_speech_settings')
        self.assertFalse("json.loads((APP / 'speech-settings.json')" in main, 'startup reads the file directly')


if __name__ == '__main__':
    unittest.main()
