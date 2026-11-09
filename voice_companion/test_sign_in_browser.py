"""sign_in_browser: Thunderbird's sign-in page in the person's own browser (Will, November 9, 2026)."""
import unittest
from unittest.mock import patch

import sign_in_browser


class SignInBrowserTests(unittest.TestCase):
    def test_the_default_browser_is_named_as_people_know_it(self):
        for prog_id, name in (('ChromeHTML', 'Google Chrome'), ('FirefoxURL-308046B0AF4A39CB', 'Firefox'),
                              ('MSEdgeHTM', 'Microsoft Edge'), ('BraveHTML', 'Brave'), ('OperaStable', 'Opera'),
                              ('SomethingElse', 'your web browser'), ('', 'your web browser')):
            with self.subTest(prog_id=prog_id):
                self.assertEqual(sign_in_browser.browser_name(prog_id), name)

    def test_only_https_pages_are_opened(self):
        started = []
        for url in ('http://example.com', 'file:///C:/Windows', 'javascript:alert(1)', '', None):
            with self.subTest(url=url), self.assertRaises(OSError):
                sign_in_browser.open_page(url, starter=started.append)
        self.assertEqual(started, [])
        with patch.object(sign_in_browser, '_read_prog_id', lambda: 'ChromeHTML'):
            self.assertEqual(sign_in_browser.open_page('https://accounts.google.com/x', starter=started.append), 'Google Chrome')
        self.assertEqual(started, ['https://accounts.google.com/x'])

    def test_no_way_to_open_a_browser_is_an_os_error(self):
        with patch.object(sign_in_browser.os, 'startfile', None, create=True):
            with self.assertRaises(OSError):
                sign_in_browser.open_page('https://accounts.google.com/x')


if __name__ == '__main__':
    unittest.main()
