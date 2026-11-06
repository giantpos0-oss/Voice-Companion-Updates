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


if __name__ == '__main__':
    unittest.main()
