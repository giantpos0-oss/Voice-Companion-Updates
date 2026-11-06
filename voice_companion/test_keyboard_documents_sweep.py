"""Nightly sweep, November 6, 2026: Word processor, Notepad, Document reader and File manager
used with the keyboard only, as a blind user who never speaks a command."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import companion as app
from file_manager import FileManager
from test_file_manager import FakeFiles, settle


class FileManagerKeys(unittest.TestCase):
    """Keys pressed on the File manager screen go through the app, as the window sends them."""
    files = ('a.txt', 'b.txt')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in self.files:
            (self.root / name).write_text('x')
        self.backend = FakeFiles(self.root)
        self.fm = FileManager(self.backend)
        self.fm.refresh()
        settle(self.fm)
        self.fm.command('enter')
        settle(self.fm)
        self.spoken = []
        for patcher in (patch.object(app, 'FILE_MANAGER', self.fm), patch.object(app, 'APP_WINDOW', None),
                        patch.object(app, 'speak', self.say),
                        patch.object(app, 'sync_app_context'), patch.object(app, 'CONFIRM_CHOICE', 'no'),
                        patch.object(app, 'LAST_YES_NO', '')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def say(self, text, *args, **kwargs):
        app.remember_question(text)
        self.spoken.append(text)

    def key(self, key):
        """Press one key; return what was said."""
        self.spoken.clear()
        request = app.navigation_key(key, 'files')
        if request:
            app.handle(request, 'files')
        notices = settle(self.fm)
        return ' '.join(self.spoken + ([notices] if notices else []))

    def typed(self, text):
        """Type into the box File manager shows (a new name or a search), then press Enter."""
        self.spoken.clear()
        app.handle_keyboard(text, 'files')
        notices = settle(self.fm)
        return ' '.join(self.spoken + ([notices] if notices else []))


class DeleteQuestionKeys(FileManagerKeys):
    def test_y_deletes_and_n_keeps_as_on_every_other_question(self):
        # The window sends a letter as "Letter:" and the character, upper case with Shift.
        # Y and N did nothing at all here, and said nothing.
        self.assertIn('Say Yes or No', self.key('Delete'))
        said = self.key('Letter:n')
        self.assertIn('canceled', said)
        self.assertIsNone(self.fm.pending)
        self.assertEqual(self.backend.actions, [])
        self.key('Delete')
        self.key('Letter:Y')
        self.assertEqual(self.backend.actions[0][0], 'delete')

    def test_f1_says_the_question_again(self):
        # Will, October 31, 2026: F1 in a yes or no question says the question again. Here it was silent.
        question = self.key('Delete')
        self.assertEqual(self.key('F1'), question)
        self.assertEqual(self.fm.pending[0], 'delete')
        self.assertEqual(self.backend.actions, [])


if __name__ == '__main__':
    unittest.main()
