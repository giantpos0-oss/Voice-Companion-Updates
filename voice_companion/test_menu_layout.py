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

    def test_a_choice_that_stays_on_the_main_menu_keeps_your_place(self):
        # Check for updates says its answer and stays on the main menu. Down went back to
        # File manager before, because choosing an item forgot where you were.
        mode = self.key('F1', 'awake')
        for _ in range(6):
            mode = self.key('Down', mode)
        self.assertTrue(self.said[-1].startswith('Check for updates (C), 7 of 10.'), self.said[-1])
        with mock.patch.object(companion, 'UPDATES', None):
            self.assertEqual(self.key('Enter', mode), 'awake')
        self.key('Down', mode)
        self.assertTrue(self.said[-1].startswith('Help (H), 8 of 10.'), self.said[-1])

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


# Every (key, command) each Alt menu had before the regrouping of November 10, 2026.
# Regrouping moves items and renames groups; it must never drop or change a command.
ALT_MENU_COMMANDS = {
    'mailbox': [('', '@options:Email'), ('', 'add account'), ('', 'add contact {value}'), ('', 'add thunderbird account'), ('', 'create folder'), ('', 'delete folder'), ('', 'email list size'), ('', 'go to drafts'), ('', 'go to inbox'), ('', 'go to sent'), ('', 'go to spam'), ('', 'go to trash'), ('', 'hide thunderbird'), ('', 'how big are the attachments'), ('', 'list folders'), ('', 'main menu'), ('', 'message status'), ('', 'move folder'), ('', 'open attachment'), ('', 'remove email account'), ('', 'save all attachments'), ('', 'show thunderbird'), ('', 'switch account'), ('', 'which email account'), ('A', 'reply all'), ('Alt+1', 'who is it from'), ('Alt+2', 'who is it to'), ('Alt+3', 'read the cc'), ('Alt+4', 'what is the subject'), ('Alt+5', 'when was it sent'), ('C', 'copy sender address'), ('Ctrl+A', 'select all messages'), ('Ctrl+End', 'oldest message'), ('Ctrl+Home', 'newest message'), ('D', 'open email draft'), ('Delete', 'delete'), ('Double:F1', 'help with email'), ('E', 'new email to sender'), ('Enter', 'open current message'), ('F', 'forward'), ('F2', 'rename folder'), ('F5', 'list messages'), ('G', 'go to folder'), ('H', 'mark important or not important'), ('I', 'message details'), ('L', 'list attachments'), ('M', 'move'), ('N', 'new email'), ('P', 'list contacts'), ('Page Down', 'next messages'), ('Page Up', 'previous messages'), ('Q', 'mark as read or unread'), ('R', 'reply'), ('S', 'what is selected'), ('Space', 'toggle message selection'), ('U', 'clear selection'), ('W', 'which folder'), ('X', 'flag or unflag')],
    'email_draft': [('', '@options:Email'), ('', 'add contact {value}'), ('', 'attach the last download'), ('', 'discard draft'), ('', 'go to bcc'), ('', 'go to body'), ('', 'go to cc'), ('', 'go to subject'), ('', 'go to to'), ('', 'high importance'), ('', 'importance'), ('', 'leave email'), ('', 'low importance'), ('', 'normal importance'), ('', 'remove attachment'), ('Alt+S', 'send email'), ('Ctrl+B', 'toggle bold'), ('Ctrl+I', 'toggle italic'), ('Ctrl+K', 'list contacts'), ('Ctrl+L', 'list attachments'), ('Ctrl+O', 'attach a file'), ('Ctrl+R', 'read email draft'), ('Ctrl+S', 'save draft'), ('Ctrl+Shift+I', 'change importance'), ('Ctrl+Shift+T', 'read receipt on or off'), ('Ctrl+U', 'toggle underline'), ('Ctrl+Y', 'redo'), ('Ctrl+Z', 'undo'), ('Double:F1', 'help with writing email')],
    'note': [('', '@options:Notepad'), ('', 'main menu'), ('', 'new line'), ('', 'scratch that'), ('Ctrl+O', 'list notes'), ('Ctrl+R', 'read from top'), ('Ctrl+S', 'save note'), ('Ctrl+Y', 'redo'), ('Ctrl+Z', 'undo'), ('Double:F1', 'help with notepad')],
    'web': [('', '@options:Web browser'), ('', 'add favorite'), ('', 'go to favorite'), ('', 'hide browser window'), ('', 'set up chrome'), ('', 'show browser window'), ('', 'web history'), ('Alt+Left', 'web key Back'), ('Alt+Right', 'web key Forward'), ('Ctrl+D', 'download manager'), ('Ctrl+End', 'bottom of page'), ('Ctrl+F', 'find {value}'), ('Ctrl+Home', 'top of page'), ('Ctrl+L', 'web key Search'), ('Double:F1', 'help with web'), ('Escape', 'web browser menu'), ('F5', 'web key Refresh'), ('F6', 'list headings'), ('F7', 'list links'), ('F8', 'list fields')],
    'downloads': [('', '@options:Web browser'), ('', 'download details'), ('', 'move to next'), ('', 'open downloads folder'), ('Ctrl+Down', 'move download later'), ('Ctrl+Up', 'move download earlier'), ('Delete', 'delete download'), ('Double:F1', 'help with downloads'), ('Enter', 'open download'), ('Escape', 'close downloads'), ('Space', 'pause or resume download')],
    'contacts': [('', 'call details'), ('', 'main menu'), ('', 'read contact'), ('', 'refresh contacts'), ('Ctrl+E', 'email contact'), ('Ctrl+F', 'find contact {value}'), ('Ctrl+L', 'choose address book'), ('Ctrl+N', 'add contact'), ('Delete', 'delete contact'), ('Double:F1', 'help with contacts'), ('Enter', 'open contact'), ('F2', 'edit contact')],
    'calendar': [('', 'main menu'), ('', 'refresh calendar'), ('Ctrl+G', 'go to date'), ('Ctrl+L', 'choose calendar'), ('Ctrl+N', 'add event'), ('Delete', 'delete event'), ('Double:F1', 'help with calendar'), ('Down', 'next event'), ('Enter', 'read event'), ('F2', 'edit event'), ('Home', 'today'), ('Left', 'previous day'), ('Page Down', 'next week'), ('Page Up', 'previous week'), ('Right', 'next day'), ('Up', 'previous event')],
    'help': [('', 'close help'), ('', 'help topics'), ('', 'list subsections'), ('', 'main menu'), ('', 'open user guides'), ('', 'release notes'), ('', 'start tutorial')],
    'tutorial': [('', 'main menu'), ('', 'next lesson'), ('', 'previous lesson'), ('Ctrl+Down', 'continue reading'), ('Ctrl+E', 'explain command {value}'), ('Ctrl+F', 'find lesson {value}'), ('Ctrl+L', 'lesson list'), ('Ctrl+R', 'repeat'), ('Double:F1', 'list commands')],
    'attachments': [('Ctrl+A', 'tag all attachments'), ('Ctrl+D', 'save attachment to folder'), ('Ctrl+I', 'read attachment details'), ('Ctrl+O', 'attach a file'), ('Ctrl+S', 'save attachment'), ('Ctrl+Shift+A', 'clear attachment tags'), ('Ctrl+Shift+S', 'save all attachments'), ('Ctrl+Shift+T', 'what attachments are tagged'), ('Delete', 'remove attachment'), ('Double:F1', 'help with attachments'), ('Enter', 'open attachment'), ('Escape', 'close attachments'), ('Space', 'tag attachment')],
    'file_reader': [('', 'go to beginning of document'), ('', 'go to end of document'), ('', 'main menu'), ('B', 'next bookmark'), ('Ctrl+F', 'find {value}'), ('Ctrl+R', 'read document'), ('Double:F1', 'help with document reader'), ('Enter', 'follow link'), ('Escape', 'back to files'), ('H', 'next heading'), ('Insert+Down', 'say all'), ('Insert+F', 'what formatting'), ('Insert+Shift+Down', 'what is selected'), ('K', 'next link'), ('L', 'next list'), ('N', 'next footnote'), ('Shift+H', 'previous heading'), ('T', 'next table')],
    'youtube': [('', 'clear filters'), ('', 'history'), ('', 'liked videos'), ('', 'main menu'), ('', 'media menu'), ('', 'my playlists'), ('', 'my subscriptions'), ('', 'normal speed'), ('', 'open in browser'), ('', 'post comment {value}'), ('', 'save to watch later'), ('', 'sign in'), ('', 'sign out'), ('', 'skip amount {value}'), ('', 'stop video'), ('', 'subscriptions'), ('', 'watch later'), ('', 'youtube home'), ('', 'youtube menu'), ('0', 'restart video'), ('A', 'autoplay on or off'), ('C', 'captions on or off'), ('Ctrl+Down', 'video volume down'), ('Ctrl+F', 'search youtube'), ('Ctrl+Left', 'previous chapter'), ('Ctrl+Right', 'next chapter'), ('Ctrl+Shift+F', 'search filters'), ('Ctrl+Up', 'video volume up'), ('D', 'read description'), ('Double:F1', 'help with youtube'), ('Escape', 'go back'), ('F', 'video full screen'), ('F5', 'refresh youtube'), ('G', 'go to channel'), ('H', 'list chapters'), ('I', 'video details'), ('Left', 'skip back'), ('M', 'mute or unmute'), ('N', 'next video'), ('O', 'read comments'), ('P', 'previous video'), ('Q', 'video quality'), ('R', 'read caption'), ('Right', 'skip forward'), ('S', 'skip ad'), ('Space', 'play or pause video'), ('T', 'like video'), ('U', 'subscribe or unsubscribe'), ('W', 'save video'), ('X', 'up next'), ('comma', 'slower video'), ('period', 'faster video')],
}

