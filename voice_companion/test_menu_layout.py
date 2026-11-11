"""Main menu layout and how it is announced (Will, November 10, 2026).

- Web browser moved into a new Web tools group on the main menu, with the other web
  places: Web favorites, Web history, Downloads and Set up Chrome. "Web browser" still
  opens the web browser from anywhere.
- Arriving on the main menu says only the item you are on, the way a BrailleSense does:
  "File manager (F), 1 of 10." F1 and "Main menu" go to the first item. Escape from a
  group on the main menu (Office tools, Web tools, Media...) lands on that group's item.
- The very first startup words still say "You are on the main menu."
"""
import unittest
from unittest import mock

import companion
import task_navigation
from test_core_email_fixes import CompanionTestCase


FIRST_ITEM = 'File manager (F), 1 of 10.'


class MenuLayoutCase(CompanionTestCase):
    def setUp(self):
        super().setUp()
        for name, value in dict(TASK_NAV=None, NAMED_LIST=None, OPEN_NOTE=None, OFFICE_RETURN=False,
                                MAIN_MENU_INDEX=None, MAIN_MENU_LEAD='', web_session=None,
                                FAVORITES_AFTER=False).items():
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'note_buffer', []); p.start(); self.addCleanup(p.stop)

    def key(self, key, mode):
        request = companion.navigation_key(key, mode)
        return mode if request is None else companion.handle(request, mode)


class WebToolsMenuTests(MenuLayoutCase):
    def test_main_menu_has_web_tools_in_place_of_web_browser(self):
        self.assertEqual([name for name, _ in companion.MAIN_MENU_CHOICES],
                         ['File manager', 'Office tools', 'Organizer', 'Web tools', 'Media', 'Options',
                          'Check for updates', 'Help', 'Shut down or restart', 'Exit Voice Companion'])

    def test_web_tools_lists_the_web_places(self):
        mode = companion.handle('web tools', 'awake')
        self.assertEqual(mode, 'web_tools_menu')
        self.assertEqual(self.said[-1], 'Web tools. Web browser (W), 1 of 5.')
        names = [name for name, _, _ in companion.task_navigation().items('web_tools_menu')]
        self.assertEqual(names, ['Web browser', 'Web favorites', 'Web history', 'Downloads', 'Set up Chrome'])

    def test_spoken_variants_open_web_tools(self):
        for said in ('Web tools.', 'open web tools', 'Go to web tools.', 'web tools menu'):
            self.assertEqual(companion.handle(said, 'awake'), 'web_tools_menu', said)

    def test_enter_on_web_tools_from_the_main_menu(self):
        mode = self.key('F1', 'awake')
        for _ in range(3):
            mode = self.key('Down', mode)
        self.assertTrue(self.said[-1].startswith('Web tools (W), 4 of 10.'), self.said[-1])
        self.assertEqual(self.key('Enter', mode), 'web_tools_menu')

    def test_web_browser_still_opens_from_anywhere(self):
        with mock.patch.object(companion, 'open_browser_menu', return_value='browser_menu') as opened:
            for mode in ('awake', 'office_menu', 'web_tools_menu', 'media_menu'):
                self.assertEqual(companion.handle('Web browser.', mode), 'browser_menu', mode)
        self.assertEqual(opened.call_count, 4)

    def test_web_tools_items_run_their_commands(self):
        expected = {'Web browser': 'web browser', 'Web favorites': 'list favorites', 'Web history': 'web history',
                    'Downloads': 'download manager', 'Set up Chrome': 'set up chrome'}
        self.assertEqual({name: command for name, _, command in task_navigation.WEB_TOOLS}, expected)

    def test_leaving_the_browser_menu_goes_back_to_web_tools(self):
        mode = companion.handle('web tools', 'awake')
        with mock.patch.object(companion, 'open_browser_menu', return_value='browser_menu'):
            mode = self.key('Enter', mode)
        self.assertEqual(mode, 'browser_menu')
        self.assertEqual(companion.OFFICE_RETURN, 'web_tools_menu')
        # A web page and search are part of Web tools: the way back is kept.
        companion.office_return('go to va.gov', 'browser_menu', 'web')
        self.assertEqual(companion.OFFICE_RETURN, 'web_tools_menu')
        with mock.patch.object(companion, 'handle_browser_menu', return_value='awake'):
            companion.web_session = mock.Mock()
            companion.web_session.menu.level = 'menu'
            mode = companion.handle('escape', 'browser_menu')
        self.assertEqual(mode, 'web_tools_menu')
        self.assertEqual(self.said[-1], 'Web tools. Web browser (W), 1 of 5.')

    def test_downloads_from_web_tools_goes_back_to_web_tools(self):
        mode = companion.handle('web tools', 'awake')
        companion.task_navigation().indices['web_tools_menu'] = 3
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'downloads')
        mode = self.key('Escape', mode)
        self.assertEqual(mode, 'web_tools_menu')
        self.assertTrue(self.said[-1].startswith('Web tools. Downloads (D), 4 of 5.'), self.said[-1])

    def test_close_browser_from_a_group_says_one_message(self):
        # Close browser goes to the main menu and says so. Before, Favorite apps (and Web tools)
        # then spoke over it, so "Browser window closed." was cut off.
        for group in ('web_tools_menu', 'favorites_menu'):
            companion.OFFICE_RETURN = group
            companion.web_session = mock.Mock(snapshot={'url': 'https://example.com/'})
            companion.web_session.backend.regular = False
            del self.said[:]
            self.assertEqual(companion.handle('close browser', 'web'), 'awake', group)
            self.assertEqual(self.said, ['Browser window closed. ' + FIRST_ITEM], group)
            self.assertFalse(companion.OFFICE_RETURN)

    def test_the_web_browser_menu_does_not_promise_the_main_menu(self):
        # Opened from Web tools or Favorite apps, Escape goes back there, not to the main menu.
        from browser_menu import BrowserMenu
        words = BrowserMenu(self.folder).start()
        self.assertNotIn('main menu', words)
        self.assertTrue(words.endswith('Escape goes back.'), words)

    def test_going_to_media_ends_the_way_back_to_web_tools(self):
        companion.OFFICE_RETURN = 'web_tools_menu'
        companion.office_return('radio', 'web', 'media')
        self.assertFalse(companion.OFFICE_RETURN)

    def test_web_tools_has_the_same_keys_as_the_other_groups(self):
        import input_parity
        self.assertEqual(input_parity.SCREEN_KEYS['web_tools_menu']['F1'], 'help with main menu')
        self.assertEqual(input_parity.SCREEN_KEYS['web_tools_menu']['Ctrl+F12'], 'go to sleep')
        self.assertEqual(companion.navigation_key('Alt+O', 'web_tools_menu'), 'open options')
        self.assertEqual(companion.options_return_notice('web_tools_menu'), 'Back to Web tools.')

    def test_a_misheard_word_keeps_you_in_web_tools(self):
        self.assertEqual(companion.handle('purple elephant', 'web_tools_menu'), 'web_tools_menu')
        self.assertIn('Web tools', self.said[-1])


