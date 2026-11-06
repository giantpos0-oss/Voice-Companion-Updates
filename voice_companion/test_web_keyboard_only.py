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
