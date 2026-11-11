"""Windows checks for Options, Favorite apps, and the Tab order of the real Options dialog.

The list itself is tested on any computer in test_favorite_apps.py. These tests drive the
Win32 dialog in native_settings.py: the list box, its keys and words, and that Tab moves only
between the controls that matter (the list, then OK and Cancel), never to the helper buttons
for a mouse (Will, November 10, 2026).
"""
import ctypes as c
from ctypes import wintypes as w
import sys
import time
import unittest

from native_settings import NativeSettings
from real_window_tests import real_window
from settings_model import DEFAULTS, SettingsSession


# Like the window key tests, this class runs on Windows in its own process, never in the long
# shared run (real_window_tests.py). It is new: try it on a claude/try-... branch before it
# joins the window test list in build-windows.ps1.
@unittest.skipUnless(sys.platform == 'win32', 'Native Windows controls require Windows')
@real_window
class FavoriteAppsDialogTests(unittest.TestCase):
    def open_panel(self, values=None):
        self.saved = []; self.notices = []
        context = {'engines': ('windows',), 'windows_voices': ('Test voice',), 'espeak_voices': (), 'ai_voices': ('coral',),
                   'accounts': (), 'podcasts': (), 'podcast_limits': {}}
        base = DEFAULTS | {'rate': '0', 'volume': '100', 'punctuation': 'some', 'input_mode': 'mixed', 'engine': 'windows',
                           'windows_voice': 'Test voice', 'ai_voice': 'coral', 'email_list_size': '10', 'browser': 'Chrome',
                           'radio_source': 'all', 'podcast_limit': 'manual', 'ai_consent': False, 'remove_ai': False, 'api_key': ''}
        self.session = SettingsSession(base | (values or {}), context)
        def save(values): self.saved.append(values); self.panel.accepted()
        self.panel = NativeSettings(self.session, self.notices.append, save, lambda key: None).start()
        self.assertTrue(self.panel.ready.wait(8)); self.assertFalse(self.panel.closed.is_set(), self.notices)
        self.u = c.WinDLL('user32', use_last_error=True)
        self.u.GetDlgItem.restype = w.HWND; self.u.GetDlgItem.argtypes = [w.HWND, c.c_int]
        self.u.GetFocus.restype = w.HWND
        self.u.SendMessageW.restype = c.c_ssize_t; self.u.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        self.u.PostMessageW.restype = w.BOOL; self.u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        return self.panel.hwnd

    def tearDown(self):
        if hasattr(self, 'panel') and not self.panel.closed.is_set():
            self.panel.cancel(); self.panel.closed.wait(3)

    def wait(self, condition):
        until = time.monotonic() + 5
        while not condition() and time.monotonic() < until: time.sleep(.02)
        self.assertTrue(condition(), self.notices)

    def said(self, words):
        self.wait(lambda: any(words in notice for notice in self.notices))

    def press(self, control, key):
        before = len(self.notices)
        self.u.PostMessageW(control, 0x100, key, 0); self.u.PostMessageW(control, 0x101, key, 0)
        self.wait(lambda: len(self.notices) > before)
        return self.notices[-1]

    def line(self, listbox, index):
        buffer = c.create_unicode_buffer(256)
        self.u.SendMessageW(listbox, 0x189, index, c.cast(buffer, c.c_void_p).value)   # LB_GETTEXT
        return buffer.value

    def test_the_list_selects_moves_and_saves(self):
        hwnd = self.open_panel({'favorite_email': True})
        self.panel.command('Favorite apps')
        self.wait(lambda: bool(self.u.GetDlgItem(hwnd, 200)))
        apps = self.u.GetDlgItem(hwnd, 200)
        self.said('Favorite apps dialog. Apps, list box. File manager, not selected, 1 of 12.')
        self.assertEqual(self.line(apps, 3), 'Email, selected')
        self.assertEqual(self.press(apps, 0x26), 'Start of list.')
        self.assertEqual(self.press(apps, 0x28), 'Word processor, not selected, 2 of 12.')
        self.assertEqual(self.press(apps, 0x20), 'Word processor, selected.')
        self.assertTrue(self.session.values['favorite_word_processor'])
        self.assertEqual(self.line(apps, 1), 'Word processor, selected')
        self.panel.command('Move up.')
        self.said('Word processor, moved to 1 of 12.')
        self.assertEqual(int(self.u.SendMessageW(apps, 0x188, 0, 0)), 0)
        self.assertEqual(self.line(apps, 0), 'Word processor, selected')
        self.assertEqual(self.press(apps, ord('E')), 'Email, selected, 4 of 12.')
        self.panel.command('move to top')
        self.said('Email, moved to 1 of 12.')
        self.u.PostMessageW(apps, 0x100, 0x0D, 0)
        self.wait(lambda: len(self.saved) == 1)
        self.assertEqual(self.saved[0]['favorite_order'][:3], ['Email', 'Word processor', 'File manager'])
        self.assertTrue(self.saved[0]['favorite_word_processor'] and self.saved[0]['favorite_email'])

    def test_escape_keeps_the_earlier_list(self):
        hwnd = self.open_panel()
        self.panel.command('Favorite apps')
        self.wait(lambda: bool(self.u.GetDlgItem(hwnd, 200)))
        apps = self.u.GetDlgItem(hwnd, 200)
        self.press(apps, 0x20); self.panel.command('move to bottom'); self.said('File manager, moved to 12 of 12.')
        self.u.PostMessageW(apps, 0x100, 0x1B, 0)
        self.said('Changes canceled.')
        self.assertFalse(self.session.values['favorite_file_manager'])
        self.assertEqual(list(self.session.values['favorite_order'])[0], 'File manager')

    def tab_stops(self, hwnd, start, count=6):
        names = []
        for _ in range(count):
            focused = self.u.GetFocus() or start
            before = len(self.notices)
            self.u.PostMessageW(focused, 0x100, 9, 0)
            self.wait(lambda: len(self.notices) > before)
            names.append(self.notices[-1].split(',')[0])
        return names

    def test_tab_moves_between_the_list_ok_and_cancel_only(self):
        hwnd = self.open_panel()
        self.panel.command('Favorite apps')
        self.wait(lambda: bool(self.u.GetDlgItem(hwnd, 200)))
        stops = self.tab_stops(hwnd, self.u.GetDlgItem(hwnd, 200))
        self.assertEqual(stops[:3], ['OK', 'Cancel', 'Apps'])
        self.assertNotIn('Move up', stops); self.assertNotIn('Select or unselect', stops)

    def test_tab_never_stops_on_the_email_header_helper_buttons(self):
        hwnd = self.open_panel()
        self.panel.command('Email options')
        self.wait(lambda: bool(self.u.GetDlgItem(hwnd, 200)))
        stops = self.tab_stops(hwnd, self.u.GetDlgItem(hwnd, 200), count=12)
        for helper in ('Enable / disable', 'Move up', 'Move down'):
            self.assertNotIn(helper, stops)
        self.assertIn('Spoken email headers', stops)
        self.assertIn('OK', stops)


if __name__ == '__main__':
    unittest.main()
