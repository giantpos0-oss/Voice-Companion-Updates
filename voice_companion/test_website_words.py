"""'Go to website ...' keeps the whole address (November 2026: it heard "websiteexample.com")."""
import unittest
from unittest import mock

import companion


class WebsiteWordsTests(unittest.TestCase):
    def test_the_command_words_never_join_the_address(self):
        for said in ('go to website example dot com', 'Go to website example dot com.', 'open website example dot com',
                     'Open website, example dot com.', 'go to the website example dot com', 'open web site example dot com'):
            with self.subTest(said=said):
                self.assertEqual(companion.website_words(said).rstrip('.').lstrip(', '), 'example dot com')

    def test_the_routing_snapshot_never_joins_website_to_the_address(self):
        import json
        from pathlib import Path
        snapshot = json.loads((Path(__file__).resolve().parent.parent / 'tools' / 'routing-snapshot.json').read_text(encoding='utf-8'))
        for key, record in snapshot.items():
            with self.subTest(key=key):
                self.assertFalse(any('websiteexample' in said for said in record['said']), record['said'])


if __name__ == '__main__':
    unittest.main()
