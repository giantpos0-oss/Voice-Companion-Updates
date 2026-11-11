"""Companion stops talking the moment you start to speak, on every screen (speech_stop.py).

Will, November 10, 2026: whether Companion went quiet when he started a command or
started dictating depended on the screen and the command. Now one place in the
recognizer loop does it for every utterance. These tests drive the real loop in
companion.main() with a scripted recognizer, and check the noise and echo guard.
"""
import queue
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import companion as app
from speech_stop import SpeechStop, real_words


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class GuardTests(unittest.TestCase):
    def test_noise_words_never_count(self):
        stop = SpeechStop()
        for noise in ('', 'the', 'uh', 'hmm', 'the the', '[unk]', 'a', 'um the'):
            self.assertFalse(stop.heard(noise, speaking=True), noise)
        self.assertFalse(stop.listening)
        self.assertEqual(real_words('Uh, the email.'), ['email'])

    def test_the_first_real_word_stops_speech(self):
        stop = SpeechStop()
        self.assertTrue(stop.heard('open', speaking=True))
        self.assertTrue(stop.listening)

    def test_companions_own_words_heard_back_do_not_stop_it(self):
        clock = Clock()
        stop = SpeechStop(clock)
        stop.said('Main menu. What would you like to do? You have 3 new messages.')
        for echo in ('main', 'main menu', 'what would you like', 'you have three new messages', 'main menu what would you lake'):
            self.assertFalse(stop.heard(echo, speaking=True), echo)
        self.assertTrue(stop.heard('open email', speaking=True))
        stop.finish()
        # Order matters: the same words in another order are the user's.
        self.assertTrue(stop.heard('new messages you have', speaking=True))
        stop.finish()
        # A navigation command always stops it, even when Companion just said the word.
        stop.said('Say next to hear more.')
        self.assertTrue(stop.heard('next', speaking=True, command=True))
        self.assertTrue(stop.suggested('Next.'))
        self.assertFalse(stop.suggested('next to hear more'))
        stop.finish()
        # Old words are no longer coming out of the speakers.
        clock.now += 60
        self.assertTrue(stop.heard('main menu', speaking=True))

    def test_once_the_user_is_talking_their_words_are_theirs(self):
        stop = SpeechStop()
        self.assertFalse(stop.heard('write', speaking=False))   # nothing to stop yet
        self.assertTrue(stop.listening)
        stop.said('Text added.')                                 # speech starts while they talk
        self.assertTrue(stop.heard('write text added', speaking=True))

    def test_a_pause_with_no_end_goes_stale(self):
        clock = Clock()
        stop = SpeechStop(clock)
        stop.heard('hello', speaking=True); stop.pausing()
        self.assertFalse(stop.stale())
        clock.now += 30
        self.assertTrue(stop.stale())
        self.assertTrue(stop.finish())
        self.assertFalse(stop.finish())


class Recognizer:
    """Vosk's KaldiRecognizer, scripted: each chunk of sound gives a partial or a final result."""
    def __init__(self, script, done, state, speaking):
        self.script, self.done, self.state, self.speaking = list(script), done, state, speaking
        self.partial, self.text = '', ''

    def AcceptWaveform(self, audio):
        if not self.script:
            self.done.set()
            return False
        kind, words, *talk = self.script.pop(0)
        if self.speaking:
            # Companion talks from the first sound on (after the startup words, which the loop skips).
            self.state['speaking'], self.speaking = True, False
        if talk and callable(talk[0]):
            talk[0]()
        elif talk:
            self.state['speaking'] = True
        if not self.script:
            self.done.set()
        if kind == 'partial':
            self.partial = words
            return False
        self.text, self.partial = words, ''
        return True

    def PartialResult(self):
        return '{"partial": "%s"}' % self.partial

    def Result(self):
        return '{"text": "%s"}' % self.text

    def Reset(self):
        self.partial = ''


class Audio:
    """The microphone queue: quiet for the startup moment, then one chunk per call."""
    def __init__(self):
        self.start = time.monotonic()

    def get(self, timeout=None):
        if time.monotonic() - self.start < .45:
            time.sleep(timeout or .02)
            raise queue.Empty
        return b'\x00\x00' * 160

    def get_nowait(self):
        raise queue.Empty


