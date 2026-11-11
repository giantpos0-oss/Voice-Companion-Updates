"""Tab moves only between the controls that matter on each screen (Will, November 10, 2026).

Before, Tab and Shift+Tab from the command box, or past the end of a help topic or an email,
stopped on the helper buttons under it: "Options (Alt+O)", "Enter typed command" and
"AI voice setup (trainer)". Enter there opened Options or a dialog by surprise. Those buttons
are for a helper with a mouse. Each has a key and a spoken command, so they stay on the
screen but out of the Tab order. The buttons a screen really needs stay in it: Status and
Cancel update while an update downloads, and OK and Cancel in Options.

The window tests run on Windows in their own process (real_window_tests.py), and on any
other computer that has a display (tools/wintests.sh runs them under a virtual screen).
"""
import inspect
import os
import sys
import threading
import time
import unittest


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


def _window_tests(cls):
    if sys.platform == 'win32':
        from real_window_tests import real_window
        return real_window(cls)
    return unittest.skipUnless(_display(), 'needs a display for a real Tk window')(cls)


BASE = dict(source=None, text='', caret=0, ack=0, focus=True)
# Each screen, what has the keyboard when it opens, and every control Tab or Shift+Tab may reach.
SCREENS = (
    ('Main menu', dict(mode='awake', menu_letters=True), 'command box', {'command box'}),
    ('Favorite apps', dict(mode='favorites_menu', menu_letters=True), 'command box', {'command box'}),
    ('Address manager', dict(mode='contacts', menu_letters=True), 'command box', {'command box'}),
    ('Email list', dict(mode='mailbox'), 'command box', {'command box'}),
    ('Notepad', dict(mode='note'), 'command box', {'command box'}),
    ('YouTube', dict(mode='youtube', menu_letters=False), 'command box', {'command box'}),
    ('Media', dict(mode='media', media_navigation=True), 'command box', {'command box'}),
    ('Email draft', dict(mode='email_draft', email_field='recipient'), 'command box', {'command box'}),
    ('Update question', dict(mode='update_offer', confirmation=0), 'command box', {'command box'}),
    ('Behind Options', dict(mode='settings'), 'command box', {'command box'}),
    ('File manager', dict(mode='files', file_items=['Alpha, folder', 'Beta, file'], file_index=0), 'file list', {'file list'}),
    ('Web page', dict(mode='web', source='web', text='Page text', web_browse=True), 'text', {'text'}),
    ('Document', dict(mode='document', source='document', text='Hello there.'), 'text', {'text', 'command box'}),
    ('Email message', dict(mode='mailbox', source='email', text='Hi there.', readonly=True, rich_spans=[]), 'text', {'text', 'command box'}),
    ('Help topic', dict(mode='help', source='help', text='Help topic text.', readonly=True), 'text', {'text', 'command box'}),
    ('Document reader', dict(mode='file_reader', source='file', text='Book text.', readonly=True), 'text', {'text', 'command box'}),
    ('Update download', dict(mode='update_download'), 'command box', {'button Status', 'button Cancel update'}),
)


