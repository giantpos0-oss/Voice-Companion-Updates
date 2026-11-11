"""Shortcut keys pressed in a text box do their job and never type their command words.

Will, November 10, 2026: in the YouTube search box, Alt+O typed "open options" into the
box and searched for it, as if Enter had been pressed. A key is sent to Companion as
command words; a box that takes typed words took those words as a search.
"""
import io
import queue
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import youtube_screen as ys


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        import companion as app
        self.app = app
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.window = Mock(commands=queue.Queue())
        defaults = {'APP': self.root, 'TEXT_MODE': True, 'APP_WINDOW': self.window, 'INPUT_MODE': 'mixed', 'document': None,
                    'email_draft': None, 'mail_session': None, 'web_session': None, 'pending_website': None,
                    'pending_send': None, 'NAMED_LIST': None, 'account_setup': False, 'MAIN_MENU_INDEX': None,
                    'SYNTH_PICK_INDEX': None, 'VOICE_PICK_INDEX': None, 'help_session': None, 'tutorial_session': None,
                    'MEDIA_HUB': None, 'PREFERENCES': dict(app.PREFERENCES), 'SLEEP_RETURN_MODE': 'awake',
                    'FILE_READER': None, 'FILE_MANAGER': None, 'TASK_NAV': None, 'SCREEN_MENU': None, 'ACCOUNT_PICKER': None,
                    'ACCOUNT_ENTRY': None, 'THUNDERBIRD_SETUP': None, 'CONFIRM_CHOICE': 'yes', 'note_buffer': [],
                    'KEYBOARD_SPEECH': None, 'UI_CONTEXT_CACHE': None}
        for name, value in defaults.items():
            self.stack.enter_context(patch.object(app, name, value, create=True))
        self.said = []
        speak = lambda text, *a, **k: self.said.append(str(text))
        for name in ('speak', 'speak_prompt', 'dictation_feedback', 'speak_status'):
            self.stack.enter_context(patch.object(app, name, side_effect=speak))
        self.stack.enter_context(patch.object(app, 'interrupt_speech'))
        self.stack.enter_context(patch.object(app, 'sync_app_context'))
        self.options = self.stack.enter_context(patch.object(app, 'open_settings', return_value='settings'))
        self.stack.enter_context(patch.object(ys, 'SCREEN', None))
        self.searched = []
        self.stack.enter_context(patch.object(ys.YouTubeScreen, 'search',
                                              lambda screen, query=None: self.searched.append(query) or 'Results.'))
        self.stack.enter_context(patch.object(ys.YouTubeScreen, 'go', side_effect=AssertionError('browser started')))

    def keys(self, mode, *keys):
        for key in keys:
            self.window.commands.put(('keyboard', key))
        return self.app.process_keyboard_batch(mode)

    def youtube_search_box(self):
        self.assertEqual(self.app.handle('YouTube.', 'media_menu'), 'youtube')
        self.assertEqual(self.keys('youtube', 'Ctrl+F'), 'youtube')
        s = ys.screen(self.app)
        self.assertTrue(s.asking)
        return s

    def test_alt_o_in_the_youtube_search_box_opens_options_and_never_searches(self):
        s = self.youtube_search_box()
        self.assertEqual(self.keys('youtube', 'settings'), 'settings')   # Alt+O
        self.options.assert_called_once_with('youtube')
        self.assertEqual(self.searched, [])
        self.assertNotIn('open options', s.entry[1] if s.entry else '')
        self.assertFalse(any('Searching' in text or 'open options' in text.lower() for text in self.said), self.said)
        # The box is still open for the search when Options closes.
        self.assertTrue(s.asking)

    def test_typed_words_open_options_still_search_in_the_youtube_box(self):
        # Words typed and sent with Enter are a search, even these words.
        s = self.youtube_search_box()
        self.assertEqual(self.app.handle_keyboard('open options', 'youtube'), 'youtube')
        self.assertEqual(self.searched, ['open options'])
        self.options.assert_not_called()
        self.assertFalse(s.asking)

    def test_alt_o_on_the_youtube_lists_still_opens_options(self):
        self.assertEqual(self.app.handle('YouTube.', 'media_menu'), 'youtube')
        self.assertEqual(self.keys('youtube', 'settings'), 'settings')
        self.options.assert_called_once_with('youtube')

    def test_alt_o_in_yahoo_setup_says_setup_is_open(self):
        # It said "That is not a complete email address": the words "open options" were the address.
        with patch.object(self.app, 'ACCOUNT_ENTRY', {'provider': 'yahoo', 'step': 'address'}):
            self.assertEqual(self.keys('awake', 'settings'), 'awake')
            self.assertEqual(self.app.ACCOUNT_ENTRY, {'provider': 'yahoo', 'step': 'address'})
        self.options.assert_not_called()
        self.assertEqual(self.said[-1], 'Yahoo setup is open. Finish it, or press Escape to cancel.')

    def test_alt_o_in_an_answer_box_never_becomes_the_answer(self):
        # A contact's name, a station's speed: "open options" became the answer.
        nav = self.app.task_navigation()
        handled = []
        with patch.object(nav, 'prompt', ('@contacts:add-name {value}', 'contacts')), \
                patch.object(self.app, 'handle', wraps=self.app.handle) as handle:
            self.assertEqual(self.keys('task_input', 'settings'), 'settings')
            handled = [str(call.args[0]) for call in handle.call_args_list]
            self.assertEqual(nav.prompt, ('@contacts:add-name {value}', 'contacts'))   # still asking
        self.options.assert_called_once_with('task_input')
        self.assertFalse(any('open options' in text for text in handled), handled)

    def test_alt_o_in_the_favorite_name_box_never_names_a_favorite(self):
        session = Mock(); session.menu.level = 'name'
        with patch.object(self.app, 'web_session', session), patch.object(self.app, 'handle_browser_menu') as named:
            self.assertEqual(self.keys('browser_menu', 'settings'), 'settings')
        named.assert_not_called()
        self.options.assert_called_once_with('browser_menu')

    def test_alt_o_in_the_file_rename_box_never_renames(self):
        manager = Mock(pending=('rename', [str(self.root / 'a.txt')]), busy=False)
        with patch.object(self.app, 'FILE_MANAGER', manager):
            self.assertEqual(self.keys('files', 'settings'), 'settings')
        manager.process.assert_not_called()
        self.options.assert_called_once_with('files')

    def test_alt_f4_closes_companion_from_every_screen(self):
        # Alt+F4 (and the window's Close button) did nothing on YouTube, Contacts, Calendar,
        # Downloads, Attachments, File manager and the document reader.
        for mode in ('youtube', 'contacts', 'calendar', 'downloads', 'attachments', 'files', 'file_reader'):
            with self.subTest(mode=mode):
                self.assertEqual(self.app.navigation_key('Alt+F4', mode), 'exit companion')
        self.youtube_search_box()
        self.assertEqual(self.app.navigation_key('Alt+F4', 'youtube'), 'exit companion')


if __name__ == '__main__':
    unittest.main()
