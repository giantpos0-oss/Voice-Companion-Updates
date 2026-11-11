"""One place where the user's voice stops Companion's speech (Will, November 10, 2026).

Before, each screen and command stopped speech in its own way, so whether
Companion went quiet when you started to talk was hit and miss. Now the
recognizer loop in companion.py tells this module about every partial result
(the words heard so far) and about the end of every utterance:

1. The first real word of an utterance pauses Companion's speech at once, on
   every screen, for commands and for dictation alike.
2. When the utterance ends, companion.user_finished_speaking() decides:
   - "Stop talking" keeps the pause, so "Resume" goes on from that word.
   - "Resume" goes on.
   - Nothing at all, or Companion's own words heard back through the
     microphone, or talk in the room while Help reads: speech goes on from
     where it paused, as if nothing happened.
   - Anything else (a command, or words to write) ends the old speech, keeping
     an unfinished dictated sentence for its echo, and the words are acted on.

The noise guard:
- Only real words count. Noise often comes back from the recognizer as "the",
  "a", "uh", "hmm" or an unknown-word marker; those never stop speech.
- While Companion is talking, its own voice can reach the microphone. Words
  are its echo only when they follow, in order, a run of what Companion said
  in the last ECHO_SECONDS, with a few recognizer slips allowed (echo()).
  Sharing some words is not enough.
- A complete command for the screen is never echo, even when Companion's
  prompt just said it ("Say check email to open it"): companion.command_here()
  decides that, with the router's own checks and the commands Companion's
  speech suggested (suggestions()).
- In writing fields the rule is strict: only a long, nearly exact repeat of
  Companion's speech is echo. When in doubt, the user's words are kept.
- A pause the user did not finish (no end of utterance comes) goes on again
  after STALE_SECONDS, so Companion is never left silent by mistake.
"""
import re
import time
from collections import deque

# Words a recognizer often makes out of breathing, a cough or room noise.
NOISE_WORDS = frozenset(('uh', 'um', 'umm', 'uhm', 'hmm', 'hm', 'mm', 'mmm', 'mhm', 'ah', 'oh', 'er', 'erm', 'huh',
                         'the', 'a', 'an', 'unk'))
ECHO_SECONDS = 20.0      # Companion's words from this long ago can still be coming out of the speakers
# Recognizer slips allowed in an echo: one per this many words heard. In writing fields an echo
# must be at least WRITING_ECHO_WORDS long and nearly exact, so dictated words are never lost.
ECHO_SLIPS_PER = 4
WRITING_SLIPS_PER = 8
WRITING_ECHO_WORDS = 5
STALE_SECONDS = 20.0     # a pause with no end of utterance after this long is undone

_ONES = ('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen '
         'sixteen seventeen eighteen nineteen').split()
_TENS = 'twenty thirty forty fifty sixty seventy eighty ninety'.split()


def _number_words(digits):
    """'12' -> ['twelve']; '45' -> ['forty', 'five']: Companion says numbers, the recognizer writes words."""
    value = int(digits)
    if value < 20:
        return [_ONES[value]]
    if value < 100:
        return [_TENS[value // 10 - 2]] + ([_ONES[value % 10]] if value % 10 else [])
    return [_ONES[int(d)] for d in digits]


def words(text):
    found = []
    for word in re.findall(r"[^\W_]+(?:'[^\W_]+)?", str(text).casefold()):
        found.extend(_number_words(word) if word.isdigit() else [word.replace("'", '')])
    return found


def real_words(text):
    return [word for word in words(text) if word not in NOISE_WORDS]


def _closest_run(heard, spoken):
    """The fewest word changes that turn heard into some run of spoken, in order
    (an edit distance where the run may start and end anywhere in spoken)."""
    previous = [0] * (len(spoken) + 1)
    for i, word in enumerate(heard, 1):
        current = [i] + [0] * len(spoken)
        for j, said in enumerate(spoken, 1):
            current[j] = min(previous[j - 1] + (word != said), previous[j] + 1, current[j - 1] + 1)
        previous = current
    return min(previous)


# "Say check email to open it." "Say yes or no." "say Next or Previous, and okay to open."
_SAY = re.compile(r'\bsay,?\s+(?:the words?\s+)?(.+?)(?=\s+to\s|\s+when\s|\s+if\s|\s+for\s|[.;:!?()]|$)', re.I)
_SPLIT = re.compile(r'\s*,\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and\s+', re.I)


def suggestions(text):
    """The commands a spoken prompt tells the user to say, as heard words."""
    found = set()
    for clause in _SAY.findall(str(text)):
        for part in _SPLIT.split(clause.replace('"', ' ').replace('\u201c', ' ').replace('\u201d', ' ')):
            spoken = ' '.join(words(part))
            if spoken:
                found.add(spoken)
    return found


class SpeechStop:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.recent = deque(maxlen=16)   # (time said, words in order, suggested commands)
        self.listening = False   # a real word of this utterance was heard
        self.paused = False      # this utterance paused Companion's speech
        self.paused_at = 0.0

    def said(self, text):
        """Companion is saying this now; its words may come back through the microphone."""
        spoken = words(text)
        if spoken:
            self.recent.append((self.clock(), spoken, suggestions(text)))

    def _recent(self):
        now = self.clock()
        return [item for item in self.recent if now - item[0] <= ECHO_SECONDS]

    def spoken_words(self):
        """Companion's recent speech as one run of words, in the order it was said."""
        return [word for _, spoken, _ in self._recent() for word in spoken]

    def suggested(self, text):
        """True when Companion's recent speech told the user to say exactly these words."""
        heard = ' '.join(words(text))
        return bool(heard) and any(heard in offered for _, _, offered in self._recent())

    def echo(self, text, writing=False):
        """True when these words follow, in order, a run of what Companion just said."""
        heard = [word for word in words(text) if word != 'unk']
        if not real_words(text):
            return True   # only noise words: nothing of the user's to keep
        if writing and len(heard) < WRITING_ECHO_WORDS:
            return False
        spoken = self.spoken_words()
        if not spoken:
            return False
        slips = len(heard) // (WRITING_SLIPS_PER if writing else ECHO_SLIPS_PER)
        return _closest_run(heard, spoken) <= slips

    def heard(self, partial, speaking, command=False, writing=False):
        """A partial result. True when Companion's speech must stop now.
        command: True, or a function that says whether the words are a command here."""
        if not real_words(partial):
            return False
        if not self.listening:
            if speaking and self.echo(partial, writing) and not (command() if callable(command) else command):
                return False
            self.listening = True
        return bool(speaking)

    def pausing(self):
        """Companion's speech was paused for this utterance."""
        self.paused, self.paused_at = True, self.clock()

    def released(self):
        """Speech was stopped, paused or resumed by other means: this pause is no longer ours."""
        self.paused = False

    def stale(self):
        return self.paused and self.clock() - self.paused_at > STALE_SECONDS

    def finish(self):
        """The utterance ended (or was thrown away). True when it had paused Companion's speech."""
        paused = self.paused
        self.listening = self.paused = False
        return paused