class LoopTests(unittest.TestCase):
    """The real recognizer loop in companion.main(), with the microphone, speech and screens left out."""

    def run_loop(self, mode, script, saying='', speaking=True, setup=None):
        events = []
        state = {'speaking': False}
        done = threading.Event()
        stack = ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        window = Mock(commands=queue.Queue(), settings_results=queue.Queue(), key_feedback=queue.Queue(),
                      settings_notices=queue.Queue(), ui_actions=queue.Queue(), closed=done, last_navigation=0)
        sounddevice = Mock()
        previous_sd = sys.modules.get('sounddevice')
        sys.modules['sounddevice'] = sounddevice
        stack.callback(lambda: sys.modules.__setitem__('sounddevice', previous_sd) if previous_sd is not None
                       else sys.modules.pop('sounddevice', None))
        original_control, original_interrupt = app.control_speech, app.interrupt_speech

        def control(action):
            events.append(('control', action))
            original_control(action)

        def interrupt():
            events.append(('interrupt',))
            state['speaking'] = False
            original_interrupt()

        def handle(text, current):
            events.append(('handle', text, current, app.SPEECH_PAUSED, state['speaking']))
            return current

        values = {'MODEL': root, 'PARAKEET_MODEL': root / 'missing', 'TEXT_MODE': False, 'APP_WINDOW': window,
                  'KEYBOARD_SPEECH': None, 'ESPEAK_SPEECH': None, 'AI_SPEECH': None, 'SPEECH_PAUSED': False,
                  'AUDIO': Audio(), 'AUDIO_OVERFLOW': False, 'CHROME_SETUP': None, 'SETTINGS_PANEL': None,
                  'PREFERENCES': dict(app.PREFERENCES, microphone_off=False), 'SPEECH_STOP': SpeechStop(),
                  'INPUT_MODE': app.INPUT_MODE}
        for name, value in values.items():
            stack.enter_context(patch.object(app, name, value))
        stubs = {'Model': lambda path: object(), 'SetLogLevel': lambda level: None,
                 'KaldiRecognizer': lambda model, rate: Recognizer(script, done, state, speaking),
                 'update_running_elsewhere': lambda: False, 'open_microphone': lambda sd, attempts=5: Mock(),
                 'microphone_active': lambda stream: True, 'close_microphone': lambda stream: None,
                 'announce_startup': lambda: mode, 'sync_app_context': lambda *a, **k: None, 'media': lambda *a: None,
                 'start_freeze_watch': lambda *a, **k: None, 'poll_thunderbird_watch': lambda m: m,
                 'poll_file_manager': lambda m: m, 'poll_app_updates': lambda m: m, 'update_audio_ducking': lambda *a: None,
                 'poll_media_stream': lambda *a, **k: None, 'browser_focus_notice': lambda m: '',
                 'close_from_window': lambda m: None, 'speak': lambda text: None,
                 'speech_busy': lambda: app.SPEECH_PAUSED or state['speaking'],
                 'control_speech': control, 'interrupt_speech': interrupt, 'handle': handle}
        for name, value in stubs.items():
            stack.enter_context(patch.object(app, name, value))
        stack.enter_context(patch('guide_files.publish_guides', lambda *a, **k: None))
        stack.enter_context(patch('app_updates.AppUpdates', Mock()))
        stack.enter_context(patch('download_screen.poll', lambda m, current: current))
        stack.enter_context(patch('youtube_screen.poll', lambda m, current: current))
        if saying:
            app.SPEECH_STOP.said(saying)
        if setup:
            setup(stack)
        self.assertEqual(app.main(), 0)
        return events, state

    def setUp(self):
        patcher = patch.object(app, 'INPUT_MODE', 'mixed'); patcher.start(); self.addCleanup(patcher.stop)

    def test_a_command_stops_speech_on_its_first_real_word_on_every_screen(self):
        for mode, command in (('awake', 'open email'), ('document', 'save document'), ('email_draft', 'send it'),
                              ('web', 'list links'), ('mailbox', 'read message'), ('youtube', 'search for jazz')):
            with self.subTest(mode=mode):
                first = command.split()[0]
                events, _ = self.run_loop(mode, [('partial', 'uh'), ('partial', first), ('partial', command),
                                                 ('final', command)])
                # "uh" did nothing; the first real word paused speech at once.
                self.assertEqual(events[0], ('control', 'pause'), events)
                self.assertEqual(events[1], ('interrupt',), events)       # the command ends the old speech
                self.assertEqual(events[2][:3], ('handle', command, mode))
                self.assertFalse(events[2][3], 'speech is no longer paused when the command runs')

    def test_dictation_stops_speech_and_keeps_the_unfinished_sentence(self):
        def unfinished(stack):
            app.PREFERENCES['dictation_echo'] = 'at the end of a sentence'
            app.DICTATION_ECHO.clear()
            app.DICTATION_ECHO.choice = 'at the end of a sentence'
            app.DICTATION_ECHO.sentence = 'The meeting is'
        for mode in ('document', 'email_draft', 'note'):
            with self.subTest(mode=mode), patch.object(app, 'INPUT_MODE', 'dictation'):
                events, _ = self.run_loop(mode, [('partial', 'at'), ('partial', 'at noon'), ('final', 'at noon')],
                                          setup=unfinished)
                self.assertEqual(events[0], ('control', 'pause'))
                self.assertEqual(events[1], ('interrupt',))
                self.assertEqual(events[2][:3], ('handle', 'at noon', mode))
                self.assertEqual(app.DICTATION_ECHO.sentence, 'The meeting is')
        app.DICTATION_ECHO.clear()

    def test_stop_talking_keeps_the_place_so_resume_goes_on(self):
        paused = []
        script = [('partial', 'stop'), ('partial', 'stop talking'), ('final', 'stop talking'),
                  ('partial', '', lambda: paused.append(app.SPEECH_PAUSED))]
        events, state = self.run_loop('awake', script)
        self.assertEqual(events[0], ('control', 'pause'))
        self.assertNotIn(('interrupt',), events)                      # nothing was thrown away
        self.assertNotIn(('control', 'resume'), events)
        self.assertEqual(paused, [True])                              # still paused at its place
        self.assertTrue(state['speaking'])

    def test_resume_said_while_paused_is_a_command_not_new_speech(self):
        events, _ = self.run_loop('awake', [('partial', 'resume', lambda: setattr(app, 'SPEECH_PAUSED', True)),
                                            ('final', 'resume')], speaking=False)
        self.assertNotIn(('interrupt',), events)
        self.assertEqual(events[-1][:3], ('handle', 'resume', 'awake'))

    def test_noise_that_comes_to_nothing_lets_speech_go_on(self):
        events, state = self.run_loop('document', [('partial', 'well'), ('final', '')])
        self.assertEqual(events, [('control', 'pause'), ('control', 'resume')])
        self.assertFalse(app.SPEECH_PAUSED)
        self.assertTrue(state['speaking'])

    def test_noise_words_never_stop_speech(self):
        events, _ = self.run_loop('awake', [('partial', 'the'), ('partial', 'uh'), ('final', 'the')])
        self.assertEqual(events, [])

    def test_companions_own_voice_never_stops_it_or_becomes_a_command(self):
        saying = 'Main menu. What would you like to do? Say next or previous to move through the items.'
        events, _ = self.run_loop('awake', [('partial', 'main menu'), ('partial', 'main menu what would you'),
                                            ('final', 'main menu what would you like to do')], saying=saying)
        self.assertEqual(events, [])

    def test_talk_in_the_room_never_cuts_a_help_topic_off(self):
        # Help reading goes on from where it paused (test_onboard_help records this design).
        events, state = self.run_loop('help', [('partial', 'banana'), ('final', 'banana bread')])
        self.assertEqual(events[:2], [('control', 'pause'), ('control', 'resume')])
        self.assertNotIn(('interrupt',), events)
        self.assertTrue(state['speaking'])
        events, _ = self.run_loop('help', [('partial', 'next'), ('final', 'next topic')])
        self.assertEqual(events[:2], [('control', 'pause'), ('interrupt',)])
        self.assertEqual(events[2][:3], ('handle', 'next topic', 'help'))

    def test_speech_that_starts_while_the_user_talks_stops_and_their_words_are_kept(self):
        # Dictation read back, a notice: before, the words after it were thrown away as echo.
        script = [('partial', 'please'), ('partial', 'please call', 'Companion starts to talk'),
                  ('partial', 'please call me'), ('final', 'please call me')]
        events, _ = self.run_loop('document', script, speaking=False)
        self.assertEqual(events[0], ('control', 'pause'))
        self.assertEqual(events[1], ('interrupt',))
        self.assertEqual(events[2][:3], ('handle', 'please call me', 'document'))

    def acted(self, events, words, mode):
        handled = [event for event in events if event[0] == 'handle']
        self.assertEqual([event[1:3] for event in handled], [(words, mode)], events)
        self.assertIn(('interrupt',), events[:events.index(handled[0])])   # the old speech ended first

    def test_a_suggested_command_said_during_the_prompt_is_acted_on(self):
        # Coordinator, November 10, 2026: prompts tell people what to say. Saying it while
        # Companion still talks must work, even though Companion just said those words.
        cases = (
            # The main menu reads its items; an item's name is a command there.
            ('awake', 'Office tools (O), 2 of 10.', 'office tools'),
            ('awake', app.MAIN_MENU_PROMPT, 'next'),
            # Thunderbird setup (thunderbird_setup.py) and an email account that is ready.
            ('awake', 'Okay. Nothing was installed. When you want Thunderbird, say add Thunderbird account.',
             'add thunderbird account'),
            ('awake', 'Gmail is connected and selected. Say check email to open it.', 'check email'),
            # The inbox: R is Reply; its words are a command there.
            ('mailbox', 'Message 2 of 9. From Bob. Lunch. Press R to reply, or say reply.', 'reply'),
            ('mailbox', 'You have no new mail. Say get more emails to look again.', 'get more emails'),
            # A web page.
            ('web', 'Page loaded: Veterans Affairs. Say list links to hear the links.', 'list links'),
        )
        for mode, prompt, words in cases:
            with self.subTest(mode=mode, words=words):
                first = words.split()[0]
                events, _ = self.run_loop(mode, [('partial', first), ('partial', words), ('final', words)], saying=prompt)
                self.acted(events, words, mode)

    def test_dictated_words_that_share_words_with_companion_are_kept(self):
        # In writing fields, when in doubt, keep the user's words.
        cases = (('The meeting is at noon.', 'the meeting is at noon tomorrow'),
                 ('The meeting is at noon.', 'at noon'),
                 ('Text added. The meeting is at noon.', 'is at noon'),
                 ('Saved. Your document has 3 pages.', 'my document has three pages'))
        for mode in ('document', 'email_draft', 'note'):
            for said, dictated in cases:
                with self.subTest(mode=mode, dictated=dictated), patch.object(app, 'INPUT_MODE', 'dictation'):
                    events, _ = self.run_loop(mode, [('partial', dictated.split()[0]), ('partial', dictated),
                                                     ('final', dictated)], saying=said)
                    self.acted(events, dictated, mode)

    def test_a_long_passage_heard_back_is_ignored_on_every_screen(self):
        passage = ('The veterans center opens at nine in the morning on weekdays, and the parking lot is behind '
                   'the main building next to the clinic.')
        # One recognizer slip ("weak days").
        echo = 'the veterans center opens at nine in the morning on weak days and the parking lot is behind the main building'
        for mode in ('awake', 'mailbox', 'web', 'document', 'email_draft'):
            with self.subTest(mode=mode), patch.object(app, 'INPUT_MODE', 'dictation' if mode in ('document', 'email_draft') else 'mixed'):
                events, state = self.run_loop(mode, [('partial', 'the veterans'), ('partial', echo[:40]), ('final', echo)],
                                              saying=passage)
                self.assertEqual([event for event in events if event[0] != 'control'], [], events)
                self.assertTrue(state['speaking'])

    def test_numbers_said_as_digits_are_heard_back_as_words(self):
        said = 'You have 12 new messages and 3 drafts in your inbox.'
        events, _ = self.run_loop('awake', [('partial', 'you have twelve'),
                                            ('final', 'you have twelve new messages and three drafts')], saying=said)
        self.assertEqual(events, [])

    def test_words_that_only_share_some_words_with_the_prompt_are_not_echo(self):
        # The old rule (two thirds of the words said lately) took this for echo.
        said = 'Main menu. What would you like to do? Say next or previous to move through the items.'
        events, _ = self.run_loop('awake', [('partial', 'what'), ('partial', 'what time'), ('final', 'what time is it')],
                                  saying=said)
        self.acted(events, 'what time is it', 'awake')

    def test_an_answer_said_over_its_question_is_kept(self):
        # Review, November 11, 2026: "Friday" said over "Type or say a day, such as Friday"
        # was taken for Companion's echo, and nothing happened.
        for mode, said, answer in (('task_input', 'Go to a day. Type or say a day, such as Friday or October 30.', 'friday'),
                                   ('document_name', 'Save as. Or say or type another folder, such as Desktop.', 'desktop')):
            with self.subTest(mode=mode):
                events, _ = self.run_loop(mode, [('partial', answer), ('final', answer)], saying=said)
                self.acted(events, answer, mode)

    def test_typed_commands_and_keys_still_stop_speech_at_once(self):
        window = Mock(commands=queue.Queue())
        window.commands.put(('keyboard', 'Down'))
        with patch.object(app, 'APP_WINDOW', window), patch.object(app, 'interrupt_speech') as stop, \
                patch.object(app, 'navigation_key', return_value=None), patch.object(app, 'sync_app_context'):
            app.process_keyboard_batch('awake')
        stop.assert_called()


