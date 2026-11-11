"""Organizer, Favorite apps, Options for Favorite apps, and the F1 keys (Will, November 6 and 10, 2026).

- Organizer follows Office tools on the main menu. It holds Address manager and Schedule
  manager, the old Contacts and Calendar, in alphabetical order. The old words still work.
- F1 goes to the main menu from every screen. F1 twice quickly opens help for the screen;
  on the main menu that is the user guide.
- Control+F1 opens Favorite apps: the apps chosen in Options, Favorite apps, then Change favorite apps.
- Options, Favorite apps (called My menu before November 10) is one list of every app. Space selects an
  app; Control+Up and Control+Down move it. Favorite apps uses that order. Older saved options keep
  their apps and order.
"""
import unittest
from unittest import mock

import companion
import settings_model
import task_navigation
from f1_key import F1Presses
from test_core_email_fixes import CompanionTestCase


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class F1PressTests(unittest.TestCase):
    def test_one_press_waits_then_goes_to_the_main_menu(self):
        clock = Clock()
        presses = F1Presses(clock)
        self.assertIsNone(presses.press())
        self.assertIsNone(presses.due())          # still waiting for a second press
        clock.now += 0.5
        self.assertEqual(presses.due(), 'F1')
        self.assertIsNone(presses.due())          # only once

    def test_two_quick_presses_are_help_and_never_the_main_menu(self):
        clock = Clock()
        presses = F1Presses(clock)
        presses.press()
        clock.now += 0.2
        self.assertEqual(presses.press(), 'Double:F1')
        clock.now += 1
        self.assertIsNone(presses.due())

    def test_two_slow_presses_are_two_single_presses(self):
        clock = Clock()
        presses = F1Presses(clock)
        presses.press()
        clock.now += 0.6
        self.assertIsNone(presses.press())        # a new first press
        self.assertIsNone(presses.due())          # the first one was overtaken, not lost twice
        clock.now += 0.6
        self.assertEqual(presses.due(), 'F1')

    def test_window_code_uses_the_wait(self):
        from pathlib import Path
        source = (Path(__file__).parent / 'app_window.py').read_text(encoding='utf-8')
        self.assertIn("self.commands.put(('keyboard','Double:F1'))", source)
        self.assertIn("root.after(int(F1_WAIT*1000)+20,single_f1)", source)
        settings = (Path(__file__).parent / 'native_settings.py').read_text(encoding='utf-8')
        self.assertIn("self.keyboard('Double:F1')", settings)
        self.assertIn("self.f1_presses.due()", settings)


