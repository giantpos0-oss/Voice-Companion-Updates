"""The interactive tutorial: it takes every key and command while it is open, checks each
step, answers like the app, and never touches real work."""
import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import companion
import tutorial_engine
from key_state import ALT_STATE
from tutorial_engine import KEY_PREFIX, MainMenuSim, TaskMenuSim, TutorialSession, window_key


class AppHarness(unittest.TestCase):
    """The real companion module, with speech recorded and nothing that leaves the machine."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.said = []
        self.stack = contextlib.ExitStack()
        state = dict(APP=self.root, TEXT_MODE=True, APP_WINDOW=None, MAIN_MENU_INDEX=None, NAMED_LIST=None,
                     SYNTH_PICK_INDEX=None, VOICE_PICK_INDEX=None, tutorial_session=None, help_session=None,
                     account_setup=False, ACCOUNT_PICKER=None, ACCOUNT_ENTRY=None, THUNDERBIRD_SETUP=None,
                     pending_website=None, MAIN_MENU_LEAD='', SLEEP_RETURN_MODE='awake')
        self.originals = {name: Mock(name=name) for name in ('document', 'email_draft', 'mail_session', 'web_session',
                                                           'MEDIA_HUB')}
        self.stack.enter_context(patch.multiple(companion, **state, **self.originals))
        self.stack.enter_context(patch.object(companion, 'speak', lambda text, *a, **k: self.said.append(str(text))))
        self.stack.enter_context(patch.object(companion, 'interrupt_speech'))
        self.stack.enter_context(patch.object(companion, 'sync_app_context'))

    def tearDown(self):
        self.stack.close()
        self.folder.cleanup()

    def say(self, words, mode='tutorial', typed=False):
        self.said.clear()
        return companion.handle(words, mode, typed=typed)

    def press(self, key, mode='tutorial'):
        self.said.clear()
        command = companion.navigation_key(key, mode)
        return companion.handle_keyboard(command, mode) if command else mode

    def last(self):
        return ' '.join(self.said)


class EntryTests(AppHarness):
    def test_every_old_way_to_start_a_tutorial_starts_this_one(self):
        for words in tutorial_engine.START_PHRASES + ('Tutorial.', 'Lessons', 'Practice', 'Start the tutorial.'):
            for mode in ('awake', 'help'):
                with self.subTest(words=words, mode=mode):
                    companion.tutorial_session = None
                    self.assertEqual(self.say(words, mode), 'tutorial')
                    self.assertIsInstance(companion.tutorial_session, TutorialSession)
                    self.assertTrue(self.last().startswith('Tutorial. You practice each step'), self.last())

    def test_control_t_and_the_help_menu_start_it(self):
        self.assertEqual(self.press('Ctrl+T', 'awake'), 'tutorial')
        self.assertIsInstance(companion.tutorial_session, TutorialSession)
        from screen_menus import items
        self.assertIn(('Help', 'Tutorial', 'Alt, 4', 'start tutorial'), items('help'))

    def test_writing_keeps_tutorial_words_and_other_screens_protect_your_work(self):
        self.assertEqual(self.say('start tutorial', 'note'), 'note')
        self.assertIn('Say main menu first, then start tutorial.', self.last())
        self.assertIsNone(companion.tutorial_session)


class LessonFlowTests(AppHarness):
    def start(self):
        self.assertEqual(self.say('start tutorial', 'awake'), 'tutorial')

    def test_a_lesson_by_keys_and_voice_through_the_real_input_paths(self):
        self.start()
        self.press('Down')
        self.assertIn('Getting around', self.last())
        self.press('Enter')
        self.assertIn('Step 1 of', self.last())
        self.assertIn('Press Down Arrow', self.last())
        self.press('Down')
        self.assertTrue(self.last().startswith(tutorial_engine.PRAISE[0]), self.last())
        self.assertIn('File manager (F), 1 of', self.last())
        # A wrong key: what was pressed, what to do, and try again. Nothing else happens.
        self.press('Right')
        self.assertNotIn('Not quite', self.last())     # Right moves on the main menu too; it is the screen's answer
        self.press('Ctrl+N')
        self.assertIn('Not quite. You pressed Control+N.', self.last())
        self.assertIn('Try again.', self.last())
        self.assertNotIn('show me', self.last())
        self.press('Ctrl+N')
        self.assertIn('say show me to hear how, or skip to go on', self.last())
        self.press('Y')
        self.assertTrue(self.last().startswith('Here is how.'), self.last())
        self.assertEqual(self.say('repeat'), 'tutorial')
        self.assertTrue(self.last().startswith('Here is how.'))
        self.say('skip')
        self.assertIn('Skipped.', self.last())

    def test_speech_is_checked_with_its_punctuation_and_capitals(self):
        self.start()
        self.say('Getting around.')
        session = companion.tutorial_session
        session.step_index = 6          # "Say next."
        self.say('Next.')
        self.assertTrue(self.last().startswith(tutorial_engine.PRAISE[(6 + 0) % 5]), self.last())
        self.assertEqual(session.step_index, 7)
        # "please" is not understood on the real main menu: no pass, and no miss either.
        self.say('Previous, please.')
        self.assertIn('without words like please. Say just: previous.', self.last())
        self.assertEqual(session.misses, 0)
        self.say('Hello there.')
        self.assertIn('Not quite. I heard: Hello there.', self.last())
        self.say('previous', typed=True)
        self.assertEqual(session.step_index, 8)

    def test_escape_stop_tutorial_and_f1_leave_with_the_place_saved(self):
        for leave in ('Escape', 'F1', 'stop tutorial', 'Main menu.'):
            with self.subTest(leave=leave):
                self.start()
                self.say('email')
                mode = self.press(leave) if leave[0].isupper() and ' ' not in leave and '.' not in leave else self.say(leave)
                self.assertEqual(mode, 'awake')
                self.assertIsNone(companion.tutorial_session)
                self.assertIn('Tutorial stopped. Your place is saved.', self.last())
                self.assertIn('Main menu.', self.last())
                self.assertTrue((self.root / tutorial_engine.PROGRESS_FILE).exists())

    def test_a_step_that_asks_for_escape_gets_it(self):
        self.start()
        self.say('alt menus')
        session = companion.tutorial_session
        for key in ('Alt', 'Down', 'Enter'):
            self.press(key)
        self.assertIn('Press Escape to go back', self.last())
        self.assertEqual(self.press('Escape'), 'tutorial')
        self.assertEqual(session.step_index, 4)

    def test_alt_f4_leaves_through_the_real_exit_question(self):
        self.start()
        self.assertEqual(self.press('Alt+F4'), 'exit_confirm')
        self.assertIsNone(companion.tutorial_session)

    def test_f1_twice_is_tutorial_help(self):
        self.start()
        self.say('email')
        self.press('Double:F1')
        self.assertTrue(self.last().startswith('Tutorial help.'))
        self.assertIn('Now: ', self.last())

    def test_global_requests_still_work_when_the_step_does_not_ask_for_them(self):
        self.start()
        self.say('email')
        session = companion.tutorial_session
        with patch.object(companion, 'CLOCK', lambda: __import__('datetime').datetime(2026, 11, 10, 15, 5)):
            self.press('F12')
            self.assertEqual(self.last(), 'three oh five PM.')
            self.assertEqual(session.misses, 0)
        with patch.object(companion, 'speech_control', return_value='pause'), patch.object(companion, 'control_speech') as control:
            self.say('stop talking')
            control.assert_called_once_with('pause')
        self.assertEqual(self.say('go to sleep'), 'sleep')
        self.assertEqual(companion.SLEEP_RETURN_MODE, 'tutorial')

    def test_a_step_that_teaches_a_global_key_checks_it_instead(self):
        self.start()
        self.say('getting around')
        session = companion.tutorial_session
        session.begin(2)                       # Keys that work everywhere
        lesson = session.lesson()[1]
        index = next(i for i, s in enumerate(lesson.steps) if 'F12' in s.keys)
        session.step_index = index
        self.press('F12')
        self.assertEqual(session.step_index, index + 1)

    def test_nothing_real_changes_while_practicing(self):
        self.start()
        for words in ('email', 'write an email', 'send it', 'yes', 'word processor', 'save document', 'delete',
                      'web browser', 'open website va dot gov', 'options', 'check for updates', 'exit companion',
                      'radio', 'record station 1 for 30 minutes', 'file manager', 'delete', 'yes'):
            with self.subTest(words=words):
                self.assertIn(self.say(words), ('tutorial',) if words != 'exit companion' else ('tutorial', 'exit_confirm'))
            if companion.tutorial_session is None:
                break
        for key in ('Ctrl+S', 'Delete', 'Alt+O', 'Ctrl+N', 'Enter', 'Y'):
            if companion.tutorial_session is not None:
                self.press(key)
        for obj in self.originals.values():
            self.assertEqual(obj.mock_calls, [], obj)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name != tutorial_engine.PROGRESS_FILE), [])


class SimulationParityTests(AppHarness):
    """The simulated main menu and groups say exactly what the real ones say."""

    def test_main_menu_keys_and_words_match_the_real_main_menu(self):
        inputs = [('key', 'Down'), ('key', 'Down'), ('key', 'Up'), ('key', 'Home'), ('key', 'Home'), ('key', 'End'),
                  ('key', 'Down'), ('key', 'O'), ('key', 'W'), ('key', 'Q'), ('voice', 'next'), ('voice', 'previous')]
        sim = MainMenuSim(companion)
        for kind, value in inputs:
            with self.subTest(input=value):
                expected = self.press(value, 'awake') if kind == 'key' else self.say(value, 'awake')
                self.assertEqual(expected, 'awake')
                real = self.last()
                key = value if kind == 'voice' or len(value) > 1 else 'Letter:' + value.lower()
                if kind == 'key' and len(value) == 1:
                    self.said.clear(); companion.navigation_key(key, 'awake'); real = self.last()
                self.assertEqual(sim.feed(kind, value), real)

    def test_group_menus_use_the_real_menu_words(self):
        for words, mode, title in (('office tools', 'office_menu', 'Office tools'), ('organizer', 'organizer_menu', 'Organizer')):
            with self.subTest(words=words):
                self.assertEqual(self.say(words, 'awake'), mode)
                real_open = self.last()
                sim = TaskMenuSim(companion, mode, title)
                self.assertEqual(sim.open(), real_open)
                self.press('Down', mode)
                self.assertEqual(sim.feed('key', 'Down'), self.last())


class WindowTests(unittest.TestCase):
    def test_key_names_match_the_app(self):
        cases = {('Down', '', 0): 'Down', ('Return', '\r', 0): 'Enter', ('n', 'n', 4): 'Ctrl+N',
                 ('s', 'S', 5): 'Ctrl+Shift+S', ('r', 'r', 0): 'R', ('R', 'R', 1): 'Shift+R', ('Tab', '\t', 1): 'ShiftTab',
                 ('ISO_Left_Tab', '', 1): 'ShiftTab', ('F2', '', 0): 'F2', ('Delete', '', 0): 'Delete',
                 ('space', ' ', 0): 'Space', ('Next', '', 0): 'Next', ('Control_L', '', 4): 'Control',
                 ('Shift_L', '', 1): None, ('Alt_L', '', 0): None, ('1', '1', ALT_STATE): 'Alt+1',
                 ('Left', '', ALT_STATE): 'Alt+Left', ('1', '1', 4 | ALT_STATE): 'Ctrl+Alt+1', ('Escape', '', 0): 'Escape'}
        for (keysym, char, state), expected in cases.items():
            with self.subTest(keysym=keysym, state=state):
                self.assertEqual(window_key(keysym, char, state), expected)

    def test_window_sends_alt_and_every_key_to_an_open_tutorial(self):
        from screen_menus import alt_menu_key
        self.assertEqual(alt_menu_key({'mode': 'tutorial', 'tutorial_keys': True}), 'Alt')
        self.assertIsNone(alt_menu_key({'mode': 'tutorial', 'tutorial_keys': True}, command_entry_active=True))
        with patch.object(companion, 'tutorial_session', TutorialSession(companion)), \
                patch.multiple(companion, VOICE_PICK_INDEX=None, SYNTH_PICK_INDEX=None, NAMED_LIST=None):
            self.assertTrue(companion.app_context('tutorial').get('tutorial_keys'))
            self.assertEqual(companion.navigation_key('Ctrl+N', 'tutorial'), KEY_PREFIX + 'Ctrl+N')
            # A voice list opened from the tutorial keeps its own keys.
            with patch.object(companion, 'VOICE_PICK_INDEX', 0):
                self.assertFalse(tutorial_engine.intercepts_key(companion, 'Down'))

    def test_alt_o_goes_to_the_tutorial_not_to_options(self):
        source = Path(companion.__file__).read_text(encoding='utf-8')
        self.assertIn("'open options' if key=='settings' and mode!='tutorial'", source)
        self.assertEqual(tutorial_engine.canonical_key('settings'), 'Alt+O')


class MissingGuideTests(unittest.TestCase):
    """Help uses the bundled user guide. When it is missing, empty or damaged, it says so and
    you stay where you were. The tutorial does not need the guide."""
    def run_command(self, guide, command):
        with patch.object(companion, 'GUIDE', guide), patch.object(companion, 'speak') as speech, \
             patch.object(companion, 'tutorial_session', None), patch.object(companion, 'help_session', None), \
             patch.object(companion, 'sync_app_context'), patch.object(companion, 'interrupt_speech'), \
             patch.object(companion, 'APP', Path(tempfile.mkdtemp())):
            mode = companion.handle(command, 'awake', typed=True)
        return mode, ' '.join(str(call.args[0]) for call in speech.call_args_list)

    def test_help_says_the_guide_could_not_open(self):
        with tempfile.TemporaryDirectory() as folder:
            empty = Path(folder) / 'empty.txt'; empty.write_text('')
            unreadable = Path(folder) / 'bad.txt'; unreadable.write_bytes(b'\xff\xfe\x00bad')
            for guide in (Path(folder) / 'missing.txt', empty, unreadable):
                with self.subTest(guide=guide.name):
                    mode, said = self.run_command(guide, 'help')
                    self.assertEqual(mode, 'awake')
                    self.assertIn('The user guide could not open. Ask your helper to reinstall Voice Companion.', said)


if __name__ == '__main__':
    unittest.main()
