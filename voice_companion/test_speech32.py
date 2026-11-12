"""32-bit Windows voices through VoiceCompanion-Speech32.exe (speech32.py, speech32_host.py).

Will, November 2026: his NeoSpeech voices VW James, VW Kate and VW Paul are 32-bit only, so the
64-bit Voice Companion never listed them. The helper is run here as a real child process, with a
fake SAPI.SpVoice that behaves as the real one does for the calls the app makes."""
import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import speech32
import speech32_host
from speech32 import HybridVoice, Speech32Client, Token32, with_32bit_voices

HERE = Path(__file__).resolve().parent
TOKENS = 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\'


class FakeToken:
    def __init__(self, voice_id, name):
        self.Id, self.name = voice_id, name

    def GetDescription(self):
        return self.name


class FakeTokens:
    def __init__(self, tokens):
        self.tokens, self.Count = list(tokens), len(tokens)

    def Item(self, i):
        return self.tokens[i]


class FakeSpVoice:
    """SAPI.SpVoice for the calls Voice Companion makes: async Speak with numeric flags (1 async,
    2 purge, 8 XML), Pause and Resume, WaitUntilDone(ms) that is False while words are waiting
    or paused, and tokens with Id and GetDescription()."""
    TOKENS = [FakeToken(TOKENS + 'TTS_MS_EN-US_DAVID_11.0', 'Microsoft David Desktop - English (United States)'),
              FakeToken(TOKENS + 'VW Paul', 'VW Paul'), FakeToken(TOKENS + 'VW Kate', 'VW Kate')]
    SPEAK_SECONDS = 0.3

    def __init__(self, log=None, hang_word=None, tokens=None):
        self.log, self.hang_word = log, hang_word
        self.calls = []
        self.tokens = list(tokens or self.TOKENS)
        self._voice = self.tokens[0]
        self._rate, self._volume = 0, 100
        self.paused = False
        self.waiting = []
        self.until = 0

    def record(self, *call):
        self.calls.append(call)
        if self.log:
            with open(self.log, 'a', encoding='utf-8') as file:
                file.write(json.dumps(call) + '\n')

    def GetVoices(self):
        return FakeTokens(self.tokens)

    @property
    def Voice(self):
        return self._voice

    @Voice.setter
    def Voice(self, token):
        self._voice = token
        self.record('Voice', token.GetDescription())

    @property
    def Rate(self):
        return self._rate

    @Rate.setter
    def Rate(self, value):
        self._rate = value
        self.record('Rate', value)

    @property
    def Volume(self):
        return self._volume

    @Volume.setter
    def Volume(self, value):
        self._volume = value
        self.record('Volume', value)

    def Speak(self, text, flags):
        assert isinstance(flags, int)
        self.record('Speak', text, flags)
        if self.hang_word and self.hang_word in text:
            time.sleep(3600)
        if flags & 2:
            self.waiting = []
        if text:
            self.waiting.append(text)
            self.until = time.monotonic() + self.SPEAK_SECONDS
        return 1

    def Pause(self):
        self.record('Pause')
        self.paused = True

    def Resume(self):
        self.record('Resume')
        self.paused = False

    def WaitUntilDone(self, ms):
        end = time.monotonic() + ms / 1000
        while True:
            done = not self.waiting or (not self.paused and time.monotonic() >= self.until)
            if done or time.monotonic() >= end:
                break
            time.sleep(0.01)
        if done:
            self.waiting = []
        return done


WRAPPER = '''import os, sys
sys.path.insert(0, sys.argv[1])
import speech32_host
from test_speech32 import FakeSpVoice
def make():
    if os.environ.get('FAKE_BROKEN'):
        raise OSError('Class not registered')
    return FakeSpVoice(log=sys.argv[2], hang_word=os.environ.get('FAKE_HANG'))
code = speech32_host.serve(sys.stdin.buffer, sys.stdout.buffer, make_voice=make, pump=lambda: None,
                           finish=speech32_host.finish_for_sure)
sys.stdout.flush()
os._exit(code)
'''


def wait_for(condition, seconds=5):
    end = time.monotonic() + seconds
    while not condition() and time.monotonic() < end:
        time.sleep(0.02)
    return condition()


