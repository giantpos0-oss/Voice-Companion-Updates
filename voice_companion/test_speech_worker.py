"""Will, November 1, 2026: Companion froze at startup. The main loop asked the Windows voice to stop
(Speak with purge) and the voice never answered, so no key or command was handled again.
The voice now lives on its own thread (speech_worker.py)."""
import threading
import time
import unittest

from speech_worker import SpeechWorker, VoiceToken


class FakeToken:
    def __init__(self, voice_id, name):
        self.Id, self.name = voice_id, name

    def GetDescription(self):
        return self.name


class FakeTokens:
    def __init__(self, tokens):
        self.tokens, self.Count = tokens, len(tokens)

    def Item(self, i):
        return self.tokens[i]


class FakeVoice:
    """Behaves as SAPI.SpVoice does for the calls the app makes. hang: Speak waits until released."""
    TOKENS = [FakeToken('id-david', 'Microsoft David'), FakeToken('id-zira', 'Microsoft Zira')]

    def __init__(self, hang=None):
        self.said, self.calls = [], []
        self.hang = hang
        self.Voice = self.TOKENS[0]
        self.Rate, self.Volume = 0, 100

    def GetVoices(self):
        return FakeTokens(self.TOKENS)

    def Speak(self, text, flags):
        self.calls.append(('Speak', text, flags))
        if self.hang is not None and text:
            self.hang.wait(30)
        self.said.append(text)
        return 1

    def Pause(self):
        self.calls.append(('Pause',))

    def Resume(self):
        self.calls.append(('Resume',))

    def WaitUntilDone(self, ms):
        return True


def wait_for(condition, seconds=3):
    end = time.monotonic() + seconds
    while not condition() and time.monotonic() < end:
        time.sleep(0.01)
    return condition()


class SpeechWorkerTests(unittest.TestCase):
    def worker(self, voices):
        made = iter(voices)
        made_list = []
        def factory():
            voice = next(made)
            made_list.append(voice)
            return voice
        worker = SpeechWorker(factory=factory, pump=lambda: None)
        worker.STUCK_SECONDS = 0.3
        self.addCleanup(setattr, worker, 'generation', -1)   # stops the threads
        return worker, made_list

    def test_speech_reaches_the_voice_with_its_settings(self):
        worker, made = self.worker([FakeVoice()])
        self.assertEqual(worker.GetVoices().Count, 2)
        self.assertEqual(worker.Voice.GetDescription(), 'Microsoft David')
        worker.Rate, worker.Volume = 3, 80
        worker.Voice = worker.GetVoices().Item(1)
        worker.Speak('Hello.', 1)
        self.assertTrue(wait_for(lambda: made[0].said == ['Hello.']))
        self.assertEqual((made[0].Rate, made[0].Volume, made[0].Voice.Id), (3, 80, 'id-zira'))
        self.assertEqual(worker.Voice.Id, 'id-zira')
        self.assertTrue(worker.WaitUntilDone(0))

    def test_a_voice_that_stops_answering_never_holds_up_the_app(self):
        release = threading.Event()
        self.addCleanup(release.set)
        stuck, fresh = FakeVoice(hang=release), FakeVoice()
        worker, made = self.worker([stuck, fresh])
        worker.Rate = 4
        worker.Voice = worker.GetVoices().Item(1)
        worker.Speak('Welcome to Voice Companion.', 1)
        self.assertTrue(wait_for(lambda: stuck.calls and stuck.calls[-1][1] == 'Welcome to Voice Companion.'))
        started = time.monotonic()
        worker.Speak('', 3)                    # the purge that froze the app on November 1
        self.assertTrue(worker.WaitUntilDone(0))
        self.assertLess(time.monotonic() - started, 0.5)
        time.sleep(0.35)                       # longer than STUCK_SECONDS
        worker.Speak('Main menu.', 1)          # this finds the voice stuck and makes a new one
        self.assertTrue(wait_for(lambda: 'Main menu.' in fresh.said))
        self.assertEqual((fresh.Rate, fresh.Voice.Id), (4, 'id-zira'))   # same rate and voice as before
        self.assertEqual(worker.restarts, 1)

    def test_stop_drops_speech_still_waiting_but_keeps_settings(self):
        release = threading.Event()
        self.addCleanup(release.set)
        voice = FakeVoice(hang=release)
        worker, made = self.worker([voice])
        worker.STUCK_SECONDS = 30
        worker.Speak('First.', 1)
        self.assertTrue(wait_for(lambda: voice.calls))
        worker.Speak('Second.', 1)
        worker.Volume = 50
        worker.Speak('', 3)
        release.set()
        self.assertTrue(wait_for(lambda: voice.said[-1:] == ['']))
        self.assertNotIn('Second.', voice.said)
        self.assertEqual(voice.Volume, 50)

    def test_a_voice_that_cannot_start_leaves_a_safe_default(self):
        def broken():
            raise OSError('no audio')
        worker = SpeechWorker(factory=broken, pump=lambda: None)
        self.assertEqual(worker.problem, 'OSError')
        self.assertEqual(worker.Voice.Id, '')
        self.assertEqual(worker.GetVoices().Count, 1)
        self.assertEqual(worker.Speak('Hello.', 1), 0)    # never raises
        self.assertTrue(worker.WaitUntilDone(0))

    def test_voice_tokens_compare_by_id(self):
        self.assertEqual(VoiceToken('a', 'One'), VoiceToken('a', 'Other name'))
        self.assertNotEqual(VoiceToken('a', 'One'), VoiceToken('b', 'One'))


class AppUsesTheWorkerTests(unittest.TestCase):
    def test_the_main_voice_is_the_worker_not_sapi_directly(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parent / 'companion.py').read_text(encoding='utf-8')
        self.assertIn('voice = SpeechWorker()', source)
        # SAPI on the main thread only when the helper could not make any voice, so speech never stops.
        start = source.index('voice = SpeechWorker()')
        self.assertIn("if voice.problem and not voice.voices:", source[start:start + 300])


if __name__ == '__main__':
    unittest.main()