class MainMenuArrivalTests(MenuLayoutCase):
    def test_f1_says_only_the_first_item(self):
        mode = self.key('F1', 'awake')
        self.assertEqual(mode, 'awake')
        self.assertEqual(self.said[-1], FIRST_ITEM)
        self.assertEqual(companion.MAIN_MENU_INDEX, 0)

    def test_after_arrival_down_goes_to_the_second_item_and_enter_opens_the_first(self):
        mode = self.key('F1', 'awake')
        self.key('Down', mode)
        self.assertTrue(self.said[-1].startswith('Office tools (O), 2 of 10.'), self.said[-1])
        self.key('F1', mode)
        with mock.patch.object(companion, 'FILE_MANAGER', None):
            self.assertEqual(self.key('Enter', mode), 'files')

    def test_saying_main_menu_from_an_app_says_only_the_first_item(self):
        mode = companion.handle('word processor', 'awake')
        self.assertEqual(companion.handle('Main menu.', mode), 'awake')
        self.assertEqual(self.said[-1], FIRST_ITEM)

    def test_a_lead_is_said_with_the_item(self):
        companion.MAIN_MENU_LEAD = 'Help closed.'
        companion.announce_main_menu()
        self.assertEqual(self.said[-1], 'Help closed. ' + FIRST_ITEM)

    def test_escape_from_a_group_lands_on_that_group(self):
        for words, opened, item in (('office tools', 'office_menu', 'Office tools (O), 2 of 10.'),
                                    ('organizer', 'organizer_menu', 'Organizer (O), 3 of 10.'),
                                    ('web tools', 'web_tools_menu', 'Web tools (W), 4 of 10.'),
                                    ('media menu', 'media_menu', 'Media (M), 5 of 10.'),
                                    ('shut down or restart', 'power_menu', 'Shut down or restart (S), 9 of 10.')):
            mode = companion.handle(words, 'awake')
            self.assertEqual(mode, opened)
            self.assertEqual(self.key('Escape', mode), 'awake', opened)
            self.assertEqual(self.said[-1], item, opened)
            self.assertEqual(companion.MAIN_MENU_CHOICES[companion.MAIN_MENU_INDEX][0], item.split(' (')[0])

    def test_main_menu_from_a_group_goes_to_the_first_item(self):
        mode = companion.handle('office tools', 'awake')
        self.assertEqual(companion.handle('main menu', mode), 'awake')
        self.assertEqual(self.said[-1], FIRST_ITEM)

    def test_waking_up_on_the_main_menu_says_the_item(self):
        with mock.patch.object(companion, 'interrupt_speech'), mock.patch.object(companion, 'sync_app_context'), \
                mock.patch.object(companion, 'account_setup', False):
            self.assertEqual(companion.resume_from_sleep(), 'awake')
        self.assertEqual(self.said[-1], FIRST_ITEM)

    def test_the_first_startup_words_still_say_where_you_are(self):
        import startup_speech
        self.assertTrue(startup_speech.announcement('0.2.211', 'off').endswith('You are on the main menu.'))

    def test_the_old_long_prompt_is_gone(self):
        for verbosity in ('low', 'medium', 'high'):
            with mock.patch.object(companion, 'VERBOSITY', verbosity):
                companion.announce_main_menu()
            self.assertEqual(self.said[-1], FIRST_ITEM, verbosity)


if __name__ == '__main__':
    unittest.main()
