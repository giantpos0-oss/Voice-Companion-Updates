"""Will, November 18, 2026: "I clicked on a link, it said loading page and that the page did not
load cleanly". Chrome held back the click (Companion's window in front makes Chrome count its own
window as hidden), so the click waited 10 seconds and failed. A click or key that gets no answer
is now done through the page itself. A real browser plays the part: a link covered by a layer
that takes every click can never get Chrome's own click, the same "no answer"."""
import tempfile
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:          # pragma: no cover
    sync_playwright = None

from web_assistant import BrowserBackend

PAGE = '''<!doctype html><title>t</title>
<a id="link" href="#" onclick="window.clicked=(window.clicked||0)+1;return false">Next page</a>
<form id="search" onsubmit="window.submitted=(window.submitted||0)+1;document.body.append('Results');return false"><input id="box" name="q" value="dogs"></form>
<div id="cover" style="position:fixed;inset:0;background:transparent"></div>'''


@unittest.skipIf(sync_playwright is None, 'needs Playwright')
class HeldBackInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.driver = sync_playwright().start()
            cls.browser = cls.driver.chromium.launch()
        except Exception as exc:     # no browser on this machine
            raise unittest.SkipTest('no browser: %s' % type(exc).__name__)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.driver.stop()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.page = self.browser.new_page(); self.addCleanup(self.page.close)
        self.page.set_content(PAGE)
        self.backend = BrowserBackend.__new__(BrowserBackend)
        self.backend.page, self.backend.folder = self.page, Path(self.folder.name)
        self.backend.INPUT_SECONDS = 0.5

    def log(self):
        path = Path(self.folder.name) / 'browser-log.txt'
        return path.read_text(encoding='utf-8') if path.exists() else ''

    def test_a_click_chrome_will_not_take_is_done_through_the_page(self):
        self.backend._act(self.page.locator('#link'))
        self.assertEqual(self.page.evaluate('window.clicked'), 1)
        self.assertIn('click got no answer in 0.5 seconds (TimeoutError), done through the page', self.log())

    def test_enter_in_a_search_box_still_submits(self):
        self.page.evaluate("document.getElementById('cover').remove()")
        self.page.evaluate("document.getElementById('box').addEventListener('keydown',e=>{if(!e.isTrusted)return;e.preventDefault();window.typed=1})")
        # Chrome's own key press works here: no fallback, nothing logged.
        self.backend._act(self.page.locator('#box'), key='Enter')
        self.assertEqual(self.page.evaluate('window.typed'), 1)
        self.assertEqual(self.log(), '')

    def test_enter_that_gets_no_answer_submits_the_form_through_the_page(self):
        box = self.page.locator('#box')
        held = type('Held', (), {'press': lambda self, *a, **k: (_ for _ in ()).throw(TimeoutError('held back')),
                                 'evaluate': lambda self, *a, **k: box.evaluate(*a, **k)})()
        self.backend._act(held, key='Enter')
        self.assertEqual(self.page.evaluate('window.submitted'), 1)
        self.assertIn('key Enter got no answer', self.log())

    def test_a_key_chrome_answers_late_is_not_pressed_twice(self):
        # Chrome took the Enter but answered after the wait: the form was sent once, and sending
        # it again through the page would search twice.
        self.page.evaluate("document.getElementById('cover').remove()")
        box = self.page.locator('#box')
        def late(*a, **k):
            box.press('Enter'); raise TimeoutError('answered late')
        held = type('Late', (), {'press': lambda self, *a, **k: late(),
                                 'evaluate': lambda self, *a, **k: box.evaluate(*a, **k)})()
        self.backend._act(held, key='Enter')
        self.assertEqual(self.page.evaluate('window.submitted'), 1)
        self.assertIn('the page had already answered; not done again', self.log())

    def test_a_tick_box_chrome_answers_late_is_not_unticked(self):
        self.page.evaluate("document.getElementById('cover').remove();document.body.insertAdjacentHTML('beforeend','<input type=checkbox id=tick>')")
        tick = self.page.locator('#tick')
        def late(*a, **k):
            tick.click(); raise TimeoutError('answered late')
        held = type('Late', (), {'click': lambda self, *a, **k: late(),
                                 'evaluate': lambda self, *a, **k: tick.evaluate(*a, **k)})()
        self.backend._act(held)
        self.assertTrue(self.page.evaluate("document.getElementById('tick').checked"))

    def test_a_click_that_works_is_left_alone(self):
        self.page.evaluate("document.getElementById('cover').remove()")
        self.backend._act(self.page.locator('#link'))
        self.assertEqual(self.page.evaluate('window.clicked'), 1)
        self.assertEqual(self.log(), '')


if __name__ == '__main__':
    unittest.main()
