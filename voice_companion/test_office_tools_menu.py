"""The main menu groups the apps (Will, November 5, 2026).

Office tools holds Email, Word processor, Notepad, Document reader, Calendar, Contacts and
File manager. Web browser and Media stay on the main menu. Shut down or restart holds the two
power choices. Leaving an app opened from Office tools goes back to Office tools; Main menu and
Control+F1 still go to the main menu."""
import unittest
from unittest import mock

import companion
from test_core_email_fixes import CompanionTestCase


class OfficeToolsMenuTests(CompanionTestCase):
    def setUp(self):
        super().setUp()
        for name, value in dict(TASK_NAV=None, NAMED_LIST=None, OPEN_NOTE=None, OFFICE_RETURN=False,
                                MAIN_MENU_INDEX=None).items():
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'note_buffer', []); p.start(); self.addCleanup(p.stop)

    def key(self, key, mode):
        request = companion.navigation_key(key, mode)
        return mode if request is None else companion.handle(request, mode)

    def open_office(self):
        mode = companion.handle('office tools', 'awake')
        self.assertEqual(mode, 'office_menu')
        return mode

    def test_main_menu_is_grouped(self):
        self.assertEqual([name for name, _ in companion.MAIN_MENU_CHOICES],
                         ['Office tools', 'Web browser', 'Media', 'Options', 'Check for updates', 'Help',
                          'Shut down or restart', 'Exit Voice Companion'])

    def test_office_tools_lists_the_office_apps(self):
        self.open_office()
        self.assertTrue(self.said[-1].startswith('Office tools. Email'), self.said[-1])
        names = [name for name, _, _ in companion.task_navigation().items('office_menu')]
        self.assertEqual(names, ['Email', 'Word processor', 'Notepad', 'Document reader', 'Calendar', 'Contacts',
                                 'File manager'])

    def test_enter_on_the_main_menu_opens_office_tools(self):
        mode = self.key('Home', 'awake')
        self.assertTrue(self.said[-1].startswith('Office tools'), self.said[-1])
        self.assertEqual(self.key('Enter', mode), 'office_menu')

    def test_spoken_variants_open_office_tools(self):
        for said in ('Office tools.', 'open office tools', 'Go to Office tools.'):
            self.assertEqual(companion.handle(said, 'awake'), 'office_menu', said)

    def test_arrows_letters_and_ends(self):
        mode = self.open_office()
        self.key('Up', mode)
        self.assertTrue(self.said[-1].startswith('Start of list.'), self.said[-1])
        self.key('End', mode)
        self.assertTrue(self.said[-1].startswith('File manager'), self.said[-1])
        self.key('Letter:W', mode)
        self.assertTrue(self.said[-1].startswith('Word processor'), self.said[-1])

    def test_escape_from_office_tools_goes_to_the_main_menu(self):
        self.assertEqual(self.key('Escape', self.open_office()), 'awake')
        self.assertIn('Main menu', self.said[-1])

    def test_leaving_an_app_goes_back_to_office_tools_on_the_same_item(self):
        mode = self.open_office()
        self.key('Down', mode)                       # Word processor
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'word_processor')
        mode = self.key('Escape', mode)
        self.assertEqual(mode, 'office_menu')
        self.assertTrue(self.said[-1].startswith('Office tools. Word processor'), self.said[-1])
        # Then Escape again: the main menu.
        self.assertEqual(self.key('Escape', mode), 'awake')

    def test_notepad_back_to_office_tools(self):
        mode = self.open_office()
        mode = self.key('Letter:N', mode)
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'notepad_menu')
        self.assertEqual(self.key('Escape', mode), 'office_menu')

    def test_main_menu_and_control_f1_still_go_to_the_main_menu(self):
        for leave in ('main menu', 'Ctrl+F1'):
            mode = self.open_office()
            self.key('Down', mode)
            mode = self.key('Enter', mode)
            self.assertEqual(mode, 'word_processor')
            mode = self.key('Ctrl+F1', mode) if leave == 'Ctrl+F1' else companion.handle('Main menu.', mode)
            self.assertEqual(mode, 'awake', leave)
            self.assertFalse(companion.OFFICE_RETURN)

    def test_apps_opened_from_the_main_menu_by_voice_still_return_there(self):
        mode = companion.handle('word processor', 'awake')
        self.assertEqual(mode, 'word_processor')
        self.assertEqual(self.key('Escape', mode), 'awake')

    def test_going_to_the_web_ends_the_way_back(self):
        companion.OFFICE_RETURN = True
        companion.office_return('web browser', 'word_processor', 'browser_menu')
        self.assertFalse(companion.OFFICE_RETURN)

    def test_every_office_app_comes_back_to_office_tools(self):
        for index, opened in ((5, 'contacts'), (6, 'files'), (3, 'reader_menu')):
            companion.OFFICE_RETURN = False
            mode = self.open_office()
            companion.task_navigation().indices['office_menu'] = index
            mode = self.key('Enter', mode)
            self.assertEqual(mode, opened)
            # The File manager goes up one folder at a time, then out of the drive list.
            for _ in range(10):
                mode = self.key('Escape', mode)
                if mode != opened: break
            self.assertEqual(mode, 'office_menu', opened)

    def test_email_with_no_account_cancel_goes_back_to_office_tools(self):
        mode = self.key('Enter', self.open_office())          # Email
        self.assertTrue(companion.account_setup)
        mode = self.key('Escape', mode)
        self.assertEqual(mode, 'office_menu')
        self.assertTrue(self.said[-1].startswith('Account setup canceled. Office tools. Email'), self.said[-1])

    def test_an_app_that_cannot_open_keeps_you_in_office_tools(self):
        mode = self.open_office()
        companion.task_navigation().indices['office_menu'] = 4   # Calendar, Thunderbird not set up here
        with mock.patch('calendar_screen.handle', side_effect=lambda m, text, mode, typed: (m.speak('Thunderbird is not set up yet.'), 'awake')[1] if m.normalized_command(text) == 'calendar' else None):
            mode = self.key('Enter', mode)
        self.assertEqual(mode, 'office_menu')
        self.assertEqual(self.said[-1], 'Thunderbird is not set up yet.')

    def test_shut_down_or_restart_groups_the_power_choices(self):
        mode = companion.handle('shut down or restart', 'awake')
        self.assertEqual(mode, 'power_menu')
        self.assertTrue(self.said[-1].startswith('Shut down or restart. Shut down the computer'), self.said[-1])
        names = [name for name, _, _ in companion.task_navigation().items('power_menu')]
        self.assertEqual(names, ['Shut down the computer', 'Restart the computer'])
        self.assertEqual(self.key('Escape', mode), 'awake')

    def test_power_choice_still_asks_first(self):
        mode = companion.handle('power menu', 'awake')
        self.key('Down', mode)
        self.assertEqual(self.key('Enter', mode), 'power_confirm')
        self.assertIn('Restart the computer?', self.said[-1])

    def test_old_direct_commands_still_work_from_the_main_menu(self):
        self.assertEqual(companion.handle('notepad', 'awake'), 'notepad_menu')
        self.assertEqual(companion.handle('restart computer', 'awake'), 'power_confirm')


if __name__ == '__main__':
    unittest.main()
