"""Will, November 1, 2026: YouTube kept opening new Chrome sessions, and the Web browser sometimes
opened in Voice Companion's own Chrome instead of his. Your own Chrome is now opened in one place
(chrome_setup.link_own_chrome), at most once while it starts, and YouTube reuses its own tabs."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import browser_cdp_relay
import chrome_setup
import youtube_screen as ys


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class LinkOwnChromeOnceTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(chrome_setup.LAUNCH.update, {'at': None, 'failed': None})
        chrome_setup.LAUNCH.update({'at': None, 'failed': None})
        self.app = Mock(APP=Path(tempfile.mkdtemp()))
        self.relay = Mock(); self.relay.connected = threading.Event()
        self.opened = []
        test = self

        class Chrome:
            links = True
            def supported(self): return True
            def extension_state(self): return 'enabled'
            def open_chrome(self, address):
                test.opened.append(address)
                if Chrome.links:
                    test.relay.connected.set()
                return True
        self.Chrome = Chrome
        for target in (patch.object(browser_cdp_relay, 'prepared', lambda: self.relay),
                       patch.object(chrome_setup, 'WindowsChrome', Chrome),
                       patch.object(chrome_setup, 'OWN_CHROME_SECONDS', 0.2)):
            target.start(); self.addCleanup(target.stop)

    def link(self, clock=None):
        return chrome_setup.link_own_chrome(self.app, 'https://www.youtube.com/', 'Opening.', clock=clock)

    def test_opens_once_and_says_so_in_the_log(self):
        self.assertIs(self.link(), True)
        self.assertIs(self.link(), True)                 # linked: nothing else opens
        self.assertEqual(self.opened, ['https://www.youtube.com/'])
        log = (self.app.APP / 'browser-log.txt').read_text(encoding='utf-8')
        self.assertIn('own Chrome: opened', log)
        self.assertIn('own Chrome: linked after', log)
        self.assertNotIn('youtube', log)                 # no page addresses are written

    def test_a_chrome_still_starting_is_waited_for_not_opened_again(self):
        self.Chrome.links = False
        clock = Clock()
        self.assertEqual(self.link(clock), chrome_setup.OWN_CHROME_NOT_LINKED)
        self.assertEqual(len(self.opened), 1)
        # Asked again at once (the Web browser right after YouTube): no second Chrome, no second wait.
        self.assertEqual(self.link(clock), chrome_setup.OWN_CHROME_NOT_LINKED)
        self.assertEqual(len(self.opened), 1)
        # Much later, it may try again.
        clock.now += chrome_setup.LAUNCH_SECONDS + 1
        self.Chrome.links = True
        self.assertIs(self.link(clock), True)
        self.assertEqual(len(self.opened), 2)

    def test_while_starting_a_second_request_waits_for_the_first(self):
        clock = Clock()
        chrome_setup.LAUNCH['at'] = clock.now             # another request just started Chrome
        threading.Timer(0.05, self.relay.connected.set).start()
        self.assertIs(self.link(clock), True)
        self.assertEqual(self.opened, [])

    def test_without_the_extension_nothing_opens(self):
        self.Chrome.extension_state = lambda self: None
        self.assertIsNone(self.link())
        self.assertEqual(self.opened, [])


class Page:
    def __init__(self, url):
        self.url = url
        self.closed = False

    def is_closed(self):
        return self.closed

    def set_default_timeout(self, value):
        pass


class OwnTabTests(unittest.TestCase):
    def screen(self, urls, regular=True):
        pages = [Page(u) for u in urls]
        context = SimpleNamespace(pages=pages, new_page=lambda: pages.append(Page('about:blank')) or pages[-1])
        backend = SimpleNamespace(regular=regular, context=context)
        m = Mock(PREFERENCES={}, APP=Path(tempfile.mkdtemp()), APP_WINDOW=None,
                 web_session=SimpleNamespace(backend=backend))
        return ys.YouTubeScreen(m), pages

    def test_an_open_youtube_tab_is_used_again(self):
        s, pages = self.screen(['https://mail.google.com/', 'https://www.youtube.com/results?search_query=jazz',
                                'https://www.youtube.com/watch?v=abc'])
        self.assertIs(s.own_tab('list'), pages[1])
        self.assertIs(s.own_tab('video', create=False), pages[2])
        self.assertEqual(len(pages), 3)                # no new tab

    def test_your_other_tabs_are_never_taken(self):
        s, pages = self.screen(['https://mail.google.com/'])
        tab = s.own_tab('list')
        self.assertIsNot(tab, pages[0])
        self.assertEqual(tab.url, 'about:blank')         # a new tab of its own
        s.list_page = tab
        self.assertIsNone(s.own_tab('video', create=False))   # Gmail is never used for a video

    def test_not_in_your_own_chrome_it_does_nothing(self):
        s, pages = self.screen(['https://www.youtube.com/'], regular=False)
        self.assertIsNone(s.own_tab('list'))


class WebOpensOwnChromeTests(unittest.TestCase):
    def test_every_way_into_the_web_tries_your_chrome_before_starting_another(self):
        from web_assistant import WebSession
        calls = []
        session = WebSession.__new__(WebSession)
        session.injected_backend = None
        session.backend = SimpleNamespace(regular=False, page=None, goto=lambda url: calls.append(('goto', url)))
        session.adopt_connected_browser = lambda: calls.append(('adopt',))
        with patch.object(WebSession, 'own_browser_opener', staticmethod(lambda s: calls.append(('own',)) or True)):
            session._navigate('https://example.com/')
        self.assertEqual(calls, [('own',), ('adopt',), ('goto', 'https://example.com/')])
        # A browser that already shows pages is kept.
        calls.clear(); session.backend.page = object()
        with patch.object(WebSession, 'own_browser_opener', staticmethod(lambda s: calls.append(('own',)) or True)):
            session._navigate('https://example.com/')
        self.assertEqual(calls, [('goto', 'https://example.com/')])

    def test_the_app_wires_its_opener(self):
        import companion
        from web_assistant import WebSession
        self.assertIs(WebSession.own_browser_opener, companion.open_own_chrome_for_web)


if __name__ == '__main__':
    unittest.main()
