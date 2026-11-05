"""Will, November 4, 2026: File manager like Leasey. Companion tags (Space) that act on several
items, even across folders; Alt+Z zips and Alt+U unzips; Control+1 to Control+5 sort, and the same
key again flips the order; Alt+Enter Properties read with the arrows, with music details; no Tab
stops: Search and Sort live on the Alt menu, sorted into groups."""
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

import file_tools
from file_manager import FileManager, Item
from test_file_manager import FakeFiles, settle


class Folders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'Photos').mkdir()
        (self.root / 'Photos' / 'cat.jpg').write_bytes(b'cat' * 100)
        (self.root / 'Photos' / 'Empty').mkdir()
        (self.root / 'a.txt').write_text('Alpha')
        (self.root / 'b.txt').write_text('Bravo bravo')
        (self.root / 'song.mp3').write_bytes(b'ID3' + b'\0' * 50)
        self.backend = FakeFiles(self.root)
        self.fm = FileManager(self.backend)
        self.fm.refresh()
        settle(self.fm)
        self.fm.command('enter')
        settle(self.fm)

    def go(self, name):
        self.fm.choose(name)


class CompanionTagTests(Folders):
    def test_space_tags_and_untags_and_says_how_many(self):
        self.go('a.txt')
        self.assertEqual(self.fm.command('toggle tag'), 'Tagged. 1 item tagged.')
        self.assertIn('tagged', self.fm.labels()[self.fm.index])
        self.go('b.txt')
        self.assertEqual(self.fm.command('toggle tag'), 'Tagged. 2 items tagged.')
        self.assertEqual(self.fm.command('toggle tag'), 'Untagged. 1 item tagged.')
        self.assertEqual(self.fm.command('what is tagged'), '1 item tagged: a.txt.')
        self.assertEqual(self.fm.command('clear tags'), 'Tags cleared.')
        self.assertEqual(self.fm.command('what is tagged'), 'Nothing is tagged. ' + self.fm.say_current())

    def test_spoken_tag_words_with_the_period_speech_adds(self):
        # Will, November 4, 2026: "Tag." alone was taken as an item name.
        self.go('a.txt')
        self.assertEqual(self.fm.command('Tag.'), 'Tagged. 1 item tagged.')
        self.assertEqual(self.fm.command('Untag.'), 'Untagged. No items tagged.')
        self.assertEqual(self.fm.command('Tag it.'), 'Tagged. 1 item tagged.')
        self.assertEqual(self.fm.command('Untag this one.'), 'Untagged. No items tagged.')
        self.assertEqual(self.fm.command('Tag b.txt.'), 'Tagged. 1 item tagged.')
        self.assertEqual(self.fm.current().name, 'b.txt')

    def test_tags_stay_when_you_open_another_folder_and_all_are_copied(self):
        self.go('a.txt'); self.fm.command('toggle tag')
        self.go('Photos'); self.fm.command('open'); settle(self.fm)
        self.go('cat.jpg'); self.fm.command('toggle tag')
        self.assertEqual(self.fm.command('what is tagged'), '2 items tagged: a.txt, cat.jpg.')
        self.fm.command('copy'); settle(self.fm)
        self.assertEqual(self.backend.clip[0], [str(self.root / 'a.txt'), str(self.root / 'Photos' / 'cat.jpg')])

    def test_old_selection_words_and_keys_still_tag(self):
        for words in ('select a.txt', 'mark b.txt'):
            self.fm.command(words)
        self.assertEqual(len(self.fm.selected), 2)
        self.fm.command('clear selection')
        self.assertEqual(self.fm.selected, set())
        self.fm.command('tag all')
        self.assertEqual(len(self.fm.selected), len(self.fm.items))

    def test_tags_clear_after_the_action(self):
        self.go('a.txt'); self.fm.command('toggle tag')
        self.fm.command('delete'); self.fm.command('yes'); settle(self.fm)
        self.assertEqual(self.backend.actions[0][:2], ('delete', [str(self.root / 'a.txt')]))
        self.assertEqual(self.fm.selected, set())


