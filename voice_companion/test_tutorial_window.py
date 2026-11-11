"""The real window sends every key to an open tutorial, by the names the tutorial checks.

Runs on any computer with a display and Tk. Not yet in the Windows release list: it must
pass once on a claude/try-... branch first (CLAUDE.md, "New Windows-only tests")."""
import time
import unittest

from key_state import ALT_STATE
import test_alt_keys_window as base


@base._window_tests
class TutorialWindowKeyTests(base.AltKeyWindowTests):
    # The window set-up of the Alt key tests, without their tests.
    for _name in [n for n in dir(base.AltKeyWindowTests) if n.startswith('test_')]:
        locals()[_name] = None
    del _name

    def sent(self):
        return [item for item in list(self.window.commands.queue)]

    def test_keys_reach_the_tutorial_by_name(self):
        self.screen(mode='tutorial', tutorial_keys=True, menu_letters=True)
        self.keys(('KeyPress', 'Down', 0), ('KeyPress', 'Return', 0), ('KeyPress', 'n', 4), ('KeyPress', 'r', 0),
                  ('KeyPress', 'Tab', 0), ('KeyPress', 'Delete', 0), ('KeyPress', 'F2', 0), ('KeyPress', 'Escape', 0))
        self.assertEqual(self.sent(), [('keyboard', key) for key in
                                       ('Down', 'Enter', 'Ctrl+N', 'R', 'Tab', 'Delete', 'F2', 'Escape')])

    def test_alt_alone_and_alt_with_an_arrow_reach_the_tutorial(self):
        self.screen(mode='tutorial', tutorial_keys=True)
        self.keys(('KeyPress', 'Alt_L', 0), ('KeyRelease', 'Alt_L', ALT_STATE))
        self.keys(('KeyPress', 'Alt_L', 0), ('KeyPress', 'Left', ALT_STATE), ('KeyRelease', 'Left', ALT_STATE),
                  ('KeyRelease', 'Alt_L', ALT_STATE))
        self.assertEqual(self.sent(), [('keyboard', 'Alt'), ('keyboard', 'Alt+Left')])
        self.assertEqual(self.given_to_windows(), [])

    def test_alt_t_opens_the_command_box_and_typed_words_are_sent_as_words(self):
        self.screen(mode='tutorial', tutorial_keys=True)
        self.keys(('KeyPress', 't', ALT_STATE))
        self.assertEqual(self.sent(), [('keyboard', 'Alt+T')])
        self.window.commands.queue.clear()
        self.assertTrue(self.window.command_entry_active)
        self.keys(*[('KeyPress', c, 0) for c in 'next'])
        self.assertEqual(self.sent(), [])          # letters type into the box
        self.keys(('KeyPress', 'Return', 0))
        time.sleep(.2)
        self.assertEqual(self.sent(), ['next'])


if __name__ == '__main__':
    unittest.main()
