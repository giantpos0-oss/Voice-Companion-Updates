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

str(), .strip(), .lstrip() and .rstrip() keep the mark; use join() here instead
of ''.join(). Text that still loses the mark (an f-string with other words,
.format, .replace) becomes plain text, and then the hint is simply said. A lost
mark never hides words.

Verbosity (high, medium, low) shortens only marked hints too (brief()).
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
        return Spoken(str.__add__(str.__str__(self), str.__str__(other)),
                      self.spans + tuple((a + shift, b + shift, c) for a, b, c in getattr(other, 'spans', ())))

    def __radd__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        shift = len(other)
        return Spoken(str.__add__(str.__str__(other), str.__str__(self)),
                      tuple(getattr(other, 'spans', ())) + tuple((a + shift, b + shift, c) for a, b, c in self.spans))

    def __reduce__(self):
        return (Spoken, (str.__str__(self), self.spans))

    def _cut(self, start, end):
        """The text from start to end, with the marks inside it."""
        return Spoken(str.__getitem__(str.__str__(self), slice(start, end)),
                      tuple((max(a, start) - start, min(b, end) - start, c) for a, b, c in self.spans
                            if min(b, end) > max(a, start)))

    def strip(self, chars=None):
        plain = str.__str__(self)
        start = len(plain) - len(plain.lstrip(chars))
        return self._cut(start, max(start, len(plain.rstrip(chars))))

    def lstrip(self, chars=None):
        plain = str.__str__(self)
        return self._cut(len(plain) - len(plain.lstrip(chars)), len(plain))

    def rstrip(self, chars=None):
        return self._cut(0, len(str.__str__(self).rstrip(chars)))

    def __str__(self):
        # str(message) keeps the mark, so code that writes str(text) before speaking loses nothing.
        return self


def hint(text, instead=''):
    """Mark text as an optional hint. Empty text stays empty.

    instead: the words said in its place when hints are off. A screen's
    "I did not understand" answer uses it, so it never shrinks to a bare name."""
    text = '' if text is None else str.__str__(str(text))
    return Spoken(text, ((0, len(text), str(instead or '')),) if text.strip() else ())


def with_hint(message, hint_text):
    """message, then the hint after one space."""
    message = message if isinstance(message, str) else str(message)
    if not str(hint_text or '').strip():
        return message
    return message.rstrip() + hint(' ' + str(hint_text).strip())


def join(separator, parts):
    """separator.join(parts), keeping the hint marks of every part."""
    result = ''
    for index, part in enumerate(parts):
        result = result + (separator if index else '') + part
    return result


def brief(text, level):
    """Verbosity: 'high' keeps every hint, 'medium' keeps the first sentence of each
    hint, 'low' drops them (or says their instead words). Unmarked words are never cut,
    so a question, its answer words and a recovery step always stay. The shortened
    hints stay marked, so Hints and help messages off still removes them."""
    if level == 'high' or not has_hint(text):
        return text
    plain, result, start = str.__str__(text), '', 0
    for a, b, instead in sorted(text.spans):
        if a < start:
            continue
        result = result + plain[start:a]
        piece = plain[a:b]
        if level == 'low':
            result = result + instead
        else:
            lead = piece[:len(piece) - len(piece.lstrip())]
            first = re.split(r'(?<=[.!?])\s+', piece.strip(), maxsplit=1)[0]
            result = result + hint(lead + first, instead)
        start = b
    result = result + plain[start:]
    return result if isinstance(result, Spoken) else Spoken(result)


def has_hint(text):
    return isinstance(text, Spoken) and bool(text.spans)


def spoken(text, enabled=True):
    """The words to say: everything when hints are on; without the hint parts when off."""
    if text is None:
        return ''
    if not isinstance(text, Spoken):
        return text
    if enabled or not has_hint(text):
        return str.__str__(text)
    plain, kept, start = str.__str__(text), [], 0
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


# Where the saved preferences are. companion.py sets it, so a path that has no
# preferences of its own (the window's key feedback) can still follow the setting.
PREFERENCES_SOURCE = None


def for_speech(text):
    """spoken() with the saved setting."""
    source = PREFERENCES_SOURCE
    try:
        preferences = source() if callable(source) else {}
    except Exception:
        preferences = {}
    return spoken(text, enabled(preferences))


def enabled(preferences):
    """The saved setting; anything but an explicit off means on."""
    value = (preferences or {}).get(SETTING, True)
    if isinstance(value, str):
        return value.strip().casefold() not in ('off', 'false', 'no', '0')
    return bool(value)