class ZipTests(Folders):
    def test_alt_z_suggests_a_name_and_zips_the_tagged_items(self):
        for name in ('a.txt', 'Photos'):
            self.go(name); self.fm.command('toggle tag')
        said = self.fm.command('zip')
        self.assertEqual(self.fm.pending[0], 'zip')
        self.assertEqual(self.fm.zip_suggestion, Path(self.tmp.name).name + '.zip')
        self.assertIn('Enter', said)
        said = self.fm.command('Holiday'); said += ' ' + settle(self.fm)
        made = self.root / 'Holiday.zip'
        self.assertTrue(made.is_file(), said)
        with zipfile.ZipFile(made) as archive:
            self.assertEqual(sorted(archive.namelist()), ['Photos/Empty/', 'Photos/cat.jpg', 'a.txt'])
        self.assertIn('Zipped 2 items into Holiday.zip', said)
        self.assertEqual(self.fm.selected, set())
        self.assertEqual(self.fm.current().name, 'Holiday.zip')

    def test_one_item_suggests_its_own_name_and_never_replaces(self):
        self.go('a.txt')
        self.fm.command('zip')
        self.assertEqual(self.fm.zip_suggestion, 'a.zip')
        (self.root / 'a.zip').write_text('keep me')
        with self.assertRaises(ValueError):
            file_tools.make_zip([self.root / 'a.txt'], self.root / 'a.zip')
        self.assertEqual((self.root / 'a.zip').read_text(), 'keep me')
        self.assertEqual(file_tools.zip_name([self.root / 'a.txt'], self.root), 'a (1).zip')

    def test_alt_u_unzips_into_a_new_folder_named_after_it(self):
        file_tools.make_zip([self.root / 'Photos', self.root / 'b.txt'], self.root / 'Trip.zip')
        self.fm.command('refresh'); settle(self.fm)
        self.go('Trip.zip')
        said = self.fm.command('unzip'); said += ' ' + settle(self.fm)
        self.assertIn('Unzipped Trip.zip into the Trip folder', said)
        self.assertEqual((self.root / 'Trip' / 'b.txt').read_text(), 'Bravo bravo')
        self.assertTrue((self.root / 'Trip' / 'Photos' / 'Empty').is_dir())
        self.fm.command('refresh'); settle(self.fm)
        self.go('Trip.zip'); self.fm.command('unzip'); settle(self.fm)
        self.assertTrue((self.root / 'Trip (1)' / 'b.txt').exists())   # never mixed into the first

    def test_a_zip_that_points_outside_its_folder_is_kept_inside(self):
        bad = self.root / 'bad.zip'
        with zipfile.ZipFile(bad, 'w') as archive:
            archive.writestr('../escaped.txt', 'no')
            archive.writestr('C:/Windows/evil.txt', 'no')
            archive.writestr('fine/ok.txt', 'yes')
        folder, count = file_tools.unzip_file(bad)
        self.assertEqual(count, 1)
        self.assertFalse((self.root.parent / 'escaped.txt').exists())
        self.assertEqual((folder / 'fine' / 'ok.txt').read_text(), 'yes')
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.endswith('.unzipping')], [])

    def test_unzip_says_what_is_wrong(self):
        (self.root / 'broken.zip').write_text('not a zip')
        with self.assertRaisesRegex(ValueError, 'not a working zip file'):
            file_tools.unzip_file(self.root / 'broken.zip')
        self.go('a.txt')
        with self.assertRaisesRegex(ValueError, 'not a zip file'):
            self.fm.command('unzip')


class SortKeyTests(Folders):
    def test_control_numbers_sort_and_the_same_key_flips_the_order(self):
        self.assertTrue(self.fm.command('sort key name').startswith('Sorted by name, descending.'))
        self.assertTrue(self.fm.command('sort key name').startswith('Sorted by name, ascending.'))
        for key, word in (('date modified', 'date modified'), ('type', 'type'), ('size', 'size'), ('date created', 'date created')):
            self.assertTrue(self.fm.command('sort key ' + key).startswith('Sorted by ' + word + ', ascending.'), key)
            self.assertTrue(self.fm.command('sort key ' + key).startswith('Sorted by ' + word + ', descending.'), key)

    def test_size_and_type_order_files_with_folders_first(self):
        view = self.fm.view
        view.all_items = [Item('z.txt', 'z', size=5), Item('a.mp3', 'a', size=50), Item('Folder', 'f', True), Item('m.doc', 'm', size=1)]
        view.sort, view.descending = 'size', False
        self.assertEqual([i.name for i in view.shown()], ['Folder', 'm.doc', 'z.txt', 'a.mp3'])
        view.sort = 'type'
        self.assertEqual([i.name for i in view.shown()], ['Folder', 'm.doc', 'a.mp3', 'z.txt'])


