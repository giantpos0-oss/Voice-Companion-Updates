"""Will, November 4, 2026: Start File manager in offers the places Windows shows now, such as
C drive, a USB drive, Dropbox, OneDrive or Google Drive, and nothing that is not there."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import file_manager
from file_manager import Item, start_location, start_places
from settings_model import DEFAULTS, SettingsSession, fields


class Shell:
    def __init__(self, root):
        self.root = root

    def roots(self):
        return [Item('Local Disk (C:)', str(self.root / 'C'), True, True), Item('USB Drive (D:)', str(self.root / 'D'), True, True),
                Item('Dropbox', str(self.root / 'Dropbox'), True, True), Item('Google Drive (G:)', str(self.root / 'G'), True, True)]


class StartPlaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('C', 'D', 'Dropbox', 'G', 'Documents'):
            (self.root / name).mkdir()
        known = {'Documents': self.root / 'Documents', 'Desktop': self.root / 'not here'}
        patcher = patch('downloads.known_folder', lambda guid, name: known.get(name, self.root / ('missing ' + name)))
        patcher.start(); self.addCleanup(patcher.stop)

    def test_only_places_windows_shows_are_offered(self):
        places = start_places(Shell(self.root))
        self.assertEqual([name for name, _ in places], ['Local Disk (C:)', 'USB Drive (D:)', 'Dropbox', 'Google Drive (G:)', 'Documents'])
        context = {'file_places': dict(places)}
        field = next(f for f in fields('File manager options', context) if f.key == 'file_manager_start')
        self.assertEqual(field.choices, ('drive list', 'Local Disk (C:)', 'USB Drive (D:)', 'Dropbox', 'Google Drive (G:)', 'Documents'))

    def test_a_chosen_place_is_saved_as_its_folder_and_shown_by_name(self):
        places = dict(start_places(Shell(self.root)))
        session = SettingsSession(DEFAULTS | {'file_manager_start': 'drive list'}, {'file_places': places})
        session.set('file_manager_start', 'Dropbox')
        self.assertEqual(session.values['file_manager_start'], str(self.root / 'Dropbox'))
        self.assertEqual(start_location(session.values['file_manager_start']), str(self.root / 'Dropbox'))
        import app_settings
        self.assertEqual(app_settings.start_label(str(self.root / 'Dropbox') + '\\', places), 'Dropbox')
        # Saved again without a change: still the folder, never the name.
        again = SettingsSession(DEFAULTS | {'file_manager_start': 'Dropbox'}, {'file_places': places})
        again.set('file_manager_start', 'Dropbox')
        self.assertEqual(again.values['file_manager_start'], str(self.root / 'Dropbox'))

    def test_a_drive_that_is_unplugged_opens_the_drive_list(self):
        self.assertIsNone(start_location(str(self.root / 'E')))

    def test_a_shell_problem_still_offers_your_folders(self):
        class Broken:
            def roots(self):
                raise OSError('no shell')
        self.assertEqual(start_places(Broken()), [('Documents', str(self.root / 'Documents'))])


if __name__ == '__main__':
    unittest.main()
