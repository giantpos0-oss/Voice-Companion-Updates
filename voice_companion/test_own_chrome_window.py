"""Will, November 2, 2026: a setting, off by default, that hides your own Chrome while Voice Companion
uses it. Only Chrome windows Companion opened; "Show browser window" brings them back."""
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import own_chrome_window
from own_chrome_window import HIDE, SHOW, OwnChromeWindows
from window_hiding import Window


class FakeDesktop:
    """Behaves as window_hiding.Win32Desktop does for these calls."""
    def __init__(self, handles=()):
        self.open = {h: {'style': 0x100, 'pos': (10 * h, 20), 'parked': False} for h in handles}
        self.forward = []

    def windows(self):
        return [Window(h, 'Chrome_WidgetWin_1', 'Chrome', False, False, w['parked']) for h, w in sorted(self.open.items())]

    def exists(self, h):
        return h in self.open

    def position(self, h):
        return None if self.open[h]['parked'] else self.open[h]['pos']

    def park(self, h):
        w = self.open[h]; before = w['style']
        w['style'] |= 0x80; w['parked'] = True; w['pos'] = (-32000, -32000)
        return before

    def untuck(self, h, style=None):
        w = self.open[h]; w['style'] = style; w['parked'] = False

    def place(self, h, pos):
        self.open[h]['pos'] = pos

    def bring_forward(self, h):
        self.forward.append(h)


class OwnChromeWindowTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, own_chrome_window, 'ENABLED', False)
        own_chrome_window.ENABLED = False
        self.desktop = FakeDesktop([7])            # 7 is a Chrome window you opened yourself
        self.windows = OwnChromeWindows(desktop=lambda: self.desktop, sleep=lambda s: None)

    def start_chrome(self):
        before = self.windows.current()
        self.desktop.open[42] = {'style': 0x100, 'pos': (300, 200), 'parked': False}
        return self.windows.opened(before)

    def test_off_by_default_nothing_is_hidden(self):
        self.assertEqual(own_chrome_window.CHOICES[0], SHOW)
        from settings_model import DEFAULTS
        self.assertEqual(DEFAULTS['own_chrome_window'], SHOW)
        self.assertEqual(self.start_chrome(), {42})
        self.assertFalse(self.desktop.open[42]['parked'])
        self.assertIsNone(own_chrome_window.command(True))   # your Chrome keeps its window, as before

    def test_on_only_the_window_companion_opened_is_hidden_and_comes_back_where_it_was(self):
        own_chrome_window.ENABLED = True
        self.start_chrome()
        self.assertTrue(self.desktop.open[42]['parked'])
        self.assertFalse(self.desktop.open[7]['parked'])      # yours is never touched
        self.assertTrue(self.windows.is_hidden())
        self.assertEqual(self.windows.show(), 1)
        self.assertEqual(self.desktop.open[42], {'style': 0x100, 'pos': (300, 200), 'parked': False})
        self.assertEqual(self.desktop.forward, [42])
        self.assertEqual(self.windows.hide(), 1)               # hide browser window again
        self.assertTrue(self.desktop.open[42]['parked'])

    def test_a_window_closed_meanwhile_is_forgotten(self):
        own_chrome_window.ENABLED = True
        self.start_chrome()
        del self.desktop.open[42]
        self.assertEqual(self.windows.show(), 0)
        self.assertEqual(self.windows.hide(), 0)
        self.assertEqual(self.windows.mine, set())

    def test_the_option_turned_on_or_off_acts_at_once(self):
        with patch.object(own_chrome_window, 'WINDOWS', self.windows):
            self.start_chrome()
            own_chrome_window.set_enabled(HIDE)
            self.assertTrue(self.desktop.open[42]['parked'])
            self.assertEqual(own_chrome_window.command(False), own_chrome_window.HIDDEN_NOW)
            self.assertEqual(own_chrome_window.command(True), own_chrome_window.SHOWN_NOW)
            self.assertEqual(own_chrome_window.command(True), own_chrome_window.NOTHING_TO_SHOW)
            own_chrome_window.set_enabled(HIDE)
            own_chrome_window.set_enabled(SHOW)
            self.assertFalse(self.desktop.open[42]['parked'])
            self.assertEqual(self.desktop.forward, [42])      # brought forward only when asked

    def test_a_chrome_that_was_already_open_cannot_be_hidden(self):
        own_chrome_window.ENABLED = True
        with patch.object(own_chrome_window, 'WINDOWS', self.windows):
            self.assertEqual(own_chrome_window.command(False), own_chrome_window.NOTHING_TO_HIDE)
        self.assertFalse(self.desktop.open[7]['parked'])

    def test_starting_your_chrome_records_its_window(self):
        import browser_cdp_relay
        import chrome_setup
        own_chrome_window.ENABLED = True
        relay = Mock(); relay.connected = threading.Event()
        desktop = self.desktop

        class Chrome:
            def supported(self): return True
            def extension_state(self): return 'enabled'
            def open_chrome(self, address):
                desktop.open[42] = {'style': 0x100, 'pos': (300, 200), 'parked': False}
                relay.connected.set(); return True
        app = SimpleNamespace(APP=tempfile.mkdtemp(), speak_status=lambda words: None)
        self.addCleanup(chrome_setup.LAUNCH.update, {'at': None, 'failed': None})
        with patch.object(own_chrome_window, 'WINDOWS', self.windows), patch.object(browser_cdp_relay, 'prepared', lambda: relay), \
                patch.object(chrome_setup, 'WindowsChrome', Chrome):
            self.assertIs(chrome_setup.link_own_chrome(app, 'https://www.youtube.com/'), True)
        self.assertEqual(self.windows.mine, {42})
        self.assertTrue(self.desktop.open[42]['parked'])

    def test_web_screen_show_and_hide_use_the_option(self):
        from web_assistant import WINDOW_OWN_BROWSER, WebSession
        session = WebSession.__new__(WebSession)
        session.backend = SimpleNamespace(regular=True)
        self.assertEqual(session.browser_window(True), WINDOW_OWN_BROWSER)
        own_chrome_window.ENABLED = True
        with patch.object(own_chrome_window, 'WINDOWS', self.windows):
            self.start_chrome()
            self.assertEqual(session.browser_window(True), own_chrome_window.SHOWN_NOW)
            self.assertEqual(session.browser_window(False), own_chrome_window.HIDDEN_NOW)


if __name__ == '__main__':
    unittest.main()
