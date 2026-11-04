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


if __name__ == '__main__':
    unittest.main()
