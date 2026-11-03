import threading, time, unittest
from real_window_tests import real_window
from app_window import CompanionWindow

@real_window
class SearchBoxFocusTests(unittest.TestCase):
    def setUp(self):
        self.window = CompanionWindow('search focus test'); self.window.start()
    def tearDown(self):
        if self.window.thread.is_alive(): self.call(lambda: self.window.root.destroy())
        self.window.thread.join(5)
    def call(self, function):
        done = threading.Event(); out = []
        def run():
            try: out.append(function())
            finally: done.set()
        self.window.ui_actions.put(('ui_call', run)); done.wait(5)
        return out[0] if out else None
    def wait(self, condition):
        end = time.monotonic() + 5
        while not condition() and time.monotonic() < end: time.sleep(.02)
        return condition()
    def test_the_youtube_search_box_takes_the_keyboard_when_it_opens(self):
        self.window.set_context(dict(mode='youtube', menu_letters=False, focus=True))
        self.assertTrue(self.wait(lambda: self.window.context.get('mode') == 'youtube'))
        self.call(lambda: self.window.root.focus_force())
        self.window.set_context(dict(mode='youtube', task_input=True, naming_label='YouTube search', entry_request=(1, '')))
        self.assertTrue(self.wait(lambda: self.call(lambda: self.window.root.focus_get()) is self.window.typed))

if __name__ == '__main__':
    unittest.main()
