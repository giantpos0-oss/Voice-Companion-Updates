"""Letters in the email folder list reach the list, in the real window.

On the email screen the window checked its own email keys first, so a letter
pressed in the folder list (Control+Y, "go to folder") went into the command box
and first-letter navigation did nothing (Will, November 15, 2026). With the
folder list open, a letter is sent to it. Without a list, letters still type.
"""
from real_window_tests import real_window
import threading
import time
import unittest


@real_window
class MailboxLetterWindowTests(unittest.TestCase):
    def setUp(self):
        from app_window import CompanionWindow
        self.window = CompanionWindow('mailbox letter test')
        self.window.start()

    def tearDown(self):
        if self.window.thread.is_alive():
            self.call(lambda: self.window.root.destroy())
        self.window.thread.join(5)

    def call(self, function):
        done = threading.Event()
        errors = []

        def run():
            try:
                self.window.root.update_idletasks()
                function()
            except Exception as exc:
                errors.append(exc)
            finally:
                done.set()
        self.window.ui_actions.put(('ui_call', run))
        self.assertTrue(done.wait(5))
        if errors:
            raise errors[0]

    def wait(self, condition):
        end = time.monotonic() + 5
        while not condition() and time.monotonic() < end:
            time.sleep(.015)
        return condition()

    def screen(self, **context):
        while not self.window.commands.empty():
            self.window.commands.get_nowait()
        self.window.set_context(dict(dict(mode='mailbox', source=None, text='', caret=0, ack=0, focus=True,
                                          menu_letters=False), **context))
        if not self.wait(lambda: self.window.context == dict(self.window.context, **context)):
            self.fail('The window did not show the email screen.')

    def press(self, keysym, state=0):
        def send():
            self.window.typed.focus_force()  # Synthetic keys go to the focused widget.
            self.window.typed.event_generate('<KeyPress>', keysym=keysym, state=state)
            self.window.typed.event_generate('<KeyRelease>', keysym=keysym, state=state)
        self.call(send)

    def requests(self):
        return [item[1] for item in list(self.window.commands.queue) if isinstance(item, tuple) and item[0] == 'keyboard']

    def typed(self):
        result = []
        self.call(lambda: result.append(self.window.typed.get()))
        return result[0]

    def test_a_letter_in_the_folder_list_moves_in_the_list(self):
        self.screen(menu_letters=True)
        self.press('w')
        self.assertTrue(self.wait(lambda: self.requests() == ['Letter:w']), self.requests())
        self.assertEqual(self.typed(), '', 'The letter must not go into the command box.')

    def test_without_a_list_the_email_keys_are_unchanged(self):
        self.screen(menu_letters=False)
        self.press('y', 4)   # Control+Y still opens the folder list
        self.assertTrue(self.wait(lambda: 'Ctrl+Y' in self.requests()), self.requests())
        self.assertNotIn('Letter:y', self.requests())


if __name__ == '__main__':
    unittest.main()
