"""Will, November 2, 2026: Chrome and the Voice Companion extension are set up the first time the
web or YouTube opens, with no need to know about "Set up Chrome". Set up Chrome stays for later,
and a person who says cancel is not asked again."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import chrome_setup
from chrome_setup import MESSAGES, ChromeSetup


class FakeChrome:
    """Behaves as WindowsChrome does for setup. installed: Chrome is there; extension: its state."""
    def __init__(self, installed=True, extension=None, install_works=True):
        self.installed, self.extension, self.install_works = installed, extension, install_works
        self.calls = []

    def supported(self):
        return True

    def find_chrome(self):
        return 'chrome.exe' if self.installed else None

    def extension_state(self):
        return self.extension

    def add_extension(self):
        self.calls.append('add_extension')
        self.extension = 'enabled'

    def remove_extension(self):
        self.calls.append('remove_extension')

    def open_chrome(self, address=None):
        self.calls.append(('open', address))
        return True

    def install_chrome(self, progress, canceled):
        self.calls.append('install')
        self.installed = self.install_works
        return self.install_works


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def wait_for(condition, seconds=3):
    end = time.monotonic() + seconds
    while not condition() and time.monotonic() < end:
        time.sleep(0.01)
    return condition()


class AutomaticSetupTests(unittest.TestCase):
    def setup_for(self, chrome, linked):
        clock = Clock()
        return ChromeSetup(chrome, lambda: linked['now'], clock=clock, automatic=True), clock

    def test_chrome_missing_installs_adds_the_extension_and_links_without_questions(self):
        chrome, linked = FakeChrome(installed=False), {'now': False}
        setup, clock = self.setup_for(chrome, linked)
        self.assertEqual(setup.start_automatic(), MESSAGES['installing'])
        self.assertIsNone(setup.question)
        self.assertTrue(wait_for(lambda: not setup.worker.is_alive()))
        said = setup.poll()
        self.assertEqual(said, ['Google Chrome is installed. ' + MESSAGES['added']])
        self.assertIn('add_extension', chrome.calls)
        self.assertIsNone(setup.question)                    # never a yes or no
        linked['now'] = True
        self.assertEqual(setup.poll(), [MESSAGES['first_linked']])
        self.assertTrue(setup.finished)

    def test_extension_already_on_just_links(self):
        setup, _ = self.setup_for(FakeChrome(extension='enabled'), {'now': False})
        self.assertEqual(setup.start_automatic(), MESSAGES['already_added'])
        self.assertEqual(setup.state, 'linking')

    def test_extension_that_does_not_link_goes_to_the_store_without_asking(self):
        chrome = FakeChrome()
        setup, clock = self.setup_for(chrome, {'now': False})
        setup.start_automatic()
        clock.now += ChromeSetup.WAIT_SECONDS + 1
        self.assertEqual(setup.poll(), [MESSAGES['store']])
        self.assertIn(('open', chrome_setup.STORE_PAGE), chrome.calls)
        self.assertIsNone(setup.question)

    def test_cancel_says_how_to_set_it_up_later(self):
        setup, _ = self.setup_for(FakeChrome(), {'now': False})
        setup.start_automatic()
        self.assertEqual(setup.respond('cancel'), MESSAGES['first_canceled'])
        self.assertTrue(setup.finished)

    def test_a_failed_install_says_what_to_do(self):
        chrome = FakeChrome(installed=False, install_works=False)
        setup, _ = self.setup_for(chrome, {'now': False})
        setup.start_automatic()
        self.assertTrue(wait_for(lambda: not setup.worker.is_alive()))
        self.assertEqual(setup.poll(), [MESSAGES['install_failed']])


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.said = []
        self.app = SimpleNamespace(APP=self.folder, speak=self.said.append, speak_status=self.said.append,
                                   CHROME_SETUP=None, CHROME_SETUP_RETURN=None, web_session=None,
                                   sync_app_context=lambda *a: None, APP_WINDOW=object())
        self.chrome = FakeChrome()
        self.linked = {'now': False}
        for target in (patch.object(chrome_setup, 'WindowsChrome', lambda: self.chrome),
                       patch.object(chrome_setup, 'relay_connected', lambda app: self.linked['now']),
                       patch.object(chrome_setup, 'FocusReader', lambda speak: Mock())):
            target.start(); self.addCleanup(target.stop)

    def test_the_first_time_only(self):
        self.assertEqual(chrome_setup.first_run(self.app, 'awake', 'browser_menu'), 'chrome_setup')
        self.assertTrue(self.said[-1].startswith(MESSAGES['first_run']), self.said[-1])
        self.assertEqual(self.app.CHROME_SETUP_RETURN, 'browser_menu')
        # Asked once, whatever the answer: the next time the web opens as usual.
        self.app.CHROME_SETUP = None
        self.assertIsNone(chrome_setup.first_run(self.app, 'awake', 'browser_menu'))

    def test_once_linked_chrome_is_the_web_browser_and_the_menu_follows(self):
        menu = Mock(); menu.start.return_value = 'Web browser menu.'
        self.app.web_session = SimpleNamespace(menu=menu, saved_choice=None, chrome_offer_declined=None)
        chrome_setup.first_run(self.app, 'awake', 'browser_menu')
        self.linked['now'] = True
        self.assertEqual(chrome_setup.poll(self.app, 'chrome_setup'), 'browser_menu')
        self.assertIn(MESSAGES['first_linked'], self.said)
        self.assertEqual(self.said[-1], 'Web browser menu.')
        self.assertEqual((self.folder / 'browser-choice.txt').read_text(encoding='utf-8'), 'chrome')
        self.assertEqual((self.folder / chrome_setup.FIRST_RUN_FILE).read_text(encoding='utf-8'), 'linked')
        self.assertEqual(self.app.web_session.saved_choice, 'chrome')

    def test_cancel_keeps_embedded_edge_and_is_remembered(self):
        self.app.web_session = SimpleNamespace(menu=Mock(), saved_choice=None, chrome_offer_declined=None)
        self.app.normalized_command = lambda text: text.lower().strip(' .')
        self.app.speech_control = lambda text: None
        self.app.spoken_control = lambda text: None
        chrome_setup.first_run(self.app, 'awake', 'browser_menu')
        self.assertEqual(chrome_setup.handle(self.app, 'Cancel.', 'chrome_setup'), 'browser_menu')
        self.assertIn(MESSAGES['first_canceled'], self.said)
        self.assertTrue(self.app.web_session.chrome_offer_declined)
        self.assertEqual((self.folder / chrome_setup.FIRST_RUN_FILE).read_text(encoding='utf-8'), 'declined')
        self.assertFalse((self.folder / 'browser-choice.txt').exists())

    def test_embedded_edge_chosen_on_purpose_is_left_alone(self):
        (self.folder / 'browser-choice.txt').write_text('webview2', encoding='utf-8')
        self.assertIsNone(chrome_setup.first_run(self.app, 'awake', 'browser_menu'))

    def test_never_in_text_mode_or_without_the_window(self):
        self.app.APP_WINDOW = None
        self.assertIsNone(chrome_setup.first_run(self.app, 'awake', 'browser_menu'))

    def test_already_linked_is_never_set_up(self):
        self.linked['now'] = True
        self.assertIsNone(chrome_setup.first_run(self.app, 'awake', 'browser_menu'))
        self.assertEqual((self.folder / chrome_setup.FIRST_RUN_FILE).read_text(encoding='utf-8'), 'linked')
        self.assertEqual(self.chrome.calls, [])


if __name__ == '__main__':
    unittest.main()
