"""Dictation comes back faster (Will, November 12, 2026): only the part of the
recording with speech goes to Parakeet, and silence alone is not transcribed."""
import unittest

import numpy as np

from parakeet_recognition import speech_span, PAD_SECONDS

RATE = 16000


def sound(*parts):
    """parts: (seconds, level). Level 0 is a quiet room; speech is a loud tone with noise."""
    rng = np.random.default_rng(1)
    pieces = []
    for seconds, level in parts:
        count = int(seconds * RATE)
        noise = rng.normal(0, 40, count)
        tone = level * np.sin(np.arange(count) * 2 * np.pi * 220 / RATE) if level else 0
        pieces.append(np.clip(noise + tone, -32768, 32767))
    return np.concatenate(pieces).astype('<i2').tobytes()


def seconds(pcm):
    return len(pcm) / 2 / RATE


class SpeechSpanTests(unittest.TestCase):
    def test_silence_before_and_after_the_words_is_left_out(self):
        recording = sound((4.0, 0), (1.5, 6000), (1.0, 0))
        span = speech_span(recording)
        self.assertAlmostEqual(seconds(span), 1.5 + 2 * PAD_SECONDS, delta=0.05)
        self.assertLess(seconds(span), seconds(recording) / 2, 'Parakeet should get far less sound to work through.')

    def test_no_word_is_clipped(self):
        recording = sound((1.0, 0), (0.4, 3000), (0.6, 0), (0.3, 1500), (0.8, 0))
        span = speech_span(recording)
        start = recording.find(span)
        # Both words, with the room before the first and after the last.
        self.assertLessEqual(start / 2 / RATE, 1.0 - PAD_SECONDS + 0.03)
        self.assertGreaterEqual((start + len(span)) / 2 / RATE, 1.0 + 0.4 + 0.6 + 0.3 + PAD_SECONDS - 0.03)

    def test_a_quiet_room_has_no_speech(self):
        self.assertEqual(speech_span(sound((5.0, 0))), b'')
        self.assertEqual(speech_span(b''), b'')
        self.assertEqual(speech_span(b'\x00'), b'')

    def test_speech_with_no_pause_is_kept_whole(self):
        recording = sound((2.0, 5000))
        self.assertEqual(seconds(speech_span(recording)), seconds(recording))

    def test_speech_running_to_the_end_keeps_the_end(self):
        recording = sound((2.0, 0), (1.0, 5000))
        span = speech_span(recording)
        self.assertTrue(recording.endswith(span))


if __name__ == '__main__':
    unittest.main()
