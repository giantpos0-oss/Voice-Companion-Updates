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
  that are mostly ones Companion has just said are its own echo, and do not
  stop it. A navigation command ("next", "previous") always stops it, as
  before, even if Companion just said that word.
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
ECHO_SHARE = 2 / 3       # this share of known words, or more, is Companion's own voice
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


class SpeechStop:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.recent = deque(maxlen=16)   # (time said, set of words)
        self.listening = False   # a real word of this utterance was heard
        self.paused = False      # this utterance paused Companion's speech
        self.paused_at = 0.0

    def said(self, text):
        """Companion is saying this now; its words may come back through the microphone."""
        spoken = set(words(text))
        if spoken:
            self.recent.append((self.clock(), spoken))

    def echo_words(self):
        now = self.clock()
        known = set()
        for when, spoken in self.recent:
            if now - when <= ECHO_SECONDS:
                known |= spoken
        return known

    def echo(self, text):
        """True when these words are mostly Companion's own, heard back."""
        heard = real_words(text)
        if not heard:
            return True
        known = self.echo_words()
        return sum(word in known for word in heard) >= ECHO_SHARE * len(heard)

    def heard(self, partial, speaking, command=False):
        """A partial result. True when Companion's speech must stop now."""
        if not real_words(partial):
            return False
        if not self.listening:
            if speaking and not command and self.echo(partial):
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
