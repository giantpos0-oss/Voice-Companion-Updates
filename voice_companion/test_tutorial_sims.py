"""The tutorial's practice screens run the app's own code, and never reach your data,
the internet, or the real screens' state."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import calendar_screen
import companion
import contacts_screen
import document_reader
import youtube_screen
import tutorial_sims
from tutorial_sims import FileSim, MediaSim, NoteSim, ReaderSim, YouTubeSim, calendar_sim, contacts_sim


class PracticeScreenTests(unittest.TestCase):
    def test_contacts_and_calendar_are_private_copies(self):
        before = (list(contacts_screen.CONTACTS), contacts_screen.PENDING, calendar_screen.DAY, list(calendar_screen.EVENTS))
        book = contacts_sim(companion)
        for kind, value in (('key', 'Ctrl+N'), ('voice', 'Sam Rivera'), ('voice', 'sam@example.com'), ('key', 'Enter')):
            book.feed(kind, value)
        self.assertEqual([c.name for c in book.module.CONTACTS], ['Sam Rivera'])
        cal = calendar_sim(companion)
        self.assertIn('Doctor appointment', cal.opening)
        self.assertEqual(before, (list(contacts_screen.CONTACTS), contacts_screen.PENDING, calendar_screen.DAY,
                                  list(calendar_screen.EVENTS)))
        self.assertIsNot(book.module, contacts_screen)
        folders = [book.box.APP, cal.box.APP]
        book.close(); cal.close()
        self.assertFalse(any(f.exists() for f in folders))

    def test_contacts_never_ask_thunderbird(self):
        import thunderbird_pim
        with patch.object(thunderbird_pim, 'call', side_effect=AssertionError('real Thunderbird asked')), \
                patch.object(thunderbird_pim, 'usable', return_value=True):
            book = contacts_sim(companion)
            book.feed('key', 'Ctrl+N')
            book.close()

    def test_media_has_no_way_to_the_internet(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('internet used')):
            radio = MediaSim(companion, 'radio')
            self.assertIn('Found 2 stations', radio.feed('voice', 'search radio for jazz'))
            self.assertIn('Playing Jazz 24', radio.feed('voice', 'play station 1'))
            self.assertIn('Recording Jazz 24', radio.feed('voice', 'record station 1 for 30 minutes'))
            radio.close()
            podcasts = MediaSim(companion, 'podcast')
            podcasts.feed('voice', 'search podcasts for history')
            podcasts.feed('key', 'Enter'); podcasts.feed('key', 'Enter')
            said = podcasts.feed('voice', 'download this episode') or ''
            self.assertNotIn('Traceback', said)
            podcasts.close()

    def test_youtube_opens_no_browser(self):
        before = youtube_screen.SCREEN
        with patch('web_assistant.WebSession', side_effect=AssertionError('a browser opened')):
            sim = YouTubeSim(companion)
            for kind, value in (('key', 'Ctrl+F'), ('voice', 'coffee'), ('voice', 'confirm'), ('key', 'Enter'),
                                ('key', 'Space'), ('key', 'C'), ('key', 'Escape')):
                sim.feed(kind, value)
            self.assertIs(youtube_screen.SCREEN, before)
            sim.close()

    def test_file_manager_stays_on_the_practice_drive_in_memory(self):
        sim = FileSim(companion)
        for _ in range(4):
            sim.feed('key', 'Escape')
        self.assertIn(sim.manager.location, (None, tutorial_sims.PracticeFiles.ROOT))
        sim = FileSim(companion)
        sim.feed('key', 'End'); sim.feed('key', 'Delete'); sim.feed('key', 'Y')
        self.assertEqual(sim.files.actions, ['delete'])
        self.assertNotIn('Shopping list.txt', sim.files.tree[tutorial_sims.PracticeFiles.ROOT])

    def test_the_reader_keys_are_one_list_for_the_reader_and_the_tutorial(self):
        for key, command in document_reader.READER_KEYS.items():
            self.assertEqual(companion.navigation_key(key, 'file_reader'), command)
        for letter, kind in document_reader.QUICK_LETTERS:
            self.assertEqual(document_reader.READER_KEYS[letter], 'next ' + kind)
            self.assertEqual(document_reader.READER_KEYS['Shift+' + letter], 'previous ' + kind)
        sim = ReaderSim(companion)
        self.assertTrue(sim.feed('key', 'H').startswith('heading level'))
        sim.close()

    def test_a_practice_note_is_saved_only_in_its_own_folder(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(companion, 'APP', Path(folder)):
            sim = NoteSim(companion)
            sim.feed('voice', 'Buy milk.')
            self.assertEqual(sim.feed('key', 'Ctrl+S'), companion.NOTE_SAVED)
            self.assertEqual(list(Path(folder).iterdir()), [])
            sim.close()
            self.assertFalse(sim.folder.exists())


if __name__ == '__main__':
    unittest.main()


class ReviewFixTests(unittest.TestCase):
    """Found in review of 0.2.211: the practice screens must never start a program, read a real
    file, leave a folder behind, or stop the whole tutorial when one screen cannot be built."""
    # Every way the app can start a program, open a file or folder, or reach the network.
    BLOCKED = ('os.startfile', 'os.system', 'subprocess.Popen', 'subprocess.run', 'subprocess.call',
               'subprocess.check_call', 'subprocess.check_output', 'webbrowser.open', 'webbrowser.open_new',
               'webbrowser.open_new_tab', 'urllib.request.urlopen')
    # Keys a person might press on any practice screen, beyond what a step asks for.
    WANDER = ('End', 'Enter', 'Space', 'Delete', 'Y', 'Enter', 'Alt+Enter', 'Alt+Z', 'Alt+U', 'Ctrl+V', 'Home', 'Enter',
              'Escape', 'Enter')

    def blocked(self):
        import contextlib
        stack = contextlib.ExitStack()
        def refuse(*args, **kwargs):
            raise AssertionError('The tutorial tried to start a program, open a file or reach the internet.')
        for target in self.BLOCKED:
            stack.enter_context(patch(target, refuse, create=True))
        return stack

    def every_sim(self):
        from tutorial_lessons import build
        for course in build(companion):
            for lesson in course.lessons:
                yield lesson, lesson.make_sims()

    def test_no_practice_screen_starts_a_program_or_reaches_the_internet(self):
        with self.blocked():
            for lesson, sims in self.every_sim():
                for name, sim in sims.items():
                    for key in self.WANDER:
                        with self.subTest(lesson=lesson.title, sim=name, key=key):
                            sim.feed('key', key)
                    sim.close()

    def test_the_downloads_screen_says_what_would_open(self):
        with self.blocked():
            sim = tutorial_sims.downloads_sim(companion)
            sim.feed('key', 'End')
            said = sim.feed('key', 'Enter')
            sim.close()
        self.assertIn('Family photos.zip', said)
        self.assertIn('Here, nothing opens.', said)

    def test_file_manager_never_reads_a_real_path(self):
        with patch('document_reader.open_document', side_effect=AssertionError('a real path was read')), \
                patch('zipfile.ZipFile', side_effect=AssertionError('a real zip was opened')):
            sim = FileSim(companion)
            sim.feed('key', 'End')
            said = sim.feed('key', 'Enter')
            self.assertIn('Shopping list.txt', said)
            for key in ('Alt+Z', 'Alt+U', 'Alt+Enter'):
                sim.feed('key', key)
            sim.close()

    def test_no_folder_is_left_behind(self):
        import tutorial_engine
        root = Path(tempfile.gettempdir())
        def practice_folders():
            return {p for p in root.iterdir() if p.name.startswith('vc-tutorial')}
        before = practice_folders()
        with tempfile.TemporaryDirectory() as progress:
            session = tutorial_engine.TutorialSession(companion, progress)
            self.assertEqual(practice_folders() - before, set(), 'building the lessons left folders')
            for position in range(len(session.order)):
                session.begin(position)
                session.close_sims()
                self.assertEqual(practice_folders() - before, set(), session.order[position][1].title)
            session.begin(0)
            session.stop()
            self.assertEqual(practice_folders() - before, set())

    def test_a_practice_screen_that_cannot_be_built_says_so_and_the_rest_work(self):
        import tutorial_engine
        def broken(*args, **kwargs):
            raise ImportError('no code for this module')
        with patch.object(tutorial_sims, 'private', broken):
            session = tutorial_engine.TutorialSession(companion)
            session.start()
            said, _ = session.words('address manager')
            self.assertIn('This lesson could not start', said)
            self.assertIn('Say next lesson', said)
            self.assertEqual(session.state, 'between')
            said, _ = session.words('lesson list')
            said, _ = session.words('word processor')
            self.assertIn('Step 1 of', said)