ALT_MENU_GROUPS = {
    'mailbox': ['Message', 'Header', 'Attachments', 'Unread and flags', 'Select', 'Go to', 'Edit folders', 'View', 'Tools'],
    'email_draft': ['Message', 'Edit', 'Go to', 'Format', 'Attachments', 'Contacts', 'Importance and read receipt',
                    'Options and help'],
    'note': ['Note', 'Edit', 'Options and help'],
    'web': ['Go to', 'Page', 'Favorites', 'Tools', 'Options and help'],
    'downloads': ['Download', 'Move in list', 'Folder', 'Leave and help'],
    'contacts': ['Contact', 'Address book', 'Leave and help'],
    'calendar': ['Event', 'Go to', 'Calendar', 'Leave and help'],
    'help': ['Help'],
    'tutorial': ['Lessons'],
    'attachments': ['Attachment', 'Tags', 'Leave and help'],
    'file_reader': ['Read', 'Go to', 'Leave and help'],
    'youtube': ['Play', 'Volume and speed', 'Captions and picture', 'This video', 'Your account', 'Search', 'Go to',
                'Leave and help'],
}


class AltMenuCategoryTests(unittest.TestCase):
    """Will, November 10, 2026: clear group names, and each item where a user would look."""
    def test_groups_have_clear_names(self):
        import screen_menus
        self.assertEqual({mode: [name for name, _ in groups] for mode, (_, groups) in screen_menus.MENUS.items()},
                         ALT_MENU_GROUPS)

    def test_no_command_was_lost_or_changed(self):
        import screen_menus
        for mode, (_, groups) in screen_menus.MENUS.items():
            with self.subTest(mode=mode):
                self.assertEqual(sorted((key, command) for _, entries in groups for _, key, command in entries),
                                 ALT_MENU_COMMANDS[mode])

    def test_each_group_has_its_own_first_letter(self):
        # A letter on the group list goes straight to one group.
        import screen_menus
        from menu_navigation import quick_key
        for mode, (_, groups) in screen_menus.MENUS.items():
            letters = [quick_key(name) for name, _ in groups]
            self.assertEqual(len(letters), len(set(letters)), (mode, letters))

    def test_items_sit_where_a_user_looks_for_them(self):
        import screen_menus
        where = {(mode, label): group for mode, (_, groups) in screen_menus.MENUS.items()
                 for group, entries in groups for label, _, _ in entries}
        for mode, label, group in (
                ('mailbox', 'Mark as read or unread', 'Unread and flags'), ('mailbox', 'Flag or unflag', 'Unread and flags'),
                ('mailbox', 'Copy sender address', 'Header'), ('mailbox', 'Email the sender', 'Message'),
                ('mailbox', 'Email drafts', 'Go to'), ('mailbox', 'Check for new mail', 'View'),
                ('mailbox', 'Show Thunderbird', 'View'), ('mailbox', 'Switch account', 'Tools'),
                ('mailbox', 'Message details', 'Message'), ('mailbox', 'Main menu', 'Go to'),
                ('email_draft', 'Undo', 'Edit'), ('email_draft', 'To', 'Go to'), ('email_draft', 'Email options', 'Options and help'),
                ('web', 'Back', 'Go to'), ('web', 'Web history', 'Go to'), ('web', 'Downloads', 'Tools'),
                ('web', 'Show browser window', 'Tools'), ('web', 'Headings', 'Page'),
                ('downloads', 'Close downloads', 'Leave and help'), ('downloads', 'Open downloads folder', 'Folder'),
                ('contacts', 'Main menu', 'Leave and help'), ('calendar', 'Today', 'Go to'),
                ('attachments', 'Close the list', 'Leave and help'), ('youtube', 'List chapters', 'This video'),
                ('note', 'Main menu', 'Options and help')):
            self.assertEqual(where.get((mode, label)), group, (mode, label))


if __name__ == '__main__':
    unittest.main()