class HelperFixture(unittest.TestCase):
    """Starts the real helper program (with the fake SAPI voice) as a child process."""

    def setUp(self):
        folder = tempfile.mkdtemp(prefix='speech32-test-')
        self.folder = Path(folder)
        self.wrapper = self.folder / 'fake_speech32.py'
        self.wrapper.write_text(WRAPPER, encoding='utf-8')
        self.log = self.folder / 'calls.jsonl'
        self.clients = []
        speech32._announced.clear()
        self.addCleanup(speech32._announced.clear)
        self.environment = patch.dict(os.environ, {'PYTHONDONTWRITEBYTECODE': '1'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self._close_clients)

    def _close_clients(self):
        for client in self.clients:
            client.kill()
            if client.process is not None:
                try:
                    client.process.wait(5)
                except subprocess.TimeoutExpired:
                    pass

    def client(self, command=None):
        client = Speech32Client(command or [sys.executable, '-I', str(self.wrapper), str(HERE), str(self.log)])
        self.clients.append(client)
        return client

    def calls(self):
        if not self.log.exists():
            return []
        return [tuple(json.loads(line)) for line in self.log.read_text(encoding='utf-8').splitlines()]


class NativeVoice(FakeSpVoice):
    """The 64-bit voice: David, Zira and Eloquence, as on Will's computer."""
    TOKENS = [FakeToken(TOKENS + 'TTS_MS_EN-US_DAVID_11.0', 'Microsoft David Desktop - English (United States)'),
              FakeToken(TOKENS + 'TTS_MS_EN-US_ZIRA_11.0', 'Microsoft Zira Desktop - English (United States)'),
              FakeToken(TOKENS + 'ETI-Eloquence', 'Code Factory ETI-Eloquence')]


def registry_voices():
    """What the 32-bit-only registry view gives on Will's computer."""
    return [Token32(speech32.PREFIX + TOKENS + 'VW James', 'VW James'),
            Token32(speech32.PREFIX + TOKENS + 'VW Kate', 'VW Kate'),
            Token32(speech32.PREFIX + TOKENS + 'VW Paul', 'VW Paul')]


# ---------------------------------------------------------------------- the helper's protocol
class HostProtocolTests(unittest.TestCase):
    def run_host(self, requests, voice=None):
        voice = voice or FakeSpVoice()
        source = io.BytesIO(b''.join((json.dumps(r).encode() if isinstance(r, dict) else r) + b'\n'
                                     for r in requests))
        output = io.BytesIO()
        code = speech32_host.serve(source, output, make_voice=lambda: voice, pump=lambda: None)
        answers = [json.loads(line) for line in output.getvalue().decode('ascii').splitlines()]
        return code, answers, voice

    def test_ready_then_one_answer_per_request_in_order(self):
        code, answers, voice = self.run_host([
            {'id': 1, 'cmd': 'list'},
            {'id': 2, 'cmd': 'voice', 'voice': TOKENS + 'VW Paul'},
            {'id': 3, 'cmd': 'rate', 'value': 25},
            {'id': 4, 'cmd': 'volume', 'value': 80},
            {'id': 5, 'cmd': 'speak', 'text': 'Hello Will.', 'flags': 2},
            {'id': 6, 'cmd': 'done', 'ms': 0}])
        self.assertEqual(code, 0)
        self.assertEqual(answers[0], {'event': 'ready', 'ok': True, 'bits': 64 if sys.maxsize > 2 ** 32 else 32})
        self.assertEqual([a['id'] for a in answers[1:]], [1, 2, 3, 4, 5, 6])
        self.assertEqual([v['name'] for v in answers[1]['voices']],
                         ['Microsoft David Desktop - English (United States)', 'VW Paul', 'VW Kate'])
        self.assertEqual(answers[2]['name'], 'VW Paul')
        self.assertEqual(voice.Voice.GetDescription(), 'VW Paul')
        self.assertEqual((voice.Rate, voice.Volume), (10, 80))      # rate kept within SAPI's -10 to 10
        self.assertIn(('Speak', 'Hello Will.', 3), voice.calls)      # always async, purge kept
        self.assertIs(answers[6]['done'], False)

    def test_voice_is_found_by_its_token_name_when_the_id_differs(self):
        # A 32-bit program can see the same token under another root or spelling.
        _, answers, voice = self.run_host([{'id': 1, 'cmd': 'voice', 'voice': 'HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\x\\vw kate'}])
        self.assertTrue(answers[1]['ok'])
        self.assertEqual(voice.Voice.GetDescription(), 'VW Kate')

    def test_missing_voice_bad_line_and_unknown_request_answer_with_an_error(self):
        _, answers, voice = self.run_host([{'id': 1, 'cmd': 'voice', 'voice': 'VW Nobody'}, b'not json',
                                           {'id': 3, 'cmd': 'dance'}, {'id': 4, 'cmd': 'speak', 'text': 'Still here.'}])
        self.assertEqual([a.get('ok') for a in answers[1:]], [False, False, False, True])
        self.assertEqual(answers[1]['error'], 'That voice is not installed.')
        self.assertIsNone(answers[2]['id'])
        self.assertEqual(voice.Voice.GetDescription(), 'Microsoft David Desktop - English (United States)')

    def test_pause_and_resume_are_safe_to_repeat_and_stop_works_while_paused(self):
        _, answers, voice = self.run_host([
            {'id': 1, 'cmd': 'speak', 'text': 'A long paragraph.', 'flags': 1},
            {'id': 2, 'cmd': 'pause'}, {'id': 3, 'cmd': 'pause'}, {'id': 4, 'cmd': 'done', 'ms': 0},
            {'id': 5, 'cmd': 'resume'}, {'id': 6, 'cmd': 'resume'},
            {'id': 7, 'cmd': 'pause'}, {'id': 8, 'cmd': 'stop'}, {'id': 9, 'cmd': 'done', 'ms': 0}])
        calls = [c[0] for c in voice.calls]
        self.assertEqual(calls, ['Speak', 'Pause', 'Resume', 'Pause', 'Resume', 'Speak'])
        self.assertEqual(voice.calls[-1], ('Speak', '', 3))
        self.assertIs(answers[4]['done'], False)                     # paused with words waiting
        self.assertIs(answers[9]['done'], True)                      # stop ended the speech

    def test_quit_answers_and_stops_before_later_requests(self):
        code, answers, voice = self.run_host([{'id': 1, 'cmd': 'quit'}, {'id': 2, 'cmd': 'speak', 'text': 'Late.'}])
        self.assertEqual(code, 0)
        self.assertEqual([a.get('id') for a in answers[1:]], [1])
        self.assertEqual(voice.calls, [])

    def test_a_voice_that_cannot_be_made_says_so_and_stops(self):
        output = io.BytesIO()
        def broken():
            raise OSError('Class not registered')
        code = speech32_host.serve(io.BytesIO(b''), output, make_voice=broken, pump=lambda: None)
        self.assertEqual(code, 2)
        ready = json.loads(output.getvalue())
        self.assertEqual((ready['event'], ready['ok']), ('ready', False))
        self.assertIn('Class not registered', ready['error'])

    def test_it_stops_when_the_parent_program_ends(self):
        requests, ended = queue.Queue(), []
        alive = iter([True, True, False])
        speech32_host.watch_parent(1234, requests, ended.append, alive=lambda pid: next(alive), every=0)
        self.assertEqual(ended, [requests])
        self.assertFalse(speech32_host.parent_alive(2 ** 22 + 12345))
        self.assertTrue(speech32_host.parent_alive(os.getpid()))

    def test_helper_does_not_import_the_main_app(self):
        source = (HERE / 'speech32_host.py').read_text(encoding='utf-8')
        imported = {line.split()[1].split('.')[0] for line in source.splitlines()
                    if line.strip().startswith(('import ', 'from '))}
        self.assertLessEqual(imported, {'json', 'os', 'queue', 'sys', 'threading', 'time', 'pythoncom', 'win32com', 'ctypes'})


# ---------------------------------------------------------------------- the voice list
class VoiceListTests(unittest.TestCase):
    def test_32bit_only_voices_follow_the_64bit_ones_without_duplicates(self):
        extra = registry_voices() + [
            Token32(speech32.PREFIX + TOKENS + 'ETI-Eloquence', 'Code Factory ETI-Eloquence'),       # in both views
            Token32(speech32.PREFIX + TOKENS + 'Other David', 'Microsoft David Desktop - English (United States)')]
        voice = HybridVoice(NativeVoice(), extra)
        voices = voice.GetVoices()
        names = [voices.Item(i).GetDescription() for i in range(voices.Count)]
        self.assertEqual(names, ['Microsoft David Desktop - English (United States)',
                                 'Microsoft Zira Desktop - English (United States)',
                                 'Code Factory ETI-Eloquence', 'VW James', 'VW Kate', 'VW Paul'])
        self.assertIsInstance(voices.Item(0), FakeToken)     # the 64-bit voice wins

    def test_registry_lists_only_tokens_missing_from_the_64bit_view(self):
        class Key:
            def __init__(self, path): self.path = path
            def __enter__(self): return self
            def __exit__(self, *args): return False

        class Registry:
            HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_32KEY, KEY_WOW64_64KEY = 'HKLM', 1, 0x200, 0x100
            views = {0x200: {'MSTTS_V110_enUS_DavidM': 'Microsoft David Desktop', 'ETI-Eloquence': 'Eloquence',
                             'VW Paul': 'VW Paul', 'VW Kate': ''},
                     0x100: {'MSTTS_V110_enUS_DavidM': 'Microsoft David Desktop', 'eti-eloquence': 'Eloquence',
                             'MSTTS_V110_enUS_ZiraM': 'Microsoft Zira Desktop'}}
            def OpenKey(self, root, path, reserved=0, access=0):
                if isinstance(root, Key):
                    return Key((root.path, path))
                return Key(self.views[access & 0x300])
            def EnumKey(self, key, index):
                names = list(key.path)
                if index >= len(names): raise OSError('No more data')
                return names[index]
            def QueryValueEx(self, key, name):
                view, token = key.path
                return view[token], 1

        voices = speech32.thirty_two_bit_only_voices(Registry())
        self.assertEqual([(v.Id, v.GetDescription()) for v in voices],
                         [(speech32.PREFIX + TOKENS + 'VW Kate', 'VW Kate'), (speech32.PREFIX + TOKENS + 'VW Paul', 'VW Paul')])

    def test_no_32bit_only_voice_leaves_the_windows_voice_as_it_was(self):
        native = NativeVoice()
        self.assertIs(with_32bit_voices(native, registry=list), native)
        self.assertIsInstance(with_32bit_voices(native, registry=registry_voices), HybridVoice)

    def test_short_names_for_the_spoken_notice(self):
        self.assertEqual(speech32.short_name('VW Paul'), 'Paul')
        self.assertEqual(speech32.short_name('Microsoft David Desktop - English (United States)'), 'David')
        self.assertEqual(speech32.short_name('Code Factory ETI-Eloquence'), 'ETI-Eloquence')


# ---------------------------------------------------------------------- speaking through the helper
class HelperSpeechTests(HelperFixture):
    def hybrid(self, client_factory=None, native=None):
        native = native or NativeVoice()
        voice = HybridVoice(native, registry_voices(), client_factory=client_factory or self.client,
                            log=self.logged.append)
        return voice, native

    def setUp(self):
        super().setUp()
        self.logged = []

    def choose(self, voice, name):
        voices = voice.GetVoices()
        voice.Voice = next(voices.Item(i) for i in range(voices.Count) if voices.Item(i).GetDescription() == name)

    def test_client_lists_the_helper_voices(self):
        client = self.client()
        self.assertTrue(client.wait_ready(10))
        answer = client.ask('list', 5)
        self.assertEqual([v['name'] for v in answer['voices']][1:], ['VW Paul', 'VW Kate'])

    def test_chosen_32bit_voice_speaks_with_rate_volume_pause_resume_and_stop(self):
        voice, native = self.hybrid()
        voice.Rate, voice.Volume = 3, 70
        self.choose(voice, 'VW Paul')
        self.assertEqual(voice.Voice.GetDescription(), 'VW Paul')
        voice.Speak('Hello from Paul.', 1)
        self.assertTrue(wait_for(lambda: ('Speak', 'Hello from Paul.', 1) in self.calls()))
        self.assertFalse(voice.WaitUntilDone(0))
        voice.Pause()
        time.sleep(FakeSpVoice.SPEAK_SECONDS + 0.1)
        self.assertFalse(voice.WaitUntilDone(0))          # paused: still not done
        voice.Resume()
        self.assertTrue(voice.WaitUntilDone(3000))
        voice.Speak('Second sentence.', 1)
        voice.Speak('', 3)                                # interrupt_speech: async + purge
        self.assertTrue(voice.WaitUntilDone(0))
        voice.Rate = -2
        self.assertTrue(wait_for(lambda: ('Rate', -2) in self.calls()))
        calls = self.calls()
        self.assertEqual(calls[:3], [('Voice', 'VW Paul'), ('Rate', 3), ('Volume', 70)])
        self.assertEqual([c for c in calls if c[0] in ('Pause', 'Resume')], [('Pause',), ('Resume',)])
        self.assertIn(('Speak', '', 3), calls)
        self.assertEqual([c for c in native.calls if c[0] == 'Speak' and c[1]], [])   # 64-bit voice said nothing
        self.assertEqual(self.logged, [])

    def test_choosing_a_64bit_voice_again_stops_the_helper_speech_and_uses_sapi(self):
        voice, native = self.hybrid()
        self.choose(voice, 'VW Paul')
        voice.Speak('Paul talking.', 1)
        self.choose(voice, 'Microsoft Zira Desktop - English (United States)')
        voice.Speak('Zira talking.', 1)
        self.assertTrue(wait_for(lambda: ('Speak', '', 3) in self.calls()))
        self.assertEqual(native.Voice.GetDescription(), 'Microsoft Zira Desktop - English (United States)')
        self.assertIn(('Speak', 'Zira talking.', 1), native.calls)
        self.assertEqual(voice.Voice.GetDescription(), 'Microsoft Zira Desktop - English (United States)')

    def test_synchronous_speak_waits_until_the_helper_is_done(self):
        voice, native = self.hybrid()
        self.choose(voice, 'VW Kate')
        started = time.monotonic()
        voice.Speak('Wait for me.', 0)
        self.assertGreaterEqual(time.monotonic() - started, FakeSpVoice.SPEAK_SECONDS - 0.05)
        self.assertTrue(voice.WaitUntilDone(0))

    def test_closing_input_ends_the_helper(self):
        client = self.client()
        self.assertTrue(client.wait_ready(10))
        client.close(wait=5)
        self.assertIsNotNone(client.process.poll())

    def test_missing_helper_falls_back_to_the_64bit_voice_and_says_so_once(self):
        missing = lambda: self.client([str(self.folder / speech32.HELPER_NAME), '--parent', '1'])
        voice, native = self.hybrid(missing)
        self.choose(voice, 'VW Paul')
        voice.Speak('Welcome to Voice Companion.', 1)
        spoken = [c[1] for c in native.calls if c[0] == 'Speak' and c[1]]
        self.assertEqual(spoken, ['Paul could not start, so Companion is using David.', 'Welcome to Voice Companion.'])
        self.assertEqual(self.logged and self.logged[0].split(' (')[0], 'VW Paul')
        # The keyboard voice fails the same way a moment later: the user hears it once.
        other, other_native = self.hybrid(missing)
        self.choose(other, 'VW Paul')
        other.Speak('A', 1)
        self.assertEqual([c[1] for c in other_native.calls if c[0] == 'Speak' and c[1]], ['A'])
        # The choice is kept, so it is saved and tried again at the next start.
        self.assertEqual(voice.Voice.GetDescription(), 'VW Paul')
        self.assertTrue(voice.WaitUntilDone(3000))     # the 64-bit voice answers

    def test_notice_is_not_cut_off_by_the_purge_of_the_speech_that_found_the_problem(self):
        missing = lambda: self.client([str(self.folder / 'nothing.exe')])
        voice, native = self.hybrid(missing)
        voice._extra.append(Token32(speech32.PREFIX + TOKENS + 'VW Paul', 'VW Paul'))
        native.calls.clear()
        voice._chosen, voice._client = voice._extra[2], missing()
        voice.Speak('Next item.', 3)
        speaks = [c for c in native.calls if c[0] == 'Speak']
        self.assertEqual(speaks, [('Speak', 'Paul could not start, so Companion is using David.', 3), ('Speak', 'Next item.', 1)])

    def test_helper_that_never_gets_ready_falls_back_and_replays_unheard_words(self):
        never = lambda: self.client([sys.executable, '-c', 'import time; time.sleep(30)'])
        with patch.object(Speech32Client, 'START_SECONDS', 0.4):
            voice, native = self.hybrid(never)
            self.choose(voice, 'VW Paul')
            voice.Speak('Voice Companion is starting.', 1)
            self.assertFalse(voice.WaitUntilDone(0))
            time.sleep(0.5)
            voice.Speak('Say help.', 1)
        spoken = [c[1] for c in native.calls if c[0] == 'Speak' and c[1]]
        self.assertEqual(spoken, ['Paul could not start, so Companion is using David.',
                                  'Voice Companion is starting.', 'Say help.'])

    def test_helper_that_stops_answering_is_ended_and_the_64bit_voice_takes_over(self):
        with patch.dict(os.environ, {'FAKE_HANG': 'freeze'}), patch.object(Speech32Client, 'HANG_SECONDS', 0.5):
            voice, native = self.hybrid()
            self.choose(voice, 'VW Paul')
            client = voice._client
            self.assertTrue(client.wait_ready(10))
            voice.Speak('This will freeze.', 1)
            started = time.monotonic()
            self.assertTrue(voice.WaitUntilDone(0))         # a stuck helper is never waited on
            self.assertLess(time.monotonic() - started, 1)
            time.sleep(0.7)
            voice.Speak('Are you there?', 1)
        spoken = [c[1] for c in native.calls if c[0] == 'Speak' and c[1]]
        self.assertEqual(spoken, ['Paul stopped working, so Companion is using David.', 'Are you there?'])
        self.assertTrue(wait_for(lambda: client.process.poll() is not None))
        self.assertIn('stopped', self.logged[0])

    def test_helper_that_cannot_make_a_voice_falls_back(self):
        with patch.dict(os.environ, {'FAKE_BROKEN': '1'}):
            voice, native = self.hybrid()
            self.choose(voice, 'VW Kate')
            self.assertTrue(wait_for(lambda: voice._client is None or voice._client.failure() is not None))
            voice.Speak('Hello.', 1)
        self.assertEqual([c[1] for c in native.calls if c[0] == 'Speak' and c[1]][0],
                         'Kate could not start, so Companion is using David.')
        self.assertIn('Class not registered', self.logged[0])

    def test_voice_the_helper_cannot_find_falls_back_instead_of_using_another_voice(self):
        voice, native = self.hybrid()
        self.choose(voice, 'VW James')            # in the registry, but SAPI does not list it
        self.assertTrue(voice._client.wait_ready(10))
        self.assertTrue(wait_for(lambda: voice._voice_answer and voice._voice_answer[0] is not None, 5))
        voice.Speak('Hello.', 1)
        self.assertEqual([c[1] for c in native.calls if c[0] == 'Speak' and c[1]],
                         ['James could not start, so Companion is using David.', 'Hello.'])

    def test_choosing_the_voice_again_after_a_failure_tries_the_helper_again(self):
        missing = lambda: self.client([str(self.folder / 'nothing.exe')])
        factories = iter([missing, self.client])
        voice, native = self.hybrid(lambda: next(factories)())
        self.choose(voice, 'VW Paul')
        voice.Speak('One.', 1)
        self.choose(voice, 'VW Paul')
        voice.Speak('Two.', 1)
        self.assertTrue(wait_for(lambda: ('Speak', 'Two.', 1) in self.calls()))
        self.assertNotIn('Two.', [c[1] for c in native.calls if c[0] == 'Speak'])

    def test_voice_check_lists_the_helper_voices(self):
        import voice_inventory
        report = self.folder / 'voice-check.txt'
        with patch.object(speech32, 'Speech32Client', lambda: self.client()):
            names, path = voice_inventory.report(HybridVoice(NativeVoice(), registry_voices()), report)
        text = report.read_text(encoding='utf-8')
        self.assertIn('VW Paul', names)
        self.assertIn('Voices from the 32-bit speech helper (VoiceCompanion-Speech32.exe):\n'
                      '  Microsoft David Desktop - English (United States)\n  VW Paul\n  VW Kate\n', text)

    def test_voice_check_says_why_the_helper_did_not_answer(self):
        import voice_inventory
        report = self.folder / 'voice-check.txt'
        with patch.object(speech32, 'Speech32Client', lambda: self.client([str(self.folder / 'nothing.exe')])):
            voice_inventory.report(NativeVoice(), report)
        self.assertIn('The 32-bit speech helper did not answer: FileNotFoundError', report.read_text(encoding='utf-8'))


# ---------------------------------------------------------------------- the app's voice paths
class AppVoiceTests(HelperFixture):
    """SpeechWorker, keyboard speech, voice commands, Options and the saved voice."""

    def worker(self):
        from speech_worker import SpeechWorker
        factory = lambda: HybridVoice(NativeVoice(), registry_voices(), client_factory=self.client, log=lambda text: None)
        worker = SpeechWorker(factory=factory, pump=lambda: None)
        self.addCleanup(setattr, worker, 'generation', -1)
        return worker

    def test_speech_worker_makes_its_windows_voice_with_the_32bit_voices(self):
        import speech_worker
        made = NativeVoice()
        with patch.object(speech32, 'thirty_two_bit_only_voices', registry_voices), \
                patch.object(speech_worker, 'sapi_dispatch', lambda: made):
            voice = speech_worker.sapi_voice()
        self.assertIsInstance(voice, HybridVoice)
        self.assertIs(voice._native, made)
        with patch.object(speech32, 'thirty_two_bit_only_voices', list), \
                patch.object(speech_worker, 'sapi_dispatch', lambda: made):
            self.assertIs(speech_worker.sapi_voice(), made)

    def test_keyboard_speech_speaks_with_a_chosen_32bit_voice(self):
        from keyboard_speech import KeyboardSpeech
        worker = KeyboardSpeech.__new__(KeyboardSpeech)
        paul = speech32.PREFIX + TOKENS + 'VW Paul'
        worker.settings = (paul, 2, 90, None, 0); worker.problem = None; worker.paused = False
        worker.active = False; worker.quiet_until = 0
        worker.queue = queue.Queue()
        for item in ('Read this.', ('pause',), ('resume',), ('interrupt',), None):
            worker.queue.put(item)
        native = NativeVoice()
        client = type(sys)('win32com.client')
        client.Dispatch = lambda name: native
        com = type(sys)('pythoncom')
        com.CoInitialize = com.CoUninitialize = lambda: None
        with patch.dict(sys.modules, {'pythoncom': com, 'win32com': type(sys)('win32com'), 'win32com.client': client}), \
                patch.object(speech32, 'thirty_two_bit_only_voices', registry_voices), \
                patch.object(speech32, 'Speech32Client', lambda: self.client()):
            worker.run()
        self.assertIsNone(worker.problem)
        self.assertTrue(wait_for(lambda: ('Speak', '', 3) in self.calls()))
        calls = self.calls()
        self.assertEqual(calls[0], ('Voice', 'VW Paul'))
        self.assertIn(('Speak', 'Read this.', 3), calls)
        self.assertEqual([c[0] for c in calls if c[0] in ('Pause', 'Resume')], ['Pause', 'Resume'])
        self.assertEqual([c for c in native.calls if c[0] == 'Speak' and c[1]], [])

    def test_saved_32bit_voice_is_restored_at_start(self):
        import companion
        worker = self.worker()
        self.assertTrue(companion.restore_windows_voice(worker, 'VW Paul'))
        self.assertEqual(worker.Voice.GetDescription(), 'VW Paul')
        worker.Speak('Voice Companion is ready.', 1)
        self.assertTrue(wait_for(lambda: ('Speak', 'Voice Companion is ready.', 1) in self.calls()))
        self.assertEqual(self.calls()[0], ('Voice', 'VW Paul'))
        self.assertFalse(companion.restore_windows_voice(worker, 'VW Nobody'))

    def companion_patches(self, worker):
        import companion
        patches = [patch.object(companion, 'voice', worker, create=True), patch.object(companion, 'TEXT_MODE', False),
                   patch.object(companion, 'AI_SPEECH', None), patch.object(companion, 'ESPEAK_SPEECH', None),
                   patch.object(companion, 'KEYBOARD_SPEECH', None), patch.object(companion, 'APP_WINDOW', None),
                   patch.object(companion, 'VOICE_PICK_INDEX', None), patch.object(companion, 'VOICE_PICK_ENGINE', None),
                   patch.object(companion, 'VOICE_PICK_ORIGINAL', None), patch.object(companion, 'SYNTH_PICK_INDEX', None),
                   patch.object(companion, 'VOICE_PICK_CONFIRM', False), patch.object(companion, 'SPEECH_PAUSED', False),
                   patch.object(companion, 'APP', self.folder)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return companion

    def test_use_voice_command_chooses_a_32bit_voice_and_saves_it(self):
        worker = self.worker()
        companion = self.companion_patches(worker)
        with patch.object(companion, 'speak') as speech:
            companion.handle('Use voice VW Paul.', 'awake')
        self.assertEqual(speech.call_args.args[0], 'Using VW Paul.')
        self.assertEqual(worker.Voice.GetDescription(), 'VW Paul')
        self.assertEqual(json.loads((self.folder / 'speech-settings.json').read_text())['voice'], 'VW Paul')
        self.assertTrue(wait_for(lambda: ('Voice', 'VW Paul') in self.calls()))
        names = [choice[1] for choice in companion.voice_choices('windows')]
        self.assertEqual(names.count('VW Paul'), 1)
        self.assertEqual(names[:3], ['Microsoft David Desktop - English (United States)',
                                     'Microsoft Zira Desktop - English (United States)', 'Code Factory ETI-Eloquence'])

    def test_options_lists_and_applies_a_32bit_voice(self):
        import app_settings
        from settings_model import DEFAULTS
        worker = self.worker()
        companion = self.companion_patches(worker)
        with patch.object(companion, 'PREFERENCES', dict(DEFAULTS)), patch.object(companion, 'mail_session', None), \
                patch.object(companion, 'web_session', None), patch.object(companion, 'apply_transcript'), \
                patch('windows_actions.startup_enabled', return_value=False), patch.object(app_settings, 'save_preferences'):
            values, context = app_settings.snapshot(companion)
            self.assertIn('VW Kate', context['windows_voices'])
            values['windows_voice'] = 'VW Kate'
            app_settings.apply_settings(companion, values)
        self.assertEqual(worker.Voice.GetDescription(), 'VW Kate')
        self.assertTrue(wait_for(lambda: ('Voice', 'VW Kate') in self.calls()))
        self.assertEqual(json.loads((self.folder / 'speech-settings.json').read_text())['voice'], 'VW Kate')

    def test_app_wide_stop_pause_and_resume_reach_the_helper(self):
        worker = self.worker()
        companion = self.companion_patches(worker)
        companion.restore_windows_voice(worker, 'VW Paul')
        worker.Speak('A long answer from Companion.', 1)
        companion.control_speech('pause')        # speech_stop: the user's first word pauses
        companion.control_speech('resume')       # nothing was said after all
        companion.control_speech('pause')
        companion.interrupt_speech()             # a command: the old speech ends
        self.assertFalse(companion.SPEECH_PAUSED)
        self.assertTrue(wait_for(lambda: self.calls() and self.calls()[-1] == ('Speak', '', 3)))
        calls = self.calls()
        self.assertEqual([c[0] for c in calls if c[0] in ('Pause', 'Resume')], ['Pause', 'Resume', 'Pause', 'Resume'])
        self.assertTrue(wait_for(lambda: not companion.speech_busy(), 3))


class DroppedVoiceTests(HelperFixture):
    """A stand-in voice that is dropped must close its helper at once: no orphan
    VoiceCompanion-Speech32.exe processes may pile up."""

    def alive(self):
        return sum(1 for client in self.clients if client.process is not None and client.process.poll() is None)

    def test_frozen_main_voice_is_replaced_and_its_helper_closed(self):
        from speech_worker import SpeechWorker
        release = threading.Event()
        self.addCleanup(release.set)
        natives = []

        def factory():
            native = NativeVoice()
            native.hang_word = 'freeze'
            original = native.Speak
            def speak(text, flags):
                if 'freeze' in text:
                    release.wait(30)
                return original(text, flags)
            native.Speak = speak
            natives.append(native)
            return HybridVoice(native, registry_voices(), client_factory=self.client, log=lambda text: None)

        worker = SpeechWorker(factory=factory, pump=lambda: None)
        worker.STUCK_SECONDS = 0.3
        self.addCleanup(setattr, worker, 'generation', -1)
        import companion
        companion.restore_windows_voice(worker, 'VW Paul')
        self.assertTrue(wait_for(lambda: self.alive() == 1 and self.clients[0].ready))
        companion.restore_windows_voice(worker, 'Microsoft Zira Desktop - English (United States)')
        worker.Speak('This will freeze.', 1)      # the 64-bit voice stops answering
        self.assertTrue(wait_for(lambda: worker.busy_since is not None, 3))
        time.sleep(0.4)
        worker.Speak('Hello again.', 1)            # stuck: a new voice is made
        self.assertEqual(worker.restarts, 1)
        self.assertTrue(wait_for(lambda: len(natives) == 2, 3))
        self.assertTrue(wait_for(lambda: self.alive() == 0, 3), 'helpers still running: %d' % self.alive())
        self.assertTrue(wait_for(lambda: ('Speak', 'Hello again.', 1) in natives[1].calls, 3))

    def test_speech_worker_close_and_a_voice_made_too_late_close_their_helpers(self):
        from speech_worker import SpeechWorker
        worker = SpeechWorker(factory=lambda: HybridVoice(NativeVoice(), registry_voices(), client_factory=self.client,
                                                           log=lambda text: None), pump=lambda: None)
        import companion
        companion.restore_windows_voice(worker, 'VW Kate')
        self.assertTrue(wait_for(lambda: self.alive() == 1))
        worker.close()
        self.assertTrue(wait_for(lambda: self.alive() == 0, 3))
        made = HybridVoice(NativeVoice(), registry_voices(), client_factory=self.client)
        made.Voice = registry_voices()[1]
        speech32.release(made)
        self.assertTrue(wait_for(lambda: self.alive() == 0, 3))
        speech32.release(NativeVoice())           # a plain voice: nothing to close


class PackagingTests(unittest.TestCase):
    def test_build_makes_installs_and_checks_the_32bit_helper(self):
        build = (HERE / 'build-windows.ps1').read_text(encoding='utf-8')
        self.assertIn("'VoiceCompanion-Speech32'", build)
        self.assertIn("'speech32_host.py'", build)
        self.assertIn("dist\\VoiceCompanion\\VoiceCompanion-Speech32.exe", build)
        self.assertIn("'--check-speech32'", build)
        workflow = (HERE.parent / '.github' / 'workflows' / 'windows-installer.yml').read_text(encoding='utf-8')
        self.assertIn('architecture: x86', workflow)
        self.assertIn('VOICE_COMPANION_BUILD_PYTHON32', workflow)

    def test_packaged_check_rejects_a_missing_or_64bit_helper(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / speech32.HELPER_NAME
            with self.assertRaisesRegex(RuntimeError, 'is missing'):
                speech32.check_helper(exe)
            header = bytearray(512)
            header[:2] = b'MZ'
            header[0x3c:0x40] = (128).to_bytes(4, 'little')
            header[128:132] = b'PE\0\0'
            header[132:134] = (0x8664).to_bytes(2, 'little')
            exe.write_bytes(bytes(header))
            with self.assertRaisesRegex(RuntimeError, 'not a 32-bit program'):
                speech32.check_helper(exe)
            header[132:134] = (0x14c).to_bytes(2, 'little')
            exe.write_bytes(bytes(header))
            self.assertEqual(speech32.machine_bits(exe), 32)


if __name__ == '__main__':
    unittest.main()


class NoticeSurvivesPurgeTests(HelperFixture):
    """Review, November 11, 2026: with the helper missing, the "could not start" notice was
    purged by the very next speech (keyboard echo speaks with purge), so Will heard only
    "Using VW Paul." in David's voice, with no reason."""

    def test_the_notice_is_heard_even_when_the_next_speech_purges(self):
        native = NativeVoice()
        voice = speech32.HybridVoice(native, registry_voices(), log=lambda text: None,
                                     client_factory=lambda: self.client([str(self.folder / 'missing-Speech32.exe')]))
        voice.Speak('', 3)                               # keyboard speech interrupts first
        tokens = voice.GetVoices()
        voice.Voice = next(tokens.Item(i) for i in range(tokens.Count) if 'Paul' in tokens.Item(i).GetDescription())
        voice.Rate, voice.Volume = 0, 100
        voice.Speak('', 3)                               # the app-wide speech stop
        voice.Speak('Using VW Paul.', 3)
        heard = ' '.join(native.waiting)
        self.assertIn('Paul could not start, so Companion is using David.', heard)
        self.assertIn('Using VW Paul.', heard)
        # Once heard safely, it is not said again.
        voice.Speak('Next thing.', 3)
        self.assertNotIn('could not start', ' '.join(native.waiting))

    def test_without_a_purge_the_notice_is_not_doubled(self):
        native = NativeVoice()
        voice = speech32.HybridVoice(native, registry_voices(), log=lambda text: None,
                                     client_factory=lambda: self.client([str(self.folder / 'missing-Speech32.exe')]))
        tokens = voice.GetVoices()
        voice.Voice = next(tokens.Item(i) for i in range(tokens.Count) if 'Paul' in tokens.Item(i).GetDescription())
        voice.Speak('Hello.', 1)
        self.assertEqual(' '.join(native.waiting).count('could not start'), 1)


class GentleCloseTests(HelperFixture):
    """kill() lets the helper exit by itself (so its one-file launcher can clean up) and never waits."""

    def test_kill_returns_at_once_and_the_helper_ends(self):
        client = self.client()
        self.assertTrue(client.wait_ready(15) if hasattr(client, 'wait_ready') else True)
        started = time.monotonic()
        client.kill()
        self.assertLess(time.monotonic() - started, 0.5)
        client.process.wait(10)          # ends by itself after its input closes
        self.assertIsNotNone(client.process.returncode)
