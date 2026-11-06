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


class _Window(unittest.TestCase):
    """The real window and its helpers; no tests of its own."""
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

    def menu(self, mode, title, items):
        from display_options import settings
        while not self.window.commands.empty():
            self.window.commands.get_nowait()
        self.window.set_context(dict(mode=mode, source=None, text='', caret=0, ack=0, focus=True, menu_letters=True,
                                     display=settings({'display_text_size': '400 percent'}), display_title=title,
                                     display_items=items, display_index=0))
        if not self.wait(lambda: self.window.context.get('display_title') == title):
            self.fail('The window did not show ' + title + '.')
        time.sleep(.3)

    def feedback(self):
        import queue
        said = []
        while True:
            try:
                said.append(self.window.key_feedback.get_nowait())
            except queue.Empty:
                return said



@real_window
class MediaFormWindowTests(_Window):
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


@real_window
class MenuSpaceWindowTests(_Window):
    """Space in the Media menu (or any list menu) was typed into the command box and said
    "space". Down Arrow and Enter then did nothing at all, until Backspace."""

    def test_space_is_not_typed_and_the_arrows_still_work(self):
        for mode, title, items in (('media_menu', 'Media menu', ['Radio', 'Podcasts', 'Media player', 'YouTube']),
                                   ('awake', 'Main menu', ['File manager', 'Office tools', 'Media'])):
            with self.subTest(screen=title):
                self.menu(mode, title, items)
                self.feedback()
                self.press('space')
                if not self.wait(lambda: self.window.key_feedback.qsize() > 0):
                    self.fail('Space said nothing. ' + str(self.window.debug_state()))
                self.assertEqual(self.feedback(), ['Space does nothing in this list. Press Enter to choose.'])
                self.assertEqual(self.typed(), '')
                self.press('Down')
                if not self.wait(lambda: ('keyboard', 'Down') in self.queued()):
                    self.fail('Down Arrow did not arrive after Space. ' + str(self.window.debug_state()))



@real_window
class MenuCommandBoxWindowTests(_Window):
    """After Alt+T in the Media menu, the main menu or the radio results, each letter of a
    typed command jumped to a menu item ("p" went to Podcasts) instead of being typed."""

    def test_alt_t_types_letters_and_spaces(self):
        from key_state import ALT_STATE
        for mode, title, items in (('media_menu', 'Media menu', ['Radio', 'Podcasts', 'Media player', 'YouTube']),
                                   ('awake', 'Main menu', ['File manager', 'Office tools', 'Media']),
                                   ('media', 'Radio', ['WGN Radio 720', 'WBEZ Chicago'])):
            with self.subTest(screen=title):
                self.menu(mode, title, items)
                if mode == 'media':
                    self.window.set_context(dict(self.window.context, media_navigation=True))
                self.press('t', ALT_STATE)   # Alt+T opens the command box
                for char in 'play wgn':
                    self.press('space' if char == ' ' else char)
                if not self.wait(lambda: self.typed() == 'play wgn'):
                    self.fail('Typed: ' + repr(self.typed()) + ' ' + str(self.window.debug_state()))
                self.assertEqual([c for c in self.queued() if isinstance(c, tuple) and c[0] == 'keyboard'], [])
                self.press('Return')
                if not self.wait(lambda: 'play wgn' in self.queued()):
                    self.fail('Enter did not run the command. ' + str(self.queued()))

    def test_escape_clears_a_typed_command_and_the_letters_jump_again(self):
        from key_state import ALT_STATE
        self.menu('media_menu', 'Media menu', ['Radio', 'Podcasts', 'Media player', 'YouTube'])
        self.press('t', ALT_STATE)
        self.press('x')
        if not self.wait(lambda: self.typed() == 'x'):
            self.fail('Typed: ' + repr(self.typed()))
        self.press('Escape')
        if not self.wait(lambda: self.typed() == ''):
            self.fail('Escape kept: ' + repr(self.typed()))
        self.assertNotIn(('keyboard', 'Escape'), self.queued())   # it closed the box; it did not leave the menu
        self.press('p')
        if not self.wait(lambda: ('keyboard', 'Letter:p') in self.queued()):
            self.fail('P did not jump to Podcasts after Escape. ' + str(self.window.debug_state()))
