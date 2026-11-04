"""Empty and edge states in the guided browser (sweep, November 4, 2026).

Each test records something a person heard that was wrong or left them stuck."""
import tempfile
import unittest
from unittest.mock import Mock, patch

from web_browse import BrowseCursor
from web_assistant import WebSession


class EmptyTableTests(unittest.TestCase):
    def test_arrows_in_an_empty_table_say_it_is_empty(self):
        # T said "Table." and then every arrow said "Move to a table with T first."
        # The person had just done that.
        cursor = BrowseCursor({'elements': [{'key': 't1', 'role': 'table', 'tag': 'table', 'label': '', 'start': 0, 'end': 0}]})
        self.assertEqual(cursor.move('t'), 'Table.')
        for key in ('Down', 'Up', 'Right', 'Left', 'Home', 'End', 'Prior', 'Next'):
            self.assertEqual(cursor.table_move(key), 'This table is empty.')

    def test_arrows_away_from_any_table_still_say_to_press_t(self):
        cursor = BrowseCursor({'elements': [{'key': 'p', 'role': 'paragraph', 'tag': 'p', 'label': 'Words', 'start': 0, 'end': 5}]})
        self.assertEqual(cursor.table_move('Down'), 'Move to a table with T first.')


class DialogWithoutButtonsTests(unittest.TestCase):
    """A page dialog that Escape does not close. Escape always went to the page, so a
    dialog with no buttons trapped the keyboard, and the message named a Close button
    that was not there."""

    def session(self, elements):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        session = WebSession(folder.name, Mock())
        session.injected_backend = True
        session._sync_browser_tab = lambda: None
        session.snapshot = {'url': 'https://example.com/', 'text': 'Please wait', 'elements': elements, 'modal_key': 'm1'}
        session._refresh = Mock(return_value='Please wait')   # the page keeps its dialog
        return session

    def test_a_dialog_with_no_buttons_does_not_send_you_to_a_close_button(self):
        session = self.session([{'key': 'p', 'role': 'paragraph', 'tag': 'p', 'label': 'Please wait', 'start': 0, 'end': 11}])
        said = session.keyboard('Escape')
        self.assertNotIn('Close button.', said.replace('no Close button', ''))
        self.assertEqual(said, 'Dialog remains open. It has no Close button. Press Escape again for the web browser menu.')

    def test_a_dialog_with_a_button_names_it_and_offers_the_way_out(self):
        session = self.session([{'key': 'b', 'role': 'button', 'tag': 'button', 'label': 'Close', 'start': 0, 'end': 5}])
        self.assertEqual(session.keyboard('Escape'),
                         'Dialog remains open. Move to its Close button, or press Escape again for the web browser menu.')

    def test_a_second_escape_on_the_same_dialog_opens_the_web_browser_menu(self):
        import companion as app
        session = self.session([])
        with patch.object(app, 'web_session', session), patch.object(app, 'interrupt_speech'):
            self.assertEqual(app.navigation_key('Escape', 'web'), 'web key Escape')
            session.keyboard('Escape')
            self.assertEqual(app.navigation_key('Escape', 'web'), 'web browser menu')
            # Another key in between: Escape tries the dialog again first.
            session.keyboard('Quick:k')
            self.assertEqual(app.navigation_key('Escape', 'web'), 'web key Escape')


class DownloadFolderNameTests(unittest.TestCase):
    """A download folder at the top of a drive, such as a USB stick (E:\\), has no
    folder name. The empty Downloads list said "Files you download are saved in . "."""

    def test_a_drive_is_named_as_a_drive(self):
        from downloads import folder_words
        from pathlib import PureWindowsPath
        self.assertEqual(folder_words(PureWindowsPath('E:\\')), 'drive E')
        self.assertEqual(folder_words(PureWindowsPath('C:\\Users\\Will\\Downloads')), 'Downloads')

    def test_the_empty_list_names_the_drive(self):
        import download_screen
        from pathlib import PureWindowsPath
        model = Mock(items=[]); model.folder.return_value = PureWindowsPath('E:\\')
        with patch.object(download_screen, 'manager', return_value=model):
            self.assertEqual(download_screen.describe(Mock()),
                             'No downloads yet. Files you download are saved in drive E. Escape goes back.')


class HiddenChromeAtExitTests(unittest.TestCase):
    """Options, Web browser, Your own Chrome window: "Hide it while Companion uses it".
    When Companion closed, a Chrome window it had hidden stayed off the screen, the
    taskbar and Alt+Tab. It is the person's own Chrome, and nothing could bring it back."""

    def test_exit_puts_hidden_chrome_back_without_taking_the_keyboard(self):
        import own_chrome_window
        from test_own_chrome_window import FakeDesktop
        desktop = FakeDesktop([7])
        windows = own_chrome_window.OwnChromeWindows(desktop=lambda: desktop, sleep=lambda s: None)
        self.addCleanup(setattr, own_chrome_window, 'ENABLED', False)
        own_chrome_window.ENABLED = True
        before = windows.current()
        desktop.open[42] = {'style': 0x100, 'pos': (300, 200), 'parked': False}
        windows.opened(before)
        self.assertTrue(desktop.open[42]['parked'])
        with patch.object(own_chrome_window, 'WINDOWS', windows):
            own_chrome_window.restore_at_exit()
        self.assertFalse(desktop.open[42]['parked'])
        self.assertEqual(desktop.open[42]['pos'], (300, 200))
        self.assertEqual(desktop.forward, [])   # back on the taskbar, not pulled in front

    def test_restore_is_registered_to_run_at_exit_once_a_window_is_hidden(self):
        import own_chrome_window
        from test_own_chrome_window import FakeDesktop
        desktop = FakeDesktop([42])
        windows = own_chrome_window.OwnChromeWindows(desktop=lambda: desktop, sleep=lambda s: None)
        windows.mine.add(42)
        with patch('atexit.register') as register, patch.object(own_chrome_window, 'EXIT_WATCHED', False):
            windows.hide()
            windows.hide()
        register.assert_called_once_with(own_chrome_window.restore_at_exit)


if __name__ == '__main__':
    unittest.main()
