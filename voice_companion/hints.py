"""Hints and help messages (Will, November 10, 2026).

Options, Verbosity options, "Hints and help messages" (on by default). When it is
off, Voice Companion says what happened and skips optional "here is how you
could..." guidance, such as "Press F1 twice for help." or "Say next or previous,
then that one to play."

Hints are marked where the message is written, never guessed from the words:

    speak('Downloads.' + hint(' Say pause download, ... Press F1 twice for help.'))

hint() returns a Spoken string. It is equal to its plain words, so tests and
code that compare text are not affected, and adding plain text before or after
it keeps the mark. Only speak() looks at the mark (spoken()).

What is never marked as a hint, so it is always said:
- a question and how to answer it ("Say yes or no, or press Y or N.")
- what to do after an error ("Close it, then try again.")
- what just happened

Text that loses the mark (an f-string, ''.join, .strip()) becomes plain text,
and then the hint is simply said. A lost mark never hides words.
"""
import re

SETTING = 'speak_hints'
LABEL = 'Hints and help messages'


class Spoken(str):
    """Message text with optional hint parts, kept as (start, end, words when off) positions."""

    def __new__(cls, text='', spans=()):
        made = super().__new__(cls, text)
        made.spans = tuple((a, b, (rest or [''])[0]) for a, b, *rest in spans if 0 <= a < b <= len(made))
        return made

    def __add__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        shift = len(self)
        return Spoken(str.__add__(str(self), str(other)),
                      self.spans + tuple((a + shift, b + shift, c) for a, b, c in getattr(other, 'spans', ())))

    def __radd__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        shift = len(other)
        return Spoken(str.__add__(str(other), str(self)),
                      tuple(getattr(other, 'spans', ())) + tuple((a + shift, b + shift, c) for a, b, c in self.spans))

    def __reduce__(self):
        return (Spoken, (str(self), self.spans))


def hint(text, instead=''):
    """Mark text as an optional hint. Empty text stays empty.

    instead: the words said in its place when hints are off. A screen's
    "I did not understand" answer uses it, so it never shrinks to a bare name."""
    text = '' if text is None else str(text)
    return Spoken(text, ((0, len(text), str(instead or '')),) if text.strip() else ())


def with_hint(message, hint_text):
    """message, then the hint after one space."""
    message = message if isinstance(message, str) else str(message)
    if not str(hint_text or '').strip():
        return message
    return message.rstrip() + hint(' ' + str(hint_text).strip())


def has_hint(text):
    return bool(getattr(text, 'spans', ()))


def spoken(text, enabled=True):
    """The words to say: everything when hints are on; without the hint parts when off."""
    if text is None:
        return ''
    if enabled or not has_hint(text):
        return str(text)
    plain, kept, start = str(text), [], 0
    for a, b, instead in sorted(text.spans):
        if a >= start:
            kept.append(plain[start:a] + instead)
            start = b
    kept.append(plain[start:])
    words = ''.join(kept)
    words = re.sub(r'[ \t]{2,}', ' ', words)
    words = re.sub(r' +([.,;:?!])', r'\1', words)
    return words.strip()


_NAME = r'(?:hints|help hints|hints and help messages|help messages)'
_TOGGLE = (re.compile(r'(?:(?:set|turn|switch) )?(?:the )?' + _NAME + r'(?: to)? (on|off)'),
           re.compile(r'(?:turn|switch) (on|off) (?:the )?' + _NAME),
           re.compile(r'(enable|disable) (?:the )?' + _NAME))


def toggle_request(command):
    """True for "hints on", False for "hints off", None for anything else.
    Speech adds commas, periods and capitals ("Hints, off."); they are ignored."""
    words = ' '.join(re.sub(r'[^a-z ]+', ' ', str(command or '').casefold()).split())
    for pattern in _TOGGLE:
        found = pattern.fullmatch(words)
        if found:
            return found[1] in ('on', 'enable')
    return None


def enabled(preferences):
    """The saved setting; anything but an explicit off means on."""
    value = (preferences or {}).get(SETTING, True)
    if isinstance(value, str):
        return value.strip().casefold() not in ('off', 'false', 'no', '0')
    return bool(value)
