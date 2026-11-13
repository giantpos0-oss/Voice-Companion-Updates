"""Keys and voice commands are answered quickly (Will, November 12, 2026:
"response times on both ends should be snappier").

- The main loop wakes the moment a key arrives (response_times.CommandQueue).
- The keyboard voice sets its rate and volume only when they change.
- An exact command heard on a command screen skips the dictation model's second pass;
  anything that may be text to write still gets it.
- A slow answer is written to response-times.txt with its slow step, never the words.
"""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import response_times
from response_times import CommandQueue, Log, key_label


class CommandQueueTests(unittest.TestCase):
    def test_a_key_wakes_a_waiting_loop_at_once(self):
        commands = CommandQueue()
        woke = []
        def loop():
            started = time.monotonic()
            commands.arrived.wait(5)
            woke.append(time.monotonic() - started)
        thread = threading.Thread(target=loop); thread.start()
        time.sleep(0.05)
        commands.put(('keyboard', 'Down'))
        thread.join(5)
        self.assertLess(woke[0], 0.5)

    def test_it_remembers_when_the_first_key_of_a_batch_arrived(self):
        now = [10.0]
        commands = CommandQueue(clock=lambda: now[0])
        commands.put(('keyboard', 'Down')); now[0] = 10.2
        commands.put(('keyboard', 'Down'))
        commands.get_nowait(); commands.get_nowait()
        self.assertEqual(commands.take_oldest(), 10.0)
        self.assertIsNone(commands.take_oldest())
        self.assertTrue(commands.empty())

    def test_key_labels_never_carry_typed_text(self):
        self.assertEqual(key_label(('keyboard', 'Down')), 'Down')
        self.assertEqual(key_label(('keyboard', 'Web:Pass:secret')), 'web page key')
        self.assertEqual(key_label(('account_secret', 'hunter2')), 'account secret')
        self.assertEqual(key_label('send email to bob'), 'typed command')


class LogTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.log = Log(self.folder, wall=lambda fmt: '2026-11-12 20:00:00')

    def test_quick_answers_are_not_written(self):
        self.assertFalse(self.log.slow('key Down', 'awake', [('waiting', 0.01), ('handling', 0.05)]))
        self.assertFalse((self.folder / response_times.FILE_NAME).exists())

    def test_a_slow_answer_names_its_slow_step(self):
        self.assertTrue(self.log.slow('voice command', 'mailbox', [('second recognition', 1.2), ('handling', 0.1)]))
        text = (self.folder / response_times.FILE_NAME).read_text(encoding='utf-8')
        self.assertEqual(text, '2026-11-12 20:00:00 voice command on mailbox: 1.30 seconds (second recognition 1.20, handling 0.10)\n')

    def test_the_file_keeps_only_recent_lines(self):
        for _ in range(response_times.KEEP_LINES + 20):
            self.log.slow('key Down', 'awake', [('handling', 0.5)])
        lines = (self.folder / response_times.FILE_NAME).read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), response_times.KEEP_LINES)

    def test_no_folder_or_a_broken_folder_never_raises(self):
        self.assertFalse(Log(None).slow('key Down', 'awake', [('handling', 1)]))
        blocker = self.folder / 'a file'; blocker.write_text('x')
        self.assertFalse(Log(blocker / 'inside').slow('key Down', 'awake', [('handling', 1)]))


class KeyboardVoiceTests(unittest.TestCase):
    def test_rate_and_volume_are_set_only_when_they_change(self):
        from keyboard_speech import KeyboardSpeech
        class Voice:
            def __init__(self): self.__dict__['sets'] = []
            def __setattr__(self, name, value): self.sets.append(name); self.__dict__[name] = value
            def Speak(self, *args): pass
            def WaitUntilDone(self, ms): return True
        voice = Voice()
        worker = KeyboardSpeech.__new__(KeyboardSpeech)
        worker.settings = ('', 3, 100, None, 0); worker.problem = None; worker.paused = False
        worker.active = False; worker.quiet_until = 0
        worker.queue = Mock(get=Mock(side_effect=['Down', 'Up', 'Down', None]))
        with patch.dict(sys.modules, {'pythoncom': Mock(), 'win32com': Mock(),
                                      'win32com.client': Mock(Dispatch=Mock(return_value=voice))}), \
             patch('speech32.with_32bit_voices', lambda native: native):
            worker.run()
        self.assertEqual(voice.sets, ['Rate', 'Volume'], 'Three words must not set the rate three times.')


class QuickVoiceCommandTests(unittest.TestCase):
    def setUp(self):
        import companion
        self.companion = companion

    def quick(self, heard, mode, input_mode='mixed', editor=True):
        c = self.companion
        with patch.object(c, 'INPUT_MODE', input_mode), patch.object(c, 'document', Mock() if editor else None), \
             patch.object(c, 'email_draft', Mock() if editor else None), patch.object(c, 'web_writing_field', lambda: False):
            return c.quick_voice_command(heard, mode)

    def test_the_phrase_list_is_packaged_and_loads(self):
        phrases = self.companion.command_phrases()
        self.assertGreater(len(phrases), 100)
        for phrase in ('next', 'previous', 'check email', 'main menu', 'go back'):
            self.assertIn(phrase, phrases)

    def test_an_exact_command_on_a_command_screen_is_quick(self):
        self.assertTrue(self.quick('check email', 'awake'))
        self.assertTrue(self.quick('Next.', 'mailbox'))   # recognizers add capitals and periods

    def test_words_that_may_be_writing_still_get_the_dictation_model(self):
        self.assertFalse(self.quick('next', 'document'))                     # writing comes first in writing fields
        self.assertFalse(self.quick('next', 'email_draft'))
        self.assertFalse(self.quick('next', 'note'))
        self.assertFalse(self.quick('check email', 'contacts'))              # names are spoken there
        self.assertFalse(self.quick('check email', 'tutorial'))
        self.assertFalse(self.quick('please check my email from john', 'awake'))   # not an exact phrase

    def test_commands_only_input_makes_writing_screens_quick_too(self):
        self.assertTrue(self.quick('next', 'document', input_mode='commands'))


if __name__ == '__main__':
    unittest.main()
