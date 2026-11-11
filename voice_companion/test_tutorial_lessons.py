"""The tutorial's lessons: every main menu app has one, every step can be done with the
input it asks for, and each step's keys and words are the app's real ones."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import companion
import tutorial_engine
from tutorial_engine import TutorialSession, canonical_key, plain
from tutorial_lessons import build, main_menu_apps


def solution(step):
    """The inputs that do a step, as a person would give them."""
    if step.replay:
        return list(step.replay)
    if step.keys:
        return [('key', step.keys[0])]
    if step.phrases:
        return [('voice', step.phrases[0])]
    if step.text:
        return [('voice', step.example or 'Hello there.')]
    raise AssertionError('A step with nothing to do: ' + step.say)


def give(session, kind, value):
    return session.key(value) if kind == 'key' else session.words(value)


class LessonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.courses = build(companion)

    def session(self, folder=None):
        return TutorialSession(companion, folder, courses=build(companion))

    def test_every_main_menu_app_has_a_course(self):
        taught = {command for course in self.courses for command in course.apps}
        apps = main_menu_apps(companion)
        self.assertGreaterEqual(len(apps), 15)
        for name, command in apps:
            with self.subTest(app=name):
                self.assertIn(command, taught, name + ' has no tutorial course.')
        # The groups are followed: Word processor is inside Office tools, not on the main menu itself.
        self.assertIn(('Word processor', 'word processor'), apps)
        self.assertNotIn('office tools', [c for _, c in apps])

    def test_every_course_has_lessons_and_every_lesson_has_steps(self):
        keys = [c.key for c in self.courses]
        self.assertEqual(len(keys), len(set(keys)))
        for course in self.courses:
            self.assertTrue(course.lessons, course.name)
            lesson_keys = [l.key for l in course.lessons]
            self.assertEqual(len(lesson_keys), len(set(lesson_keys)), course.name)
            for lesson in course.lessons:
                with self.subTest(lesson=course.name + ': ' + lesson.title):
                    self.assertTrue(lesson.steps)
                    self.assertTrue(lesson.intro.strip())
                    for step in lesson.steps:
                        self.assertTrue(step.say.rstrip().endswith(('.', '?')), step.say)
                        self.assertNotIn('{value}', step.say)
                        self.assertNotIn('@', step.say.replace('sam@example.com', ''))

    def test_every_lesson_can_be_done_step_by_step_and_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as folder:
            session = self.session(folder)
            made = set()
            original = tutorial_engine.EditorSim.__init__

            def tracked(sim, *args, **kwargs):
                original(sim, *args, **kwargs)
                made.add(sim.folder)
            with patch.object(tutorial_engine.EditorSim, '__init__', tracked):
                for position, (course, lesson) in enumerate(session.order):
                    with self.subTest(lesson=course.name + ': ' + lesson.title):
                        session.begin(position)
                        for number, step in enumerate(lesson.steps):
                            said = ''
                            for kind, value in solution(step):
                                said, leave = give(session, kind, value)
                                self.assertIsNone(leave, step.say)
                            self.assertTrue(session.step_index > number or session.state == 'between',
                                            course.name + ', ' + lesson.title + ', step ' + str(number + 1) + ': ' +
                                            step.say + ' Said: ' + said)
                        self.assertEqual(session.state, 'between')
            for path in made:
                self.assertFalse(path.exists(), 'A practice folder was left behind.')
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), [tutorial_engine.PROGRESS_FILE])

    def test_resuming_rebuilds_the_simulated_screen(self):
        # Stop after any step, start again: the step continues on the same simulated screen.
        session = self.session()
        for position, (course, lesson) in enumerate(session.order):
            for stop_at in range(1, len(lesson.steps)):
                with self.subTest(lesson=lesson.title, step=stop_at):
                    session.begin(position)
                    for step in lesson.steps[:stop_at]:
                        for kind, value in solution(step):
                            give(session, kind, value)
                    session.begin(position, stop_at, resumed=True)
                    self.assertEqual(session.step_index, stop_at)
                    step = lesson.steps[stop_at]
                    for kind, value in solution(step):
                        said, _ = give(session, kind, value)
                    self.assertTrue(session.step_index == stop_at + 1 or session.state == 'between', said)
            session.close_sims()

    def test_key_steps_use_the_keys_of_the_real_screen(self):
        from input_parity import SCREEN_KEYS, screen_command
        from task_navigation import SHORTCUTS
        from file_manager import GROUPS
        file_keys = {key: command for _, items in GROUPS.values() for _, key, command in items}
        checked = 0
        for course in self.courses:
            for lesson in course.lessons:
                for step in lesson.steps:
                    if not step.command or not step.keys:
                        continue
                    for key in step.keys:
                        with self.subTest(step=step.say, key=key):
                            if key == 'F1':
                                self.assertIn(step.command, ('@main_menu', 'main menu'))   # F1 is the main menu everywhere
                                checked += 1
                            elif key.startswith('Double:') and step.screen in SCREEN_KEYS and key[7:] in SCREEN_KEYS[step.screen]:
                                self.assertEqual(screen_command(key[7:], step.screen), step.command)
                                checked += 1
                            elif step.screen in SCREEN_KEYS and key in SCREEN_KEYS[step.screen]:
                                real = screen_command(key, step.screen)
                                self.assertEqual(real.replace('@prompt:', ''), step.command)
                                checked += 1
                            elif step.screen == 'document' and key in SHORTCUTS:
                                if SHORTCUTS[key] != step.command:
                                    # Two names for one action ("heading one", "heading 1"): the document does the same.
                                    self.assertEqual(*(self.document_says(c) for c in (SHORTCUTS[key], step.command)))
                                checked += 1
                            elif step.screen == 'files' and key in file_keys and step.command in file_keys.values():
                                self.assertEqual(file_keys[key], step.command)
                                checked += 1
        self.assertGreater(checked, 100)

    @staticmethod
    def document_says(command):
        sim = tutorial_engine.EditorSim('document', 'The red fox ran home.')
        try:
            return sim.feed('voice', command)
        finally:
            sim.close()

    def test_drills_follow_the_app_menus(self):
        """A new item in an Alt menu, a screen key, or the document menu gets a step by itself."""
        from screen_menus import MENUS, items
        from task_navigation import DOCUMENT_ACTIONS
        commands = {step.command for c in self.courses for l in c.lessons for step in l.steps if step.command}
        for mode in ('mailbox', 'email_draft', 'note', 'web', 'contacts', 'calendar', 'help', 'file_reader', 'youtube'):
            for group, label, key, command in items(mode):
                with self.subTest(mode=mode, item=label):
                    self.assertIn(command, commands)
        for group, entries in DOCUMENT_ACTIONS.items():
            for label, key, command in entries:
                with self.subTest(group=group, item=label):
                    self.assertIn(command, commands)
        from input_parity import SCREEN_KEYS
        for mode in ('mailbox', 'email_draft', 'note', 'web', 'contacts', 'calendar', 'file_reader', 'youtube'):
            for key, command in SCREEN_KEYS[mode].items():
                if key not in ('F1', 'Ctrl+F12'):
                    with self.subTest(mode=mode, key=key):
                        self.assertIn(command, commands)

    def test_spoken_steps_on_the_main_menu_are_understood_there(self):
        """Every phrase a main menu step accepts works on the real main menu."""
        phrases = {p for c in self.courses for l in c.lessons for s in l.steps if s.screen == 'awake' for p in s.phrases}
        self.assertIn('office tools', phrases)
        for phrase in sorted(phrases):
            with self.subTest(phrase=phrase):
                said = []
                state = dict(MAIN_MENU_INDEX=1, tutorial_session=None, help_session=None, document=None, email_draft=None,
                             mail_session=None, web_session=None, NAMED_LIST=None, TEXT_MODE=True, APP_WINDOW=None,
                             account_setup=False, ACCOUNT_PICKER=None, pending_website=None, MEDIA_HUB=None)
                with tempfile.TemporaryDirectory() as folder, \
                        patch.multiple(companion, APP=Path(folder), **state), \
                        patch.object(companion, 'speak', lambda text, *a, **k: said.append(str(text))), \
                        patch.object(companion, 'interrupt_speech'), patch.object(companion, 'sync_app_context'), \
                        patch.object(companion, 'ProtectedStore') as store, patch('os.startfile', create=True), \
                        patch('subprocess.Popen'), patch('subprocess.run'):
                    store.return_value.selected.return_value = None
                    store.return_value.accounts.return_value = []
                    try:
                        companion.handle(phrase, 'awake')
                    except Exception as error:   # a phrase that reaches a real service would be a bug too
                        self.fail(phrase + ': ' + repr(error))
                text = ' '.join(said)
                self.assertNotIn('I did not understand', text, phrase)


class ProgressTests(unittest.TestCase):
    def test_a_damaged_progress_file_starts_fresh(self):
        with tempfile.TemporaryDirectory() as folder:
            for content in ('not json', '[1, 2]', json.dumps({'current': {'lesson': 'gone/lesson', 'step': 2}, 'done': 5})):
                (Path(folder) / tutorial_engine.PROGRESS_FILE).write_text(content)
                session = TutorialSession(companion, folder)
                self.assertIsNone(session.progress['current'])
                self.assertIn('Go in order', session.start())

    def test_the_place_you_stopped_is_offered_first(self):
        with tempfile.TemporaryDirectory() as folder:
            session = TutorialSession(companion, folder)
            session.start()
            session.words('email')
            course, lesson = session.lesson()
            self.assertEqual(course.key, 'email')
            for kind, value in solution(lesson.steps[0]):
                give(session, kind, value)
            self.assertEqual(session.step_index, 1)
            said, leave = session.words('stop tutorial')
            self.assertEqual(leave, 'main menu')
            self.assertIn('Your place is saved.', said)
            again = TutorialSession(companion, folder)
            first = again.start()
            self.assertIn('Continue where you stopped: Email, ' + lesson.title, first)
            said, _ = again.key('Enter')
            self.assertIn('Continuing where you stopped.', said)
            self.assertIn('Step 2 of', said)

    def test_go_in_order_starts_with_the_first_lesson_not_done(self):
        with tempfile.TemporaryDirectory() as folder:
            session = TutorialSession(companion, folder)
            session.progress['done'] = [session.lesson_id(0)]
            session.start()
            said, _ = session.words('go in order')
            self.assertEqual(session.position, 1)
            self.assertIn(session.order[1][1].title, said)


if __name__ == '__main__':
    unittest.main()