class AltMenuTests(Folders):
    def test_alt_menu_groups_actions_search_sort_and_go_to(self):
        top = self.fm.command('file manager menu')
        self.assertTrue(top.startswith('File manager menu. Actions'), top)
        self.assertEqual([label.split(',')[0] for label in self.fm.labels()], ['Actions', 'Search', 'Sort', 'Go to'])
        self.fm.command('next'); self.fm.command('next')
        self.assertTrue(self.fm.command('enter').startswith('Sort. Name. Control+1.'))
        self.assertIn('Control+3', ' '.join(self.fm.labels()))
        self.assertTrue(self.fm.command('escape').startswith('File manager menu. Sort'))
        self.fm.command('home'); self.fm.command('enter')
        labels = ' '.join(self.fm.labels())
        for words in ('Space', 'Alt+Z', 'Alt+U', 'Alt+Enter', 'Control+C'):
            self.assertIn(words, labels)
        self.fm.command('escape'); self.fm.command('escape')
        self.assertFalse(self.fm.menu)

    def test_a_submenu_item_runs_its_command(self):
        self.fm.command('file manager menu'); self.fm.command('next'); self.fm.command('next')
        self.fm.command('enter'); self.fm.command('next')
        self.assertTrue(self.fm.command('enter').startswith('Sorted by date modified'))
        self.assertFalse(self.fm.menu)


class PropertiesTests(Folders):
    def test_alt_enter_lists_properties_read_with_the_arrows(self):
        self.go('b.txt')
        said = self.fm.command('properties'); said += ' ' + settle(self.fm)
        self.assertEqual(self.fm.menu, 'properties')
        self.assertIn('Properties of b.txt. Name: b.txt.', said)
        labels = self.fm.labels()
        self.assertEqual(labels[:3], ['Name: b.txt', 'Type: TXT file', 'Size: 11 bytes'])
        self.assertTrue(any(line.startswith('Modified: ') for line in labels))
        self.assertTrue(self.fm.command('next').startswith('Type: TXT file. 2 of'))
        self.assertTrue(self.fm.command('escape').startswith('b.txt, file'))
        self.assertFalse(self.fm.menu)

    def test_music_files_add_their_details(self):
        self.backend.extended = lambda path: [('Title', 'Supplier'), ('Artist', 'Young Fletcher'), ('Album', ''), ('Genre', 'Hip hop'),
                                              ('Year', '2024'), ('Length', '3 minutes, 5 seconds')]
        self.go('song.mp3'); self.fm.command('properties'); settle(self.fm)
        labels = self.fm.labels()
        self.assertEqual(labels[2:7], ['Title: Supplier', 'Artist: Young Fletcher', 'Genre: Hip hop', 'Year: 2024', 'Length: 3 minutes, 5 seconds'])

    def test_folder_properties_count_what_is_inside(self):
        self.go('Photos'); self.fm.command('properties'); settle(self.fm)
        self.assertIn('Contains: 1 file, 1 folder', self.fm.labels())

    def test_shell_values_read_naturally(self):
        self.assertEqual(file_tools.detail_text('Length', 1_850_000_000), '3 minutes, 5 seconds')
        self.assertEqual(file_tools.detail_text('Artist', ('A', 'B')), 'A, B')
        self.assertEqual(file_tools.detail_text('Bit rate', 320000), '320 kbps')
        self.assertEqual(file_tools.detail_text('Year', 0), '')


class KeyboardTests(unittest.TestCase):
    def test_new_keys_reach_the_new_commands(self):
        import companion
        expected = {'Space': 'toggle tag', 'Ctrl+A': 'tag all', 'Ctrl+Shift+A': 'clear tags', 'Ctrl+Shift+T': 'what is tagged',
                    'Alt+Z': 'zip', 'Alt+U': 'unzip', 'Alt+Enter': 'properties',
                    'Ctrl+1': 'sort key name', 'Ctrl+2': 'sort key date modified', 'Ctrl+3': 'sort key type',
                    'Ctrl+4': 'sort key size', 'Ctrl+5': 'sort key date created',
                    # Older keys kept, as Will chose for every old key (November 3, 2026).
                    'Ctrl+Shift+1': 'sort by name', 'Alt+N': 'sort by name'}
        for key, command in expected.items():
            self.assertEqual(companion.navigation_key(key, 'files'), command, key)

    def test_the_window_has_no_file_buttons_to_tab_to(self):
        source = (Path(__file__).parent / 'app_window.py').read_text(encoding='utf-8')
        self.assertNotIn("('Search','search files'),('Search subfolders'", source)
        self.assertNotIn('def file_tab(', source)


if __name__ == '__main__':
    unittest.main()