@_window_tests
class TabOrderWindowTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter   # noqa: F401
        except ImportError:
            self.skipTest('Tk is not installed')
        from app_window import CompanionWindow
        self.window = CompanionWindow('tab order test'); self.window.start()
        self.assertTrue(self.window.ready.wait(10))
        # Room for the helper buttons, at the usual text size, so they are on the screen.
        self.call(lambda: self.window.root.geometry('1500x950'))

    def tearDown(self):
        if self.window.thread.is_alive():
            self.call(lambda: self.window.root.destroy(), check=False)
        self.window.thread.join(5)

    def call(self, function, check=True):
        done = threading.Event(); result = []; errors = []
        def run():
            try: result.append(function())
            except Exception as exc: errors.append(exc)
            finally: done.set()
        self.window.ui_actions.put(('ui_call', run))
        ok = done.wait(5)
        if check and not ok: self.fail('The window did not run the request. ' + repr(self.window.debug_state()))
        if errors: raise errors[0]
        return result[0] if result else None

    def name(self, widget):
        window = self.window
        if widget is None: return 'nothing'
        if widget is window.typed: return 'command box'
        if widget is window.editor: return 'text'
        if widget is window.file_list: return 'file list'
        if widget.winfo_class() == 'Button': return 'button ' + widget.cget('text')
        return widget.winfo_class()

    def focused(self):
        return self.call(lambda: self.name(self.window.root.focus_get()))

    def open(self, context, start):
        context = dict(BASE, **context)
        self.window.set_context(context)
        end = time.monotonic() + 5
        while self.window.context is not context and time.monotonic() < end: time.sleep(.02)
        time.sleep(.3)
        widget = {'command box': self.window.typed, 'text': self.window.editor, 'file list': self.window.file_list}[start]
        self.call(lambda: (widget.focus_force(), self.window.root.update()))

    def stops(self, sequence, presses=4):
        found = []
        for _ in range(presses):
            def press():
                (self.window.root.focus_get() or self.window.typed).event_generate(sequence)
                self.window.root.update()
            self.call(press); time.sleep(.05)
            found.append(self.focused())
        return found

    def test_tab_stops_only_on_the_controls_each_screen_needs(self):
        for title, context, start, allowed in SCREENS:
            with self.subTest(screen=title):
                for sequence in ('<Tab>', '<Shift-Tab>'):
                    self.open(context, start)
                    found = self.stops(sequence)
                    self.assertTrue(set(found) <= allowed, (title, sequence, found))
        # The helper buttons are still on the screen for a mouse.
        self.assertTrue(self.call(lambda: all(b.winfo_ismapped() for b in self.window.row_buttons)))

    def test_no_helper_button_is_in_the_tab_order(self):
        def takes_focus():
            return {b.cget('text'): str(b.cget('takefocus')) for b in self.window.row_buttons + self.window.update_buttons}
        self.assertEqual(self.call(takes_focus), {'Options (Alt+O)': '0', 'Enter typed command': '0',
                                                  'AI voice setup (trainer)': '0', 'Status': '0', 'Cancel update': '0'})

    def test_the_update_buttons_still_take_turns_while_an_update_downloads(self):
        self.open(dict(mode='update_download'), 'command box')
        self.assertEqual(self.stops('<Tab>', 3), ['button Status', 'button Cancel update', 'button Status'])
        self.assertEqual(self.stops('<Shift-Tab>', 2), ['button Cancel update', 'button Status'])


class OptionsDialogTabOrderTests(unittest.TestCase):
    """The Options dialog (native_settings.py) is a Windows dialog; its Tab stops are the
    controls made with WS_TABSTOP (0x10000). test_favorite_apps_windows drives the real dialog."""

    def source(self):
        import native_settings
        return inspect.getsource(native_settings.NativeSettings._run)

    def test_email_header_helper_buttons_are_out_of_the_tab_order(self):
        # Space and Alt+Up or Alt+Down do the same in the list, and so do "toggle header",
        # "move header up" and "move header down".
        source = self.source()
        wanted = "button=control('BUTTON',label,0,225+j*155,y+110,145,27,300+j)"
        self.assertTrue(wanted in source, wanted)

    def test_the_favorite_apps_helper_buttons_are_out_of_the_tab_order(self):
        source = self.source()
        wanted = "button=control('BUTTON',label,0,225+j*155,y+APPS_HEIGHT+28,145,27,310+j)"
        self.assertTrue(wanted in source, wanted)

    def test_ok_cancel_and_close_stay_in_the_tab_order(self):
        source = self.source()
        for wanted in ("ok=control('BUTTON','OK',0x10000|1,", "cancel=control('BUTTON','Cancel',0x10000,",
                       "close_button=control('BUTTON','Close settings',0x10000,"):
            self.assertTrue(wanted in source, wanted)


if __name__ == '__main__':
    unittest.main()