class MenuTests(CompanionTestCase):
    def setUp(self):
        super().setUp()
        for name, value in dict(TASK_NAV=None, NAMED_LIST=None, OPEN_NOTE=None, OFFICE_RETURN=False,
                                FAVORITES_AFTER=False, MAIN_MENU_INDEX=None, SETTINGS_RETURN_MODE='awake').items():
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'note_buffer', []); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'PREFERENCES', dict(companion.PREFERENCES)); p.start(); self.addCleanup(p.stop)

    def key(self, key, mode):
        request = companion.navigation_key(key, mode)
        return mode if request is None else companion.handle(request, mode)

    def choose(self, *names):
        for name in names:
            companion.PREFERENCES[task_navigation.favorite_key(name)] = True

    # Organizer

    def test_organizer_follows_office_tools(self):
        names = [name for name, _ in companion.MAIN_MENU_CHOICES]
        self.assertEqual(names[:3], ['File manager', 'Office tools', 'Organizer'])
        mode = companion.handle('Organizer.', 'awake')
        self.assertEqual(mode, 'organizer_menu')
        self.assertTrue(self.said[-1].startswith('Organizer. Address manager'), self.said[-1])
        self.assertEqual([name for name, _, _ in companion.task_navigation().items('organizer_menu')],
                         ['Address manager', 'Schedule manager'])

    def test_address_manager_opens_from_organizer_and_comes_back(self):
        mode = companion.handle('organizer', 'awake')
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'contacts')
        self.assertTrue(any(said.startswith('Address manager.') for said in self.said), self.said)
        for _ in range(5):
            mode = self.key('Escape', mode)
            if mode != 'contacts': break
        self.assertEqual(mode, 'organizer_menu')
        self.assertTrue(self.said[-1].startswith('Organizer. Address manager'), self.said[-1])
        self.assertEqual(self.key('Escape', mode), 'awake')

    def test_new_and_old_names_open_the_same_screens(self):
        for said in ('Address manager.', 'open address manager', 'contacts', 'address book'):
            with self.subTest(said=said):
                self.assertEqual(companion.handle(said, 'awake'), 'contacts')
        import calendar_screen
        for said in ('Schedule manager.', 'open schedule manager', 'calendar'):
            with self.subTest(said=said), mock.patch.object(calendar_screen, 'handle', side_effect=lambda m, text, mode, typed:
                                                             'calendar' if m.normalized_command(text) in calendar_screen.OPEN else None):
                self.assertEqual(companion.handle(said, 'awake'), 'calendar')

    def test_help_topics_answer_to_both_names(self):
        from pathlib import Path
        import onboard_help
        guide = Path(companion.__file__).with_name('START HERE - Veteran.txt')
        for wanted, chapter in (('address manager', 'Address manager'), ('contacts', 'Address manager'),
                                ('schedule manager', 'Schedule manager'), ('calendar', 'Schedule manager'),
                                ('organizer', 'Getting started'), ('favorite apps', 'Getting started')):
            with self.subTest(wanted=wanted):
                session = onboard_help.HelpSession(guide)
                words = session.topic(wanted)
                self.assertNotIn(onboard_help.NOT_FOUND, words)
                self.assertEqual(session.topics[session.topic_index]['name'].casefold(), chapter.casefold(), words)

    def test_file_manager_is_first_and_returns_to_the_main_menu(self):
        mode = self.key('Home', 'awake')
        self.assertTrue(self.said[-1].startswith('File manager'), self.said[-1])
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'files')
        for _ in range(10):
            mode = self.key('Escape', mode)
            if mode != 'files': break
        self.assertEqual(mode, 'awake')

    # F1

    def test_f1_goes_to_the_main_menu_from_every_screen(self):
        for mode in ('awake', 'document', 'email_draft', 'note', 'mailbox', 'web', 'files', 'local_media',
                     'media_menu', 'word_processor', 'file_reader', 'settings', 'help', 'media', 'tutorial',
                     'office_menu', 'organizer_menu', 'favorites_menu', 'contacts', 'calendar'):
            with self.subTest(mode=mode):
                self.assertEqual(companion.navigation_key('F1', mode), '@main_menu')

    def test_f1_twice_is_help_for_the_screen(self):
        cases = {'awake': 'help', 'note': 'help with notepad', 'mailbox': 'help with email', 'web': 'help with web',
                 'contacts': 'help with contacts', 'calendar': 'help with calendar', 'files': 'file manager help',
                 'office_menu': 'help with main menu', 'organizer_menu': 'help with main menu',
                 'favorites_menu': 'help with main menu', 'tutorial': 'list commands'}
        for mode, request in cases.items():
            with self.subTest(mode=mode):
                self.assertEqual(companion.navigation_key('Double:F1', mode), request)

    def test_f1_twice_on_the_main_menu_opens_the_user_guide(self):
        self.assertEqual(self.key('Double:F1', 'awake'), 'help')

    def test_f1_twice_in_a_document_is_document_help(self):
        self.open_document()
        self.assertEqual(companion.navigation_key('Double:F1', 'document'), 'help with documents')

    def test_menus_say_f1_twice_for_help_and_f1_for_the_main_menu(self):
        navigation = companion.task_navigation()
        items = navigation.items('notepad_menu')
        self.assertIn('Main menu, 4 of 4. F1.', navigation.describe(items[3], 3, 4).replace(' (M)', ''))
        items = navigation.items('reader_menu')
        help_item = next(i for i, item in enumerate(items) if item[0] == 'Help')
        self.assertTrue(navigation.describe(items[help_item], help_item, len(items)).endswith('F1 twice.'))

    def test_spoken_messages_name_f1_twice_for_help(self):
        self.assertIn('Press F1 twice for help.', companion.MAIN_MENU_NOT_UNDERSTOOD)
        import startup_speech
        self.assertTrue(all('Press F1 for' not in words for words in vars(startup_speech).values() if isinstance(words, str)))

    # Favorite apps

    def test_control_f1_opens_favorite_apps_from_every_screen(self):
        for mode in ('awake', 'document', 'note', 'web', 'files', 'settings', 'office_menu'):
            with self.subTest(mode=mode):
                self.assertEqual(companion.navigation_key('Ctrl+F1', mode), '@favorites')

    def test_empty_favorite_apps_says_how_to_add_apps(self):
        mode = self.key('Ctrl+F1', 'awake')
        self.assertEqual(mode, 'favorites_menu')
        self.assertEqual(self.said[-1], 'Favorite apps. No apps are in it yet. To add apps, press Enter on '
                                        'Change favorite apps. Change favorite apps (C), 1 of 1.')

    def test_favorite_apps_lists_the_chosen_apps_in_order(self):
        self.choose('YouTube', 'Notepad', 'File manager')
        mode = companion.handle('favorite apps', 'awake')
        self.assertEqual(mode, 'favorites_menu')
        names = [name for name, _, _ in companion.task_navigation().items('favorites_menu')]
        self.assertEqual(names, ['File manager', 'Notepad', 'YouTube', 'Change favorite apps'])
        self.assertTrue(self.said[-1].startswith('Favorite apps. File manager'), self.said[-1])

    def test_web_favorites_keep_their_words(self):
        # "Favorites" and "My favorites" are the web browser's saved pages, not Favorite apps.
        for said in ('favorites', 'my favorites', 'Favourites.'):
            with self.subTest(said=said):
                self.assertNotIn(companion.normalized_command(said), task_navigation.FAVORITES_OPEN)

    def test_saying_favorite_apps_when_empty_says_how_to_add_apps(self):
        self.assertEqual(companion.handle('Favorite apps.', 'awake'), 'favorites_menu')
        self.assertIn('No apps are in it yet.', self.said[-1])

    def test_an_app_from_favorite_apps_comes_back_there(self):
        self.choose('Notepad', 'Address manager')
        mode = self.key('Ctrl+F1', 'awake')
        self.key('Down', mode)                       # Notepad, then Address manager
        mode = self.key('Enter', mode)
        self.assertEqual(mode, 'contacts')
        for _ in range(5):
            mode = self.key('Escape', mode)
            if mode != 'contacts': break
        self.assertEqual(mode, 'favorites_menu')
        self.assertTrue(self.said[-1].startswith('Favorite apps. Address manager'), self.said[-1])
        # F1 from there: the main menu, and the way back is used up.
        self.assertEqual(self.key('F1', mode), 'awake')
        self.assertFalse(companion.OFFICE_RETURN)

    def test_control_f1_in_a_note_saves_it_then_opens_favorite_apps(self):
        self.choose('Word processor')
        mode = self.key('Ctrl+N', companion.handle('notepad', 'awake'))
        self.assertEqual(mode, 'note')
        companion.handle('Buy milk.', mode)
        with mock.patch.object(companion, 'save_note', return_value=True) as save:
            mode = self.key('Ctrl+F1', mode)
        self.assertEqual(mode, 'favorites_menu')
        self.assertTrue(save.called)
        self.assertNotIn(companion.MAIN_MENU_PROMPT, self.said[-1])
        self.assertIn('Favorite apps. Word processor', self.said[-1])
        self.assertFalse(companion.FAVORITES_AFTER)

    def test_control_f1_in_a_changed_document_asks_to_save_first(self):
        document = self.open_document()
        companion.INPUT_MODE = 'dictation'
        companion.handle('Dinner is at six.', 'document')
        mode = self.key('Ctrl+F1', 'document')
        self.assertEqual(mode, 'document_save')
        self.assertTrue(companion.FAVORITES_AFTER)
        self.assertIn('Dinner is at six.', companion.document_text(document))

    def test_canceling_the_save_question_forgets_favorite_apps(self):
        companion.FAVORITES_AFTER = True
        self.assertEqual(companion.office_return('cancel', 'document_save', 'document'), 'document')
        self.assertFalse(companion.FAVORITES_AFTER)

    def test_change_favorite_apps_opens_options_on_favorite_apps(self):
        mode = self.key('Ctrl+F1', 'awake')
        panel = mock.Mock()
        def opened(mode):
            companion.SETTINGS_PANEL = panel
            return 'settings'
        with mock.patch.object(companion, 'open_settings', side_effect=opened), \
                mock.patch.object(companion, 'SETTINGS_PANEL', None):
            self.assertEqual(self.key('Enter', mode), 'settings')
        panel.command.assert_called_once_with('Favorite apps')
        self.assertEqual(companion.SETTINGS_RETURN_MODE, 'favorites_menu')
        self.assertEqual(companion.options_return_notice('favorites_menu'), 'Back to Favorite apps.')

    def test_favorite_apps_options_by_voice_and_the_old_words(self):
        for said in ('Change favorite apps.', 'Favorite apps options.', 'my menu', 'Open my menu.'):
            with self.subTest(said=said), mock.patch.object(companion.screen_menu(), 'run', return_value='settings') as run:
                self.assertEqual(companion.handle(said, 'awake'), 'settings')
                run.assert_called_with('@options:Favorite apps', 'awake')

    # Favorite apps in Options

    def test_favorite_apps_is_last_in_options_with_one_list_of_every_app(self):
        self.assertEqual(settings_model.CATEGORIES[-1], 'Favorite apps')
        self.assertNotIn('My menu', settings_model.CATEGORIES)
        fields = settings_model.fields('Favorite apps', {})
        self.assertEqual([(f.key, f.kind) for f in fields], [('favorite_order', 'apps')])
        self.assertEqual(list(fields[0].choices), [name for name, _ in task_navigation.FAVORITE_APPS])
        session = settings_model.SettingsSession({}, {})
        self.assertFalse(session.values['favorite_youtube'])
        self.assertEqual(list(session.values['favorite_order']), [name for name, _ in task_navigation.FAVORITE_APPS])

    def test_first_letters_in_the_category_list_reach_favorite_apps(self):
        # The categories list (native_settings): F goes to File manager options, then Favorite apps,
        # then stays there. End goes to Favorite apps, the last category.
        from menu_navigation import next_match
        names = settings_model.CATEGORIES
        first = next_match(names, 0, 'f')
        self.assertEqual(names[first], 'File manager options')
        second = next_match(names, first, 'f')
        self.assertEqual(names[second], 'Favorite apps')
        self.assertEqual(next_match(names, second, 'f'), second)   # "End of matching items."
        self.assertEqual(len(names) - 1, second)
        # S still goes Synthesizer, then Startup and exit options (test_native_settings on Windows).
        self.assertEqual([names[next_match(names, 0, 's')], names[next_match(names, 2, 's')]],
                         ['Synthesizer options', 'Startup and exit options'])

    def test_every_favorite_app_command_opens_something(self):
        for name, command in task_navigation.FAVORITE_APPS:
            with self.subTest(name=name):
                self.assertTrue(command)
                self.assertNotEqual(companion.normalized_command(command), '')



