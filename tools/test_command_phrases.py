"""The fixed command phrase list matches the command handler (tools/command_phrases.py)."""
import unittest

import command_phrases


class CommandPhrasesTests(unittest.TestCase):
    def test_the_list_is_current(self):
        self.assertTrue(command_phrases.TARGET.is_file(), 'Run python3 tools/command_phrases.py --update')
        self.assertEqual(command_phrases.TARGET.read_text(encoding='utf-8'), command_phrases.current(),
                         'The command phrase list is out of date. Run python3 tools/command_phrases.py --update')


if __name__ == '__main__':
    unittest.main()
