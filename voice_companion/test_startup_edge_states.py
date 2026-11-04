"""Startup, settings and updates in empty and edge states (bug sweep, November 4, 2026)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import companion
from test_core_email_fixes import CompanionTestCase


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


class F1RepeatsTheUpdateQuestionTests(CompanionTestCase):
    """F1 in a yes or no question says it again (Will, October 31, 2026). It found the question
    by the words "yes or no". With the microphone off, the update question says "Press Y or N"
    instead, so F1 said nothing at all, just when keys are the only way in. At startup it
    repeated the whole startup announcement instead of the question."""

    def setUp(self):
        super().setUp()
        def heard(text, *args, **kwargs):
            companion.remember_question(text); self.said.append(str(text))
        p = patch.object(companion, 'speak', heard); p.start(); self.addCleanup(p.stop)
        for name, value in dict(LAST_YES_NO='', MICROPHONE_FAILED=False, STARTUP_UPDATE_PENDING=False,
                                STARTUP_QUESTION=None, STARTUP_NOTICES=[], MAIN_MENU_LEAD='', UPDATE_OFFER=False,
                                UPDATE_RETURN_MODE='awake', PREFERENCES={'check_updates': True},
                                PREFERENCES_DAMAGED=False).items():
            p = patch.object(companion, name, value, create=True); p.start(); self.addCleanup(p.stop)
        p = patch.object(companion.sys, 'argv', ['companion']); p.start(); self.addCleanup(p.stop)

    def updates(self):
        from test_startup_announcement import FakeUpdates
        return FakeUpdates(('available', {'version': '9.9.9-test'}))

    def test_f1_repeats_the_offer_with_the_microphone_off_or_on(self):
        for off in (True, False):
            with self.subTest(microphone_off=off), patch.object(companion, 'MICROPHONE_OFF', off), \
                    patch.object(companion, 'UPDATES', self.updates()):
                companion.UPDATES.check()
                self.assertEqual(companion.poll_app_updates('awake'), 'update_offer')
                question = self.said[-1]
                self.said.clear()
                self.assertIsNone(companion.navigation_key('F1', 'update_offer'))
                self.assertEqual(self.said, [question])
                companion.handle('no', 'update_offer')

    def test_f1_after_the_startup_announcement_says_only_the_question(self):
        for off in (True, False):
            with self.subTest(microphone_off=off), patch.object(companion, 'MICROPHONE_OFF', off), \
                    patch.object(companion, 'UPDATES', self.updates()):
                self.said.clear()
                self.assertEqual(companion.announce_startup(), 'update_offer')
                self.assertTrue(self.said[-1].startswith('Voice Companion'), self.said)
                self.said.clear()
                self.assertIsNone(companion.navigation_key('F1', 'update_offer'))
                self.assertEqual(self.said, [companion.update_offer_question()])
                companion.handle('no', 'update_offer')


if __name__ == '__main__':
    unittest.main()