APPS = [name for name, _ in task_navigation.FAVORITE_APPS]


class FavoriteAppsListTests(unittest.TestCase):
    """The one list in Options, Favorite apps: keys, voice commands and what is said."""

    def setUp(self):
        from favorite_list import FavoriteList
        self.session = settings_model.SettingsSession({'favorite_email': True}, {})
        self.list = FavoriteList(self.session)

    def at(self, name):
        self.list.index = self.list.order.index(name)

    def test_each_app_says_its_name_state_and_place(self):
        self.at('Email')
        self.assertEqual(self.list.label(), 'Email, selected, 4 of 12.')
        self.at('Notepad')
        self.assertEqual(self.list.label(), 'Notepad, not selected, 3 of 12.')

    def test_space_selects_then_unselects(self):
        self.at('YouTube')
        self.assertEqual(self.list.keyboard('Space'), 'YouTube, selected.')
        self.assertTrue(self.session.values['favorite_youtube'])
        self.assertEqual(self.list.keyboard('Space'), 'YouTube, not selected.')
        self.assertFalse(self.session.values['favorite_youtube'])

    def test_select_and_unselect_by_voice_never_undo_themselves(self):
        self.at('Radio')
        self.assertEqual(self.list.voice('Select.'), 'Radio, selected.')
        self.assertEqual(self.list.voice('select'), 'Radio is already selected.')
        self.assertTrue(self.session.values['favorite_radio'])
        self.assertEqual(self.list.voice('Unselect.'), 'Radio, not selected.')
        self.assertEqual(self.list.voice('Deselect'), 'Radio is already not selected.')
        self.assertEqual(self.list.voice('Toggle.'), 'Radio, selected.')

    def test_control_arrows_move_the_app_and_say_its_new_place(self):
        self.at('Email')
        self.assertEqual(self.list.keyboard('Up', control=True), 'Email, moved to 3 of 12.')
        self.assertEqual(self.list.keyboard('Up', control=True), 'Email, moved to 2 of 12.')
        self.assertEqual(self.list.order[:4], ['File manager', 'Email', 'Word processor', 'Notepad'])
        self.assertEqual(self.list.label(), 'Email, selected, 2 of 12.')   # the cursor stays on the app
        self.assertEqual(self.list.keyboard('Down', control=True), 'Email, moved to 3 of 12.')
        self.assertEqual(self.session.values['favorite_order'], self.list.order)

    def test_moves_stop_at_the_ends(self):
        self.at('File manager')
        self.assertEqual(self.list.keyboard('Up', control=True), 'File manager is already at the top.')
        self.assertEqual(self.list.keyboard('Home', control=True), 'File manager is already at the top.')
        self.assertEqual(self.list.keyboard('End', control=True), 'File manager, moved to 12 of 12.')
        self.assertEqual(self.list.keyboard('Down', control=True), 'File manager is already at the bottom.')
        self.assertEqual(self.list.voice('Move to the bottom.'), 'File manager is already at the bottom.')
        self.assertEqual(self.list.voice('Move to top.'), 'File manager, moved to 1 of 12.')
        self.assertEqual(self.list.order, APPS)

    def test_move_words_by_voice(self):
        self.at('Podcasts')
        for said, words in (('Move up.', 'Podcasts, moved to 9 of 12.'), ('move down', 'Podcasts, moved to 10 of 12.'),
                            ('Move to the top.', 'Podcasts, moved to 1 of 12.'), ('Move to bottom', 'Podcasts, moved to 12 of 12.'),
                            ('Move, up.', 'Podcasts, moved to 11 of 12.')):
            with self.subTest(said=said):
                self.assertEqual(self.list.voice(said), words)

    def test_arrows_home_end_and_letters_move_the_cursor_and_stop_at_the_ends(self):
        self.assertEqual(self.list.keyboard('Up'), 'Start of list.')
        self.assertEqual(self.list.keyboard('Home'), 'Start of list.')
        self.assertEqual(self.list.keyboard('Down'), 'Word processor, not selected, 2 of 12.')
        self.assertEqual(self.list.keyboard('End'), 'YouTube, not selected, 12 of 12.')
        self.assertEqual(self.list.keyboard('Down'), 'End of list.')
        self.assertEqual(self.list.keyboard('End'), 'End of list.')
        self.assertEqual(self.list.keyboard('Home'), 'File manager, not selected, 1 of 12.')
        self.assertEqual(self.list.keyboard('E'), 'Email, selected, 4 of 12.')
        self.assertEqual(self.list.keyboard('E'), 'End of matching items.')
        self.assertEqual(self.list.keyboard('Z'), 'No app starts with Z.')
        self.assertEqual(self.list.voice('Next.'), 'Document reader, not selected, 5 of 12.')
        self.assertEqual(self.list.voice('previous app'), 'Email, selected, 4 of 12.')
        self.assertEqual(self.list.voice('Last item'), 'YouTube, not selected, 12 of 12.')
        self.assertEqual(self.list.voice('first item'), 'File manager, not selected, 1 of 12.')

    def test_other_words_and_keys_are_left_alone(self):
        for said in ('ok', 'cancel', 'select email', 'Use the back door at night.', 'next setting', 'move'):
            with self.subTest(said=said):
                self.assertIsNone(self.list.voice(said))
        self.assertIsNone(self.list.keyboard('C', control=True))
        self.assertIsNone(self.list.keyboard('Tab'))

    def test_cancel_puts_back_the_choices_and_the_order(self):
        self.at('YouTube')
        self.list.keyboard('Space'); self.list.keyboard('Home', control=True)
        self.session.cancel()
        self.assertFalse(self.session.values['favorite_youtube'])
        self.assertEqual(list(self.session.values['favorite_order']), APPS)

    def test_the_menu_uses_the_new_order(self):
        self.at('YouTube'); self.list.keyboard('Space'); self.list.keyboard('Home', control=True)
        items = task_navigation.favorite_items(self.session.values)
        self.assertEqual([name for name, _, _ in items], ['YouTube', 'Email', 'Change favorite apps'])
        self.assertEqual(items[0][2], 'youtube')
        self.assertEqual(items[-1][2], '@options:Favorite apps')


