"""Real window keys in Email, keyboard only (nightly sweep, November 6, 2026).

- Escape in the To, CC, BCC or Subject box sends what was typed with it, so the leave question
  keeps it and Keep writing shows it again. It was lost.
- Delete in an open message reaches Companion, which asks to move it to Trash, as "Delete" does.
  It did nothing.

Like test_header_keys_window, this uses the real window with Tk's Windows Alt bindings."""
import time
import unittest

from test_alt_keys_window import AltKeyWindowTests, _window_tests


@_window_tests
class EmailKeyWindowTests(AltKeyWindowTests):
    # Only the tests below; the Alt menu tests run in their own class.
    test_alt_alone_opens_the_email_menu_and_never_the_system_menu = None
    test_right_alt_is_routed_to_companion_too = None
    test_alt_with_a_key_does_not_open_the_menu = None
    test_alt_where_there_is_no_menu_says_why_and_stays_in_companion = None
    test_alt_letter_shortcuts_reach_companion = None

    def press(self, keysym, state=0, widget=None):
        def send():
            target = widget() if widget else self.window.typed
            target.focus_force()
            target.event_generate('<KeyPress>', keysym=keysym, state=state)
            target.event_generate('<KeyRelease>', keysym=keysym, state=state)
        self.call(send); time.sleep(.2)

    def header_box(self, field, text):
        self.screen(mode='email_draft', source='email:1', text='', email_field=field)
        self.window.focus_email_field(field, '')
        end = time.monotonic() + 3
        while self.window.email_field != field and time.monotonic() < end: time.sleep(.02)
        self.assertEqual(self.window.email_field, field)
        self.call(lambda: self.window.typed.insert(0, text))
        self.window.commands.queue.clear()

    def test_escape_in_a_header_box_keeps_what_was_typed(self):
        for field, text in (('subject', 'Lunch on Friday'), ('recipient', 'sam@example.com'), ('cc', 'ann@example.com')):
            with self.subTest(field=field):
                self.header_box(field, text)
                self.press('Escape')
                queued = list(self.window.commands.queue)
                self.assertIn(('email_field_tab', {'field': field, 'value': text, 'backward': False, 'key': 'Escape'}), queued)
                self.assertNotIn(('keyboard', 'Escape'), queued)

    def test_escape_in_an_empty_header_box_is_a_plain_escape(self):
        self.header_box('subject', '')
        self.press('Escape')
        self.assertIn(('keyboard', 'Escape'), list(self.window.commands.queue))

    def test_keys_in_the_send_review_do_not_change_the_message(self):
        # The review asks "Press Y or N". Another letter, Backspace or Control+V was typed into the
        # message, and Y then said there was no current send review.
        self.screen(mode='email_draft', source='email:1', text='See you at noon.', caret=16, confirmation='yes')
        self.call(lambda: self.window.editor.focus_force())
        for keysym, state in (('r', 0), ('BackSpace', 0), ('Delete', 0)):
            with self.subTest(key=keysym):
                self.press(keysym, state, lambda: self.window.editor)
                self.assertEqual(self.call(lambda: self.window.editor.get('1.0', 'end-1c')), 'See you at noon.')
        self.call(lambda: self.window.root.clipboard_clear() or self.window.root.clipboard_append('pasted'))
        self.call(lambda: self.window.editor.event_generate('<<Paste>>'))
        self.assertEqual(self.call(lambda: self.window.editor.get('1.0', 'end-1c')), 'See you at noon.')
        self.assertFalse([c for c in self.window.commands.queue if c[0] == 'text_edit'])
        self.window.commands.queue.clear()
        self.press('y', 0, lambda: self.window.editor)
        self.assertIn(('keyboard', 'y'), list(self.window.commands.queue))

    def test_delete_in_an_open_message_reaches_companion(self):
        self.screen(mode='mailbox', source='mail:1:1', text='Hello from Sam.', readonly=True, email_html=False)
        self.window.commands.queue.clear()
        self.press('Delete', 0, lambda: self.window.editor)
        self.assertIn(('keyboard', 'Delete'), list(self.window.commands.queue))
        self.assertEqual(self.call(lambda: self.window.editor.get('1.0', 'end-1c')), 'Hello from Sam.')


if __name__ == '__main__':
    unittest.main()
