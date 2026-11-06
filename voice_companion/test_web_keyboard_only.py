"""Web pages used with the keyboard only (sweep, November 6, 2026)."""
import unittest

from web_browse import QUICK_KEYS, BrowseCursor, page_quick_key


class ShiftNumberQuickKeyTests(unittest.TestCase):
    """The guide: "Numbers 1 to 6 go to a heading at that level. Hold Shift with any of
    them to move back." Shift and a number key types "!" or "@", not a number."""

    def test_every_letter_and_number_is_a_quick_key(self):
        for letter in QUICK_KEYS:
            self.assertEqual(page_quick_key(letter, letter, 0, False), letter)
            self.assertEqual(page_quick_key(letter.upper(), letter.upper(), 0, True), letter)
        for number in '123456':
            self.assertEqual(page_quick_key(number, number, 0, False), number)
        for char, keysym in (('7', '7'), ('z', 'z'), ('', 'F5'), (' ', 'space')):
            self.assertIsNone(page_quick_key(char, keysym, 0, False))

    def test_shift_and_a_number_moves_to_the_previous_heading_at_that_level(self):
        for number, keysym, char in (('1', 'exclam', '!'), ('2', 'at', '@'), ('3', 'numbersign', '#'),
                                     ('4', 'dollar', '$'), ('5', 'percent', '%'), ('6', 'asciicircum', '^')):
            with self.subTest(number=number):
                self.assertEqual(page_quick_key(char, keysym, 0, True), number)
                # Some systems name the key by the mark it types.
                self.assertEqual(page_quick_key(char, char, 0, True), number)

    def test_shift_and_a_number_works_on_any_keyboard_layout_on_windows(self):
        # A British keyboard types a quotation mark with Shift+2 and a pound sign with Shift+3.
        # Windows reports the number key itself (key codes 49 to 54) on every layout.
        self.assertEqual(page_quick_key('"', 'quotedbl', 50, True, windows=True), '2')
        self.assertEqual(page_quick_key('\xa3', 'sterling', 51, True, windows=True), '3')
        # Shift+7 is not a heading level; key codes mean other keys away from Windows.
        self.assertIsNone(page_quick_key('&', 'ampersand', 55, True, windows=True))
        self.assertIsNone(page_quick_key('Z', 'Z', 52, True, windows=False))

    def test_shift_number_reaches_the_previous_heading(self):
        cursor = BrowseCursor({'elements': [
            dict(key='a', role='heading', level=1, label='Top', start=0, end=3),
            dict(key='b', role='heading', level=2, label='Middle', start=4, end=10),
            dict(key='c', role='heading', level=1, label='Bottom', start=11, end=17)]})
        cursor.index = 2
        self.assertEqual(cursor.move(page_quick_key('!', 'exclam', 0, True), True), 'Top, heading level 1.')


class FormQuestionEscapeTests(unittest.TestCase):
    """F8 lists the fields; Enter on one asks for its answer ("Field 1: First. What should
    I enter?"). Escape there left the page for the web browser menu, and the form questions
    were dropped without a word. Escape now stops the questions and stays on the page;
    the next Escape opens the web browser menu, one level at a time."""

    def session(self):
        import tempfile
        from unittest.mock import Mock
        from web_assistant import WebSession
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        session = WebSession(folder.name, Mock()); session.injected_backend = True
        session._sync_browser_tab = lambda: None
        first = dict(key='a', role='field', tag='input', type='text', label='First', start=0, end=5)
        session.snapshot = {'url': 'https://example.com/', 'text': 'First, edit', 'elements': [first], 'controls': [first]}
        session.browse = BrowseCursor(session.snapshot)
        session._form_controls = lambda snapshot: [first]
        return session

    def test_escape_in_a_form_question_stops_the_questions_and_stays_on_the_page(self):
        from unittest.mock import patch
        import companion as app
        session = self.session()
        said = []
        with patch.object(app, 'web_session', session), patch.object(app, 'speak', said.append), \
                patch.object(app, 'interrupt_speech', lambda *a: None), patch.object(app, 'NAMED_LIST', None):
            self.assertIn('Found 1 field', session.fields())
            self.assertIn('What should I enter?', app.handle_keyboard(app.navigation_key('Enter', 'web'), 'web') and said[-1])
            self.assertEqual(session.form_index, 0)
            command = app.navigation_key('Escape', 'web')
            self.assertEqual(command, 'cancel form')
            self.assertEqual(app.handle_keyboard(command, 'web'), 'web')
            self.assertEqual(said[-1], 'Stopped filling the form. Entries already made remain on the page; nothing was submitted.')
            self.assertIsNone(session.form_index)
            # Nothing else is open now: Escape opens the web browser menu.
            self.assertEqual(app.navigation_key('Escape', 'web'), 'web browser menu')


class WebPageMenuKeyTests(unittest.TestCase):
    def test_top_and_bottom_of_page_show_their_keys(self):
        # The guide: "To reach the top or bottom, ... press Control+Home or Control+End."
        # The Web page menu named no key for them, so a keyboard user never learned it there.
        from screen_menus import items
        keys = {label: key for group, label, key, command in items('web')}
        self.assertEqual(keys['Top of page'], 'Ctrl+Home')
        self.assertEqual(keys['Bottom of page'], 'Ctrl+End')
        guide = open('START HERE - Veteran.txt', encoding='utf-8').read()
        self.assertIn('press Control+Home or Control+End', guide)


class SecondTryToLeaveTests(unittest.TestCase):
    """A page with unsaved changes stays open once; the next try leaves it. Just after the first
    try, Chromium can stop the second at once with net::ERR_ABORTED and never ask the page.
    The user then heard "The page did not open. Check the address and internet connection."
    (seen in about 1 run in 10 of the live test, with Back and the browser's page cache)."""

    def backend(self, *results):
        import tempfile, time
        from unittest.mock import Mock
        from web_assistant import BrowserBackend
        backend = BrowserBackend(tempfile.gettempdir()); backend.start = lambda: None
        backend.page = Mock(); backend.page.goto.side_effect = list(results)
        backend.leave_asked = time.monotonic()   # the page stayed open a moment ago
        return backend

    def test_a_stale_stop_after_the_page_stayed_open_is_tried_again(self):
        backend = self.backend(Exception('Page.goto: net::ERR_ABORTED at https://fixture.test/next'), None)
        backend.goto('https://fixture.test/next')
        self.assertEqual(backend.page.goto.call_count, 2)

    def test_other_failures_and_a_new_refusal_are_not_tried_again(self):
        from web_assistant import LEAVE_NOTICE
        backend = self.backend(Exception('net::ERR_NAME_NOT_RESOLVED'), None)
        with self.assertRaises(Exception): backend.goto('https://fixture.test/next')
        self.assertEqual(backend.page.goto.call_count, 1)
        # The page asked again and stayed open: that is said, not overridden.
        backend = self.backend(Exception('net::ERR_ABORTED'), None); backend.dialog_notice = LEAVE_NOTICE
        with self.assertRaises(Exception): backend.goto('https://fixture.test/next')
        self.assertEqual(backend.page.goto.call_count, 1)
        # No page stayed open lately: an ordinary stop is reported as before.
        backend = self.backend(Exception('net::ERR_ABORTED'), None); backend.leave_asked = float('-inf')
        with self.assertRaises(Exception): backend.goto('https://fixture.test/next')
        self.assertEqual(backend.page.goto.call_count, 1)


if __name__ == '__main__':
    unittest.main()
