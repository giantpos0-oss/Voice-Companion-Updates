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
        self.assertNotIn('main menu', words.lower())

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
    'email_draft': ['Message', 'Edit', 'Go to', 'Text style', 'Attachments', 'Contacts', 'Importance and read receipt',
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


class MenuArrivalStyleTests(MenuLayoutCase):
    """Every menu opens with its name and only its first item, letter shown (November 10, 2026)."""
    def test_web_browser_menu_says_only_its_first_item(self):
        from browser_menu import BrowserMenu
        menu = BrowserMenu(self.folder)
        self.assertEqual(menu.start(), 'Web browser menu. Search or enter address (S), 1 of 10.')
        self.assertEqual(menu.index, 0)
        session = mock.Mock(snapshot=None)
        session.backend.regular = False
        self.assertEqual(menu.process('next', session, False), ('Go to favorite (G), 2 of 10.', None))
        self.assertEqual(menu.start(resume=True), 'Web browser menu. Resume where you left off (R), 1 of 11.')

    def test_enter_right_after_opening_the_web_browser_menu_opens_search(self):
        from browser_menu import BrowserMenu
        menu = BrowserMenu(self.folder)
        menu.start()
        session = mock.Mock(snapshot=None)
        session.backend.regular = False
        self.assertEqual(menu.process('enter', session, False), ('', 'search'))

    def test_alt_on_the_web_browser_menu_says_where_you_are(self):
        from browser_menu import BrowserMenu
        companion.web_session = mock.Mock(snapshot=None)
        companion.web_session.backend.regular = False
        companion.web_session.menu = BrowserMenu(self.folder)
        companion.web_session.menu.start()
        companion.web_session.menu.process('next', companion.web_session, False)
        companion.screen_menu().handle('@sm:alt', 'browser_menu')
        self.assertEqual(self.said[-1], 'Web browser menu. Go to favorite (G), 2 of 10.')

    def test_radio_and_podcasts_say_only_their_first_item(self):
        from media_navigation import MediaNavigation
        hub = mock.Mock(stations=[], shows=[], browsing_episodes=False, preset_browsing=False, browsing_categories=False)
        nav = MediaNavigation(hub)
        self.assertEqual(nav.enter('radio'), 'Radio menu. Search stations (S), 1 of 22.')
        self.assertEqual(nav.enter('podcast'), 'Podcasts menu. Browse podcasts (B), 1 of 25.')

    def test_list_menus_open_with_their_name_and_first_item(self):
        import re
        nav = companion.task_navigation()
        for words, mode, title in (('office tools', 'office_menu', 'Office tools'), ('organizer', 'organizer_menu', 'Organizer'),
                                   ('web tools', 'web_tools_menu', 'Web tools'), ('media menu', 'media_menu', 'Media menu'),
                                   ('shut down or restart', 'power_menu', 'Shut down or restart'),
                                   ('word processor', 'word_processor', 'Word processor menu'),
                                   ('notepad', 'notepad_menu', 'Notepad menu'), ('favorite apps', 'favorites_menu', 'Favorite apps')):
            self.assertEqual(companion.handle(words, 'awake'), mode, words)
            first = nav.items(mode)[0][0]
            pattern = re.escape(title + '. ') + '(?:No apps are in it yet. To add apps, press Enter on Change favorite apps. )?' \
                + re.escape(first + ' (' + first[0].upper() + '), 1 of ' + str(len(nav.items(mode))) + '.') + '( .+\\.)?$'
            self.assertRegex(self.said[-1], pattern, words)


class AltMenuLetterTests(unittest.TestCase):
    """Windows-style letters (Will, November 10, 2026): Alt, the group's letter, the item's letter.
    No numbered paths: a number runs nothing."""
    def all_menus(self):
        """(app, group, group letter, [(label, letter, command)]) for every Alt menu."""
        import screen_menus
        rows = []
        for mode, (_, groups) in screen_menus.MENUS.items():
            for name, entries in groups:
                rows.append((mode, name, screen_menus.group_letter(name),
                             [(label, screen_menus.item_letter(command), command) for label, _, command in entries]))
        for group, letter, entries in task_navigation.DOCUMENT_LAYOUT:
            commands = {label: command for label, _, command in task_navigation.DOCUMENT_ACTIONS[group]}
            rows.append(('document', group, letter, [(label, item, commands[label]) for label, item in entries]))
        return rows

    def test_no_two_items_in_a_group_share_a_letter(self):
        groups = {}
        for mode, name, letter, items in self.all_menus():
            groups.setdefault(mode, []).append(letter)
            letters = [item for _, item, _ in items]
            self.assertEqual(len(letters), len(set(letters)), (mode, name, letters))
            self.assertTrue(all(len(x) == 1 and x.isalpha() and x.isupper() for x in letters), (mode, name, letters))
        for mode, letters in groups.items():
            self.assertEqual(len(letters), len(set(letters)), (mode, letters))

    def test_the_same_action_has_the_same_letter_in_every_app(self):
        seen = {}
        for mode, name, _, items in self.all_menus():
            for label, letter, command in items:
                action = 'help' if command.startswith('help with ') else 'options' if command.startswith('@options') else command
                if action == '{value}':
                    continue   # two different document items ask for words to say
                with self.subTest(action=action, where=(mode, name)):
                    self.assertEqual(seen.setdefault(action, (letter, mode, label))[0], letter, (seen[action], mode, label))
        for shared, letter in (('help', 'H'), ('options', 'O'), ('main menu', 'M'), ('undo', 'U'), ('redo', 'R')):
            self.assertEqual(seen[shared][0], letter, shared)

    def test_group_names_that_repeat_use_the_same_letter(self):
        letters = {}
        for mode, name, letter, _ in self.all_menus():
            self.assertEqual(letters.setdefault(name, letter), letter, (mode, name))

    def test_no_spoken_item_or_guide_teaches_a_numbered_path(self):
        import re
        import screen_menus
        from pathlib import Path
        here = Path(__file__).parent
        menu = companion.screen_menu()
        for mode, (_, groups) in screen_menus.MENUS.items():
            menu.mode = mode
            for g in range(len(groups)):
                menu.group = g if len(groups) > 1 else None
                for i in range(len(menu.entries())):
                    self.assertNotRegex(menu.describe(i), r'Alt, \d', mode)
            menu.close()
        for name in ('START HERE - Veteran.txt', 'START HERE - Veteran.html', 'TRAINER TEST CHECKLIST.txt',
                     'tutorial_curriculum.py'):
            text = re.sub(r'</?kbd>', '', (here / name).read_text(encoding='utf-8'))
            self.assertIsNone(re.search(r'Alt, \d', text), name)


class AltMenuKeyTests(MenuLayoutCase):
    def setUp(self):
        super().setUp()
        from email_draft import VoiceEmail
        from document_editor import Paragraph
        draft = VoiceEmail(self.folder / 'Email Drafts', recipient='friend@example.com', subject='Hi',
                           provider='thunderbird', compose_step='body')
        draft.paragraphs = [Paragraph('See you soon.')]
        companion.email_draft = draft
        p = mock.patch.object(companion, 'SCREEN_MENU', None); p.start(); self.addCleanup(p.stop)

    def press(self, key):
        request = companion.navigation_key(key, 'email_draft')
        return 'email_draft' if request is None else companion.handle(request, 'email_draft')

    def test_letters_open_the_group_and_run_the_item(self):
        self.press('Alt')
        self.assertEqual(self.said[-1], 'Email draft menu. Message (M), 1 of 8.')
        self.press('Letter:e')
        self.assertEqual(self.said[-1], 'Edit menu. Undo (U), 1 of 2. Control+Z. Say undo.')
        with mock.patch.object(companion, 'handle', wraps=companion.handle) as handled:
            self.press('Letter:r')
        self.assertIn(mock.call('redo', 'email_draft', typed=True), handled.call_args_list)
        self.assertIsNone(companion.SCREEN_MENU.mode)

    def test_a_number_runs_nothing(self):
        self.press('Alt')
        self.press('Letter:2')
        self.assertEqual(self.said[-1], 'No item uses 2.')
        self.assertEqual(companion.SCREEN_MENU.group, None)
        self.press('Letter:m')
        before = list(self.said)
        self.press('Letter:1')
        self.assertEqual(self.said[-1], 'No item uses 1.')
        self.assertEqual(companion.SCREEN_MENU.mode, 'email_draft')   # still open, nothing ran
        self.assertEqual(len(self.said), len(before) + 1)
        # A spoken number does not choose an item either.
        companion.handle('two', 'email_draft')
        self.assertIsNone(companion.SCREEN_MENU.mode)

    def test_a_letter_no_item_has_says_so(self):
        self.press('Alt')
        self.press('Letter:q')
        self.assertEqual(self.said[-1], 'No item uses Q.')

    def test_the_document_menu_uses_letters_not_numbers(self):
        nav = companion.task_navigation()
        nav.group = None
        self.assertEqual(nav.keyboard('MenuPick:3', 'document_menu'), '@menu:none:3')
        self.assertEqual(nav.keyboard('MenuPick:r', 'document_menu'), '@menu:' + str(list(task_navigation.DOCUMENT_ACTIONS).index('Read')))
        nav.group = 'Read'
        self.assertEqual(nav.keyboard('MenuPick:p', 'document_menu'),
                         '@menu:' + str([n for n, _, _ in task_navigation.DOCUMENT_ACTIONS['Read']].index('Read paragraph')))
        items = nav.items('document_menu')
        self.assertEqual(nav.describe(items[1], 1, len(items)), 'Read paragraph (P), 2 of 9.')


if __name__ == '__main__':
    unittest.main()
