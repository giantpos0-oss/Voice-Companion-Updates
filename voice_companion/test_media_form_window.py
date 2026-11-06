"""A radio or podcast form in the real window, at 400 percent text on a small screen
(nightly sweep, November 6, 2026).

With the keyboard only: the field takes typed letters and Space, Enter and Tab send the
value, the player keys still reach the screen, and Escape reaches it and empties the box.
"""
from real_window_tests import real_window
import threading
import time
import unittest

CONTROL, SHIFT = 4, 1


@real_window
class MediaFormWindowTests(unittest.TestCase):
    def setUp(self):
        from app_window import CompanionWindow
        self.window = CompanionWindow('media form test')
        self.window.start()
        self.assertTrue(self.window.ready.wait(10))
        self.call(lambda: self.window.root.geometry('800x560'))

    def tearDown(self):
        if self.window.thread.is_alive():
            self.call(lambda: self.window.root.destroy())
        self.window.thread.join(5)

    def call(self, function):
        done = threading.Event()
        result = []

        def run():
            try:
                self.window.root.update_idletasks()
                result.append(function())
            except Exception as exc:
                result.append(exc)
            finally:
                done.set()
        self.window.ui_actions.put(('ui_call', run))
        if not done.wait(5):
            self.fail('The window did not answer.')
        if isinstance(result[0], Exception):
            raise result[0]
        return result[0]

    def wait(self, condition):
        end = time.monotonic() + 5
        while not condition() and time.monotonic() < end:
            time.sleep(.015)
        return condition()

    def form(self, revision, value=''):
        from display_options import settings
        while not self.window.commands.empty():
            self.window.commands.get_nowait()
        field = {'label': 'Station name', 'value': value, 'choices': ()}
        self.window.set_context(dict(mode='media', source=None, text='', caret=0, ack=0, focus=True, menu_letters=False,
                                     media_navigation=True, media_revision=revision, media_form=field, media_input=True,
                                     display=settings({'display_text_size': '400 percent'}), display_title='Radio',
                                     display_items=['Station name'], display_index=0))
        if not self.wait(lambda: self.window.context.get('media_revision') == revision):
            self.fail('The window did not show the form.')
        time.sleep(.3)   # the layout settles after idle

    def press(self, keysym, state=0):
        def send():
            self.window.typed.focus_force()  # Synthetic keys go to the focused widget.
            self.window.typed.event_generate('<KeyPress>', keysym=keysym, state=state)
            self.window.typed.event_generate('<KeyRelease>', keysym=keysym, state=state)
        self.call(send)

    def queued(self):
        return list(self.window.commands.queue)

    def typed(self):
        return self.call(lambda: self.window.typed.get())

    def test_typed_name_with_a_space_is_sent_by_enter(self):
        self.form(1)
        if not self.call(lambda: self.window.typed.winfo_ismapped()):
            self.fail('The field has no room at 400 percent text.')
        for char in 'wgn am':
            self.press('space' if char == ' ' else char)
        if not self.wait(lambda: self.typed() == 'wgn am'):
            self.fail('Typed: ' + repr(self.typed()) + ' ' + str(self.window.debug_state()))
        self.assertEqual(self.queued(), [])   # no letter or Space reached the list
        self.press('Return')
        if not self.wait(lambda: ('media_field', {'value': 'wgn am', 'next': 'Enter'}) in self.queued()):
            self.fail('Enter did not send the name. ' + str(self.queued()))
        self.assertEqual(self.typed(), '')

    def test_tab_and_shift_tab_send_the_field_and_move(self):
        self.form(1, 'Jazz')
        if not self.wait(lambda: self.typed() == 'Jazz'):
            self.fail('The field does not show its value: ' + repr(self.typed()))
        self.press('Tab', SHIFT)
        if not self.wait(lambda: ('media_field', {'value': 'Jazz', 'next': 'ShiftTab'}) in self.queued()):
            self.fail('Shift+Tab did not send the field. ' + str(self.queued()))

    def test_player_keys_and_escape_reach_the_screen(self):
        self.form(1)
        self.press('w')
        for keysym, state, expected in (('s', CONTROL, 'Ctrl+S'), ('r', CONTROL, 'Ctrl+R'), ('Escape', 0, 'Escape')):
            with self.subTest(key=expected):
                self.press(keysym, state)
                if not self.wait(lambda: ('keyboard', expected) in self.queued()):
                    self.fail(expected + ' did not arrive. ' + str(self.window.debug_state()))
        self.assertEqual(self.typed(), 'w')
        # Escape cancels the form: the screen says so with a new revision, and the box empties.
        self.window.set_context(dict(self.window.context, media_revision=2, media_form=None, media_input=False))
        if not self.wait(lambda: self.typed() == ''):
            self.fail('The box kept: ' + repr(self.typed()))


if __name__ == '__main__':
    unittest.main()
