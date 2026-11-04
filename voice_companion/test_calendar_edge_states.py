"""Calendar and Contacts in empty and edge states (bug sweep, November 4, 2026).

Each test here failed before its fix. The simulated Thunderbird and the fixed clock
(Monday, October 26, 2026, five hours behind UTC) are those of test_calendar_screen.
"""
import unittest
from unittest import mock

import calendar_screen
import companion as app
import contacts_screen
import pim_sources
import thunderbird_pim
from test_calendar_contacts_sources import TWO, ContactsSourceHarness
from test_calendar_screen import CalendarHarness


class CalendarRemovedWhileOpenTests(CalendarHarness):
    """The calendar on screen is removed in Thunderbird while Calendar is open, then the person
    refreshes. Before, Companion said "All calendars is no longer in Thunderbird"."""
    thunderbird_env = TWO

    def test_the_removed_calendar_is_named(self):
        mode = self.open()
        app.handle('show Family calendar', mode)
        real = thunderbird_pim.calendars
        with mock.patch.object(thunderbird_pim, 'calendars', lambda: [c for c in real() if c.get('id') != 'cal-family']):
            app.handle('refresh', mode)
        self.assertTrue(self.said().startswith('Family, Gmail, me@gmail.com is no longer in Thunderbird, '
                                               'so all calendars are shown.'), self.said())
        self.assertEqual(calendar_screen.SOURCE, pim_sources.ALL)


class ContactsRemovedWhileOpenTests(ContactsSourceHarness):
    def test_the_removed_address_book_is_named(self):
        mode = self.open()
        app.handle('show Personal Address Book', mode)
        real = thunderbird_pim.contacts

        def without_it():
            answer = real()
            return dict(answer, books=[b for b in answer['books'] if b.get('id') != 'book-personal'],
                        contacts=[c for c in answer['contacts'] if c.get('bookId') != 'book-personal'])
        with mock.patch.object(thunderbird_pim, 'contacts', without_it):
            app.handle('refresh contacts', mode)
        self.assertIn('Personal Address Book is no longer in Thunderbird, so all address books are shown.', self.said())
        self.assertNotIn('All address books is no longer', self.said())
        self.assertEqual(contacts_screen.SOURCE, pim_sources.ALL)


class LocalAddressBookFileTests(unittest.TestCase):
    """The contacts saved on this computer (address-book.json). Before, a damaged file was written
    over by the next new contact, a file saved by Notepad with a byte order mark read as empty,
    and a file Windows held for a moment was replaced by a one-contact list."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def book(self):
        from address_book import AddressBook
        return AddressBook(self.root)

    def test_a_byte_order_mark_is_not_damage(self):
        import json
        self.book().path.write_text('\ufeff' + json.dumps({'ann': {'name': 'Ann', 'address': 'ann@example.com'}}), encoding='utf-8')
        self.assertEqual(self.book().get('Ann')['address'], 'ann@example.com')

    def test_a_damaged_file_is_kept_before_a_new_contact_is_saved(self):
        damaged = '{"ann": {"name": "Ann", "address": "ann@example.com"}, "bo'
        self.book().path.write_text(damaged, encoding='utf-8')
        self.book().save('Bob', 'bob@example.com')
        self.assertEqual(self.book().get('Bob')['address'], 'bob@example.com')
        kept = self.root / 'address-book.damaged.json'
        self.assertEqual(kept.read_text(encoding='utf-8'), damaged)

    def test_a_file_that_cannot_be_read_now_is_never_written_over(self):
        book = self.book()
        book.save('Ann', 'ann@example.com')
        before = book.path.read_text(encoding='utf-8')
        real = type(book.path).read_text

        def held(path, *args, **kwargs):
            if path == book.path:
                raise PermissionError(13, 'The file is in use')
            return real(path, *args, **kwargs)
        with mock.patch.object(type(book.path), 'read_text', held):
            with self.assertRaises(ValueError) as caught:
                book.save('Bob', 'bob@example.com')
            with self.assertRaises(ValueError):
                book.delete('Ann')
        self.assertNotIn('Errno', str(caught.exception))
        self.assertIn('Try again', str(caught.exception))
        self.assertEqual(book.path.read_text(encoding='utf-8'), before)

    def test_a_file_that_cannot_be_written_says_so_plainly(self):
        book = self.book()
        with mock.patch('address_book.write_text_atomic', side_effect=OSError(28, 'No space left on device')):
            with self.assertRaises(ValueError) as caught:
                book.save('Bob', 'bob@example.com')
        self.assertNotIn('Errno', str(caught.exception))
        self.assertFalse(book.path.exists())


if __name__ == '__main__':
    unittest.main()
