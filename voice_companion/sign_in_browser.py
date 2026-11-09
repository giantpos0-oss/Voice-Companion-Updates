"""Open a Thunderbird sign-in page in the person's own web browser (Will, November 9, 2026).

Google refuses to sign in inside a browser that another program controls, and
Voice Companion's guided Chrome is one (it is started through Playwright). On
0.2.203 that stopped Gmail right after the email address. Thunderbird's own way
is the Windows default browser, the person's normal Chrome, Firefox or Edge,
and that worked. So the page Thunderbird hands over goes there. Thunderbird
still waits for the answer on this computer, as it always does.

Only https addresses are opened. Nothing is stored or logged.
"""
import os

USER_CHOICE = r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice'
# The start of Windows' ProgId for each browser, and the name people know it by.
NAMES = (('chromehtml', 'Google Chrome'), ('firefox', 'Firefox'), ('msedgehtm', 'Microsoft Edge'),
         ('bravehtml', 'Brave'), ('opera', 'Opera'), ('vivaldi', 'Vivaldi'))
FALLBACK = 'your web browser'


def _read_prog_id():
    try:
        import winreg
    except ImportError:
        return ''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, USER_CHOICE) as key:
            value = winreg.QueryValueEx(key, 'ProgId')[0]
    except OSError:
        return ''
    return value if isinstance(value, str) else ''


def browser_name(prog_id=None):
    """The default browser's everyday name, or "your web browser" when it is not known."""
    prog_id = (_read_prog_id() if prog_id is None else prog_id).casefold()
    for start, name in NAMES:
        if prog_id.startswith(start):
            return name
    return FALLBACK


def open_page(url, starter=None):
    """Open url in the default browser. Returns the browser's name. Raises OSError when it cannot."""
    url = str(url or '')
    if not url.lower().startswith('https://'):
        raise OSError('only https sign-in pages are opened')
    starter = starter or getattr(os, 'startfile', None)
    if starter is None:
        raise OSError('there is no default browser to open here')
    starter(url)
    return browser_name()
