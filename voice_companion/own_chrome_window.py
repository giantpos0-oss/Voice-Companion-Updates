"""Your own Chrome's windows that Voice Companion opened, kept out of sight when you choose
Options, Web browser, "Your own Chrome window": "Hide it while Companion uses it".

Will, November 2, 2026: a setting, not the default. Hidden means off every screen, off the
taskbar and out of Alt+Tab, the same way guided Chrome runs in the background (chrome_window.py)
and Thunderbird is hidden (window_hiding.py). The window is moved off the screen, never
minimized: a minimized Chrome stops drawing, and videos in it stop.

Only Chrome windows that Voice Companion opened are touched. A Chrome window you opened yourself
is never hidden. "Show browser window" brings the hidden ones back, and a page that needs a
person (a Google sign-in, a check that you are a person, a payment, choosing a file) brings them
back by itself.

Everything that touches Windows goes through a desktop object, so tests use fakes.
"""
import os
import time

SHOW = 'Show it, as before'
HIDE = 'Hide it while Companion uses it'
CHOICES = (SHOW, HIDE)
ENABLED = False   # set by companion.py from the preference 'own_chrome_window'
CHROME_CLASS = 'Chrome_WidgetWin_1'

# A page that needs a person brings your hidden Chrome back by itself (web_assistant.window_need).
NEEDED = {'sign-in': 'Google sign-in needs a window, so your Chrome came back.',
          'check': 'This site wants to check that you are a person, so your Chrome came back.',
          'payment': 'This page asks for a card or payment, so your Chrome came back in case a helper needs to look.',
          'file': 'This page has a box for choosing a file, so your Chrome came back.'}
HIDDEN_NOW = 'Your Chrome is hidden again. Companion still reads every page to you, and sound still plays.'
SHOWN_NOW = ('Your Chrome is in front. Press Alt+Tab to come back to Voice Companion. '
             'To hide it again, say hide browser window.')
NOTHING_TO_SHOW = 'Your Chrome is not hidden. Press Alt+Tab to find it.'
NOTHING_TO_HIDE = ('Only a Chrome window that Voice Companion opened can be hidden. '
                   'This Chrome was already open, so it stays as it is.')
OPTION_HIDE = ('Your own Chrome window: hide it while Companion uses it. A Chrome window that Companion opens '
               'stays off the screen, the taskbar and Alt+Tab. A page that needs you, such as a sign-in, shows it.')
OPTION_SHOW = 'Your own Chrome window: show it, as before.'


def win32_desktop():
    if os.name != 'nt':
        return None
    try:
        from window_hiding import Win32Desktop
        return Win32Desktop('chrome.exe')
    except Exception:
        return None


class OwnChromeWindows:
    WAIT_SECONDS = 2.0   # for Chrome's new window to show once the extension linked

    def __init__(self, desktop=win32_desktop, sleep=time.sleep):
        self.desktop_factory, self.sleep = desktop, sleep
        self.mine = set()       # windows Voice Companion opened
        self.hidden = {}        # handle: (style to put back, (left, top) to put back)

    def desktop(self):
        try:
            return self.desktop_factory()
        except Exception:
            return None

    def current(self):
        """Handles of Chrome's main windows open now."""
        desktop = self.desktop()
        if desktop is None:
            return set()
        try:
            return {w.handle for w in desktop.windows() if w.kind == CHROME_CLASS and not w.owned and not w.tool}
        except Exception:
            return set()

    def opened(self, before):
        """Chrome was just started by Companion: the windows that were not there before are
        Companion's. They are hidden at once when the setting is on. Returns the new handles."""
        if self.desktop() is None:
            return set()
        new, waited = set(), 0.0
        while True:
            new = self.current() - set(before)
            if new or waited >= self.WAIT_SECONDS:
                break
            self.sleep(0.2)
            waited += 0.2
        self.mine |= new
        if ENABLED:
            self.hide()
        return new

    def forget_closed(self, desktop):
        for handle in list(self.mine):
            try:
                alive = desktop.exists(handle)
            except Exception:
                alive = False
            if not alive:
                self.mine.discard(handle)
                self.hidden.pop(handle, None)

    def hide(self):
        """Hide Companion's Chrome windows. Returns how many are hidden now."""
        desktop = self.desktop()
        if desktop is None:
            return 0
        self.forget_closed(desktop)
        for handle in self.mine - set(self.hidden):
            try:
                place = desktop.position(handle)
                style = desktop.park(handle)
            except Exception:
                continue
            self.hidden[handle] = (style, place)
        return len(self.hidden)

    def show(self, forward=True):
        """Put the hidden windows back where they were, on the taskbar and in Alt+Tab.
        The first one comes to the front when forward is True. Returns how many came back."""
        desktop = self.desktop()
        hidden, self.hidden = self.hidden, {}
        if desktop is None:
            return 0
        shown = 0
        for handle, (style, place) in hidden.items():
            try:
                if not desktop.exists(handle):
                    continue
                desktop.untuck(handle, style)
                desktop.place(handle, place or (40, 40))   # back on the screen
                if forward and not shown:
                    desktop.bring_forward(handle)
                shown += 1
            except Exception:
                continue
        return shown

    def is_hidden(self):
        return bool(self.hidden)

    def closed(self, handle):
        """Companion closed this window (YouTube closing): forget it."""
        self.mine.discard(handle)
        self.hidden.pop(handle, None)


WINDOWS = OwnChromeWindows()


def set_enabled(choice):
    """The preference changed (or was read at start). Hides or shows Companion's Chrome windows now."""
    global ENABLED
    ENABLED = choice == HIDE
    try:
        if ENABLED:
            WINDOWS.hide()
        else:
            WINDOWS.show(forward=False)
    except Exception:
        pass


def command(show):
    """ "Show browser window" or "hide browser window" while your own Chrome is in use. Words to say."""
    if not ENABLED:
        return None   # as before: your own browser keeps its own window (web_assistant.WINDOW_OWN_BROWSER)
    if show:
        return SHOWN_NOW if WINDOWS.show() else NOTHING_TO_SHOW
    return HIDDEN_NOW if WINDOWS.hide() else NOTHING_TO_HIDE