class PartialTests(unittest.TestCase):
    """user_started_speaking() on its own: what one partial result does on each screen."""

    def partial(self, words, mode, speaking=True, said=''):
        recognizer = Mock()
        recognizer.PartialResult.return_value = '{"partial":"%s"}' % words
        stop = SpeechStop()
        if said:
            stop.said(said)
        with patch.object(app, 'SPEECH_STOP', stop), patch.object(app, 'SPEECH_PAUSED', False), \
                patch.object(app, 'speech_busy', return_value=speaking), patch.object(app, 'control_speech') as control, \
                patch.object(app, 'handle') as handle, patch.object(app, 'INPUT_MODE', 'mixed'):
            stopped = app.user_started_speaking(recognizer, mode)
            handle.assert_not_called()
            recognizer.Reset.assert_not_called()
        return stopped, control

    def test_partial_words_pause_without_acting_or_resetting(self):
        for mode in ('awake', 'document', 'email_draft', 'mailbox', 'web', 'help', 'media', 'settings', 'youtube'):
            with self.subTest(mode=mode):
                stopped, control = self.partial('next', mode)
                self.assertTrue(stopped)
                control.assert_called_once_with('pause')

    def test_nothing_to_stop_and_asleep(self):
        stopped, control = self.partial('open email', 'awake', speaking=False)
        self.assertFalse(stopped); control.assert_not_called()
        stopped, control = self.partial('open email', 'sleep')
        self.assertFalse(stopped); control.assert_not_called()

    def test_command_here_asks_the_screen_not_a_word_list(self):
        with patch.object(app, 'SPEECH_STOP', SpeechStop()), patch.object(app, 'INPUT_MODE', 'mixed'), \
                patch.object(app, 'MAIN_MENU_INDEX', None), patch.object(app, 'account_setup', False):
            for words, mode in (('Office tools.', 'awake'), ('Web browser', 'awake'), ('reply', 'mailbox'),
                                ('Main menu.', 'document'), ('next', 'help'), ('stop talking', 'web'),
                                ('help with email', 'mailbox'), ('save draft', 'email_draft'), ('options', 'awake')):
                self.assertTrue(app.command_here(words, mode), (words, mode))
            for words, mode in (('The meeting is at noon.', 'document'), ('banana bread', 'awake'),
                                ('reply', 'awake'), ('zebra quilt', 'media'), ('anything at all', 'settings')):
                self.assertFalse(app.command_here(words, mode), (words, mode))
            # What Companion just told the user to say counts too.
            app.SPEECH_STOP.said('Thunderbird is installed and open. Close Thunderbird, then say add Thunderbird account to finish.')
            self.assertTrue(app.command_here('Add Thunderbird account.', 'awake'))

    def test_navigation_stops_even_when_companion_just_said_the_word(self):
        stopped, _ = self.partial('next', 'awake', said='Say next to hear more.')
        self.assertTrue(stopped)
        stopped, _ = self.partial('hear more', 'awake', said='Say next to hear more.')
        self.assertFalse(stopped)


if __name__ == '__main__':
    unittest.main()