class SavedFavoriteAppsTests(unittest.TestCase):
    """Saved options from older versions keep their apps and order, and the order is saved safely."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def write(self, values):
        import json
        (self.folder / 'preferences.json').write_text(json.dumps(values), encoding='utf-8')

    def names(self, preferences):
        return [name for name, _, _ in task_navigation.favorite_items(preferences)][:-1]

    def test_options_saved_by_0_2_210_keep_their_apps_in_the_old_order(self):
        # 0.2.210 saved one setting per app, every one of them, and no order.
        old = {task_navigation.favorite_key(name): name in ('YouTube', 'Notepad', 'File manager') for name in APPS}
        self.write(dict(old, verbosity='low'))
        preferences, damaged = companion.load_preferences(self.folder)
        self.assertFalse(damaged)
        self.assertEqual(self.names(preferences), ['File manager', 'Notepad', 'YouTube'])
        from favorite_list import FavoriteList
        model = FavoriteList(settings_model.SettingsSession(preferences, {}))
        self.assertEqual(model.order, APPS)
        self.assertEqual([model.state(i) for i in range(3)], ['selected', 'not selected', 'selected'])

    def test_a_new_order_is_saved_and_read_back(self):
        from types import SimpleNamespace
        from app_settings import save_preferences
        preferences, _ = companion.load_preferences(self.folder)
        session = settings_model.SettingsSession(preferences, {})
        from favorite_list import FavoriteList
        model = FavoriteList(session)
        for name in ('Radio', 'Email'):
            model.index = model.order.index(name); model.toggle(); model.move('top')
        # Options saves every setting in DEFAULTS (app_settings.apply_settings), then writes the file.
        saved = {key: session.values[key] for key in settings_model.DEFAULTS}
        save_preferences(SimpleNamespace(APP=self.folder, PREFERENCES=saved))
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ['preferences.json'])   # no side file left
        again, damaged = companion.load_preferences(self.folder)
        self.assertFalse(damaged)
        self.assertEqual(self.names(again), ['Email', 'Radio'])
        self.assertEqual(again['favorite_order'][:2], ['Email', 'Radio'])

    def test_a_damaged_order_never_loses_an_app(self):
        for order in ('Email, Radio', None, 5, ['Radio', 'radio', 'Nothing', 7, None, ' email '], [], {'a': 1}):
            with self.subTest(order=order):
                self.write({'favorite_order': order, 'favorite_email': True, 'favorite_radio': True})
                preferences, _ = companion.load_preferences(self.folder)
                full = task_navigation.favorite_order(preferences)
                self.assertEqual(sorted(full), sorted(APPS))
                session = settings_model.SettingsSession(preferences, {})
                self.assertEqual(sorted(session.values['favorite_order']), sorted(APPS))
                self.assertEqual(set(self.names(preferences)), {'Email', 'Radio'})
        self.write({'favorite_order': ['Radio', 'radio', 'Nothing', ' email '], 'favorite_email': True, 'favorite_radio': True})
        self.assertEqual(self.names(companion.load_preferences(self.folder)[0]), ['Radio', 'Email'])

    def test_an_app_missing_from_the_saved_order_is_added_at_the_end(self):
        # An app added in a later version is not in an older saved order.
        order = [name for name in APPS if name != 'Notepad'][::-1]
        self.assertEqual(task_navigation.favorite_order({'favorite_order': order}), order + ['Notepad'])

    def test_the_defaults_are_never_changed_by_a_copy(self):
        preferences, _ = companion.load_preferences(self.folder)
        session = settings_model.SettingsSession(preferences, {})
        from favorite_list import FavoriteList
        model = FavoriteList(session); model.index = 5; model.move('top')
        self.assertEqual(list(settings_model.DEFAULTS['favorite_order']), APPS)
        self.assertIsInstance(settings_model.DEFAULTS['favorite_order'], tuple)

    def test_the_order_is_checked_when_options_are_saved(self):
        session = settings_model.SettingsSession({}, {})
        session.set('favorite_order', ['YouTube', 'Unknown', 'Email'])
        self.assertEqual(session.values['favorite_order'][:2], ['YouTube', 'Email'])
        self.assertEqual(len(session.values['favorite_order']), 12)
        session.set('favorite_order', 'Radio, Notepad')
        self.assertEqual(session.values['favorite_order'][:2], ['Radio', 'Notepad'])

    def test_spoken_settings_never_treat_list_words_as_a_setting(self):
        session = settings_model.SettingsSession({}, {})
        for said in ('Apps, YouTube', 'set favorite order to YouTube', 'select', 'move up'):
            with self.subTest(said=said):
                self.assertIsNone(session.voice_setting(said))


class FavoriteAppsOptionsWordsTests(unittest.TestCase):
    def test_the_list_says_what_it_is_and_its_keys(self):
        from favorite_list import FavoriteList
        from native_settings import ROLES, apps_words
        field = settings_model.fields('Favorite apps', {})[0]
        self.assertEqual(ROLES[field.kind], 'list box')
        model = FavoriteList(settings_model.SettingsSession({}, {}))
        self.assertEqual(apps_words(field, model), 'Apps, list box. File manager, not selected, 1 of 12. '
                                                   'Space selects or unselects. Control+Up or Control+Down moves.')

    def test_the_dialog_wires_the_list_keys_and_words(self):
        import inspect, native_settings
        source = inspect.getsource(native_settings.NativeSettings._run)
        for wanted in ("words=apps[0].keyboard(key,held)", "message=apps[0].voice(text_command)",
                       # The helper buttons for a mouse are out of the Tab order (no WS_TABSTOP, 0x10000).
                       "button=control('BUTTON',label,0,225+j*155,y+APPS_HEIGHT+28,145,27,310+j)"):
            self.assertTrue(wanted in source, wanted)

    def test_help_and_lessons_name_the_list(self):
        import onboard_help
        from pathlib import Path
        from tutorial_curriculum import option_explanation
        field = settings_model.fields('Favorite apps', {})[0]
        self.assertIn('Control+Up and Control+Down move it', option_explanation(field))
        guide = Path(companion.__file__).with_name('START HERE - Veteran.txt')
        # "Help with my menu" said it found no topic: "my" was taken off as in "help with my email".
        for wanted in ('favorite apps options', 'Favourite apps options.', 'my menu', 'My menu.'):
            with self.subTest(wanted=wanted):
                session = onboard_help.HelpSession(guide)
                words = session.topic(wanted)
                self.assertNotIn(onboard_help.NOT_FOUND, words)
                self.assertEqual(session.topics[session.topic_index]['name'].casefold(), 'change your options', words)
                self.assertTrue(words.startswith('Favorite apps in Options'), words)
        session = onboard_help.HelpSession(guide)
        self.assertNotIn(onboard_help.NOT_FOUND, session.topic('my email'))   # "my" before other names still goes

    def test_the_guide_describes_the_list(self):
        from pathlib import Path
        text = Path(companion.__file__).with_name('START HERE - Veteran.txt').read_text(encoding='utf-8')
        section = text[text.index('25.11 Favorite apps in Options\nThis category'):text.index('26. SLEEP, EXIT')]
        for words in ('Space: select or unselect', 'Control+Up Arrow and Control+Down Arrow', '"Move to top"',
                      'Email, moved to 2 of 12.', 'They stay selected, in the same order.'):
            self.assertIn(words, section)
        self.assertIn('  25.11 Favorite apps in Options\n', text)
        self.assertNotIn('check box for each app', text)


if __name__ == '__main__':
    unittest.main()
