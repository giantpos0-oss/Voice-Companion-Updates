"""Verbosity options, Hints and help messages (Will, November 10, 2026).

Beginners hear "what to do next" tips. With the setting off, experienced users hear
just the result. A question and how to answer it, error recovery steps and what
just happened are always said.
"""
import ast
import json
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import companion
import hints
import settings_model
from hints import hint, spoken
from settings_model import DEFAULTS, SettingsSession, fields, prompt_text

HERE = Path(__file__).resolve().parent


class MarkTests(unittest.TestCase):
    def test_a_marked_message_equals_its_words_so_nothing_else_changes(self):
        message = 'Downloads.' + hint(' Press F1 twice for help.')
        self.assertEqual(message, 'Downloads. Press F1 twice for help.')
        self.assertIsInstance(message, str)
        self.assertEqual(spoken(message, True), 'Downloads. Press F1 twice for help.')
        self.assertEqual(spoken(message, False), 'Downloads.')

    def test_the_mark_survives_adding_text_on_either_side(self):
        message = 'Options closed. ' + ('Main menu.' + hint(' Say next or previous.')) + ' Two new messages.'
        self.assertEqual(spoken(message, False), 'Options closed. Main menu. Two new messages.')
        message = hint('Tip one.') + ' Result.' + hint(' Tip two.')
        self.assertEqual(spoken(message, False), 'Result.')
        built = 'A'
        built += hint(' tip.')
        self.assertEqual(spoken(built, False), 'A')

    def test_instead_words_replace_the_hint_when_off(self):
        message = 'Address manager.' + hint(' Say next contact.', instead=' I did not understand that.')
        self.assertEqual(spoken(message, True), 'Address manager. Say next contact.')
        self.assertEqual(spoken(message, False), 'Address manager. I did not understand that.')

    def test_plain_text_is_never_touched_even_when_it_looks_like_a_hint(self):
        # Read text (an email, a document, the guide) is plain: it is never shortened.
        for text in ('Press F1 twice for help.', 'To use another calendar, say change calendar.',
                     'Say next or previous, then that one to play.', ''):
            self.assertEqual(spoken(text, False), text)
        self.assertEqual(spoken(None, False), '')

    def test_a_lost_mark_says_the_hint_and_never_hides_words(self):
        message = 'Done.' + hint(' Say next.')
        self.assertEqual(spoken(f'Note: {message}', False), 'Note: Done. Say next.')
        self.assertEqual(spoken(message.replace('Done', 'Finished'), False), 'Finished. Say next.')

    def test_str_strip_and_join_keep_the_mark(self):
        message = '  Done.' + hint(' Say next.') + '  '
        for kept in (str(message), message.strip(), message.rstrip(), '[' + message.lstrip()):
            self.assertNotIn('Say next', spoken(kept, False), repr(kept))
        self.assertEqual(message.strip(), 'Done. Say next.')
        self.assertEqual(spoken(message.strip('. '), False), 'Done.')
        self.assertEqual(spoken(hints.join(' ', ['One.', 'Two.' + hint(' Tip.'), 'Three.']), False), 'One. Two. Three.')
        self.assertEqual(hints.join(', ', []), '')
        self.assertEqual(hints.join(' ', ['a', 'b']), 'a b')

    def test_empty_hints_and_copies(self):
        self.assertFalse(hints.has_hint(hint('')))
        self.assertFalse(hints.has_hint(hint('   ')))
        self.assertEqual(hints.with_hint('Saved.', ''), 'Saved.')
        message = hints.with_hint('Saved. ', 'Say read it to hear it.')
        self.assertEqual((message, spoken(message, False)), ('Saved. Say read it to hear it.', 'Saved.'))
        copy = pickle.loads(pickle.dumps(message))
        self.assertEqual(spoken(copy, False), 'Saved.')

    def test_the_saved_setting_reads_safely(self):
        for value, expected in ((True, True), (False, False), ('off', False), ('Off', False), ('on', True), (None, False)):
            self.assertEqual(hints.enabled({'speak_hints': value}), expected, value)
        self.assertTrue(hints.enabled({}))
        self.assertTrue(hints.enabled(None))


class VoiceCommandWordsTests(unittest.TestCase):
    def test_hints_on_and_off_with_messy_speech(self):
        for words, wanted in (('hints off', False), ('Hints, off.', False), ('turn hints off', False),
                              ('turn off hints', False), ('Turn off the hints.', False), ('disable hints', False),
                              ('hints and help messages off', False), ('help messages off', False),
                              ('set hints to off', False), ('hints on', True), ('Hints on.', True),
                              ('turn on hints', True), ('enable hints', True), ('switch hints on', True),
                              ('hints and help messages on', True)):
            self.assertIs(hints.toggle_request(words), wanted, words)

    def test_sentences_that_only_start_like_the_command_are_not_commands(self):
        for words in ('hints on the wall', 'hints', 'Hints about the party are off the table', 'help with hints',
                      'turn off the lights', 'help', '', None):
            self.assertIsNone(hints.toggle_request(words), words)


class OptionsSettingTests(unittest.TestCase):
    def test_it_is_in_verbosity_options_after_verbosity_and_on_by_default(self):
        keys = [f.key for f in fields('Verbosity options', {})]
        self.assertEqual(keys[:2], ['verbosity', 'speak_hints'])
        field = fields('Verbosity options', {})[1]
        self.assertEqual((field.label, field.kind), ('Hints and help messages', 'check'))
        self.assertIs(DEFAULTS['speak_hints'], True)
        self.assertEqual(hints.LABEL, field.label)
        self.assertEqual(hints.SETTING, field.key)

    def test_it_is_spoken_and_set_like_its_neighbours(self):
        session = SettingsSession({}, {})
        self.assertEqual(session.set('speak_hints', 'off'), 'Hints and help messages off')
        self.assertIs(session.values['speak_hints'], False)
        self.assertEqual(session.set('speak_hints', True), 'Hints and help messages on')
        self.assertEqual(session.voice_setting('Hints and help messages, off.'), ('speak_hints', 'off'))
        with self.assertRaises(ValueError):
            session.set('speak_hints', 'sometimes')

    def test_options_saves_it_with_the_other_settings(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(companion, 'APP', Path(folder)), \
                mock.patch.object(companion, 'PREFERENCES', dict(DEFAULTS)):
            companion.PREFERENCES['speak_hints'] = False
            companion.save_preferences()
            saved = json.loads((Path(folder) / 'preferences.json').read_text(encoding='utf-8'))
            self.assertIs(saved['speak_hints'], False)


class SpeakTests(unittest.TestCase):
    """The real speak(): only marked hints change."""
    def setUp(self):
        self.heard = []
        for name, value in (('PREFERENCES', dict(DEFAULTS)), ('TEXT_MODE', True), ('APP_WINDOW', None),
                            ('KEYBOARD_BATCH', False), ('TRANSCRIPT', __import__('speech_transcript').Transcript())):
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)
        for name in ('mail_log',):
            p = mock.patch.object(companion, name, side_effect=self.heard.append); p.start(); self.addCleanup(p.stop)
        p = mock.patch('builtins.print'); p.start(); self.addCleanup(p.stop)

    def say(self, text, on):
        self.heard.clear()
        companion.PREFERENCES['speak_hints'] = on
        companion.speak(text)
        return self.heard[-1] if self.heard else None

    def test_on_says_everything_and_off_drops_only_the_hint(self):
        message = 'Saved.' + hint(' Say read it to hear it.')
        self.assertEqual(self.say(message, True), 'Saved. Say read it to hear it.')
        self.assertEqual(self.say(message, False), 'Saved.')
        self.assertIs(type(self.heard[-1]), str)

    def test_off_never_shortens_plain_text(self):
        for text in ('Press F1 twice for help.', 'Dear Will, say next or previous to move. Thanks.'):
            self.assertEqual(self.say(text, False), text)

    def test_a_message_that_is_only_a_hint_says_nothing_when_off(self):
        self.assertIsNone(self.say(hint('Say next or previous.'), False))
        self.assertEqual(self.say(hint('Say next or previous.'), True), 'Say next or previous.')

    def test_a_yes_or_no_question_is_remembered_with_its_answer_words(self):
        question = 'Delete it? Say yes or no.' + hint(' Say help to learn more.')
        self.say(question, False)
        self.assertEqual(companion.LAST_YES_NO, 'Delete it? Say yes or no.')


class VoiceCommandTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.said = []
        for name, value in (('APP', Path(self.folder.name)), ('PREFERENCES', dict(DEFAULTS)), ('web_session', None)):
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(companion, 'speak', side_effect=self.said.append); p.start(); self.addCleanup(p.stop)

    def test_hints_off_and_on_from_any_screen_and_saved(self):
        for screen in ('awake', 'mailbox', 'media'):
            self.assertEqual(companion.handle('Hints, off.', screen), screen)
            self.assertIs(companion.PREFERENCES['speak_hints'], False)
            self.assertEqual(self.said[-1], 'Hints and help messages off. You hear just the result. '
                                            'To hear tips again, say hints on.')
            saved = json.loads((Path(self.folder.name) / 'preferences.json').read_text(encoding='utf-8'))
            self.assertIs(saved['speak_hints'], False)
            self.assertEqual(companion.handle('turn on hints', screen), screen)
            self.assertIs(companion.PREFERENCES['speak_hints'], True)
            self.assertEqual(self.said[-1], 'Hints and help messages on. You hear tips on what you can say next.')

    def test_a_settings_file_that_cannot_be_written_still_changes_it_now(self):
        with mock.patch.object(companion, 'save_preferences', side_effect=PermissionError(13, 'denied')):
            companion.handle('hints off', 'awake')
        self.assertIs(companion.PREFERENCES['speak_hints'], False)
        self.assertTrue(self.said[-1].endswith(companion.NOT_SAVED))


class RealMessageTests(unittest.TestCase):
    """Messages from several screens: what goes, and what always stays."""
    def test_main_menu(self):
        self.assertEqual(spoken(companion.MAIN_MENU_PROMPT, False), 'Main menu.')
        self.assertTrue(spoken(companion.MAIN_MENU_PROMPT, True).startswith('Main menu. What would you like to do? Say next'))
        self.assertEqual(spoken(prompt_text(companion.MAIN_MENU_PROMPT, 'high'), False), 'Main menu.')
        self.assertEqual(spoken(prompt_text(companion.MAIN_MENU_PROMPT, 'medium'), False), 'Main menu.')
        self.assertEqual(prompt_text(companion.MAIN_MENU_PROMPT, 'medium'),
                         'Main menu. What would you like to do? Say next or previous, and OK to open.')
        self.assertEqual(spoken(companion.MAIN_MENU_NOT_UNDERSTOOD, False),
                         'I did not understand that. You are on the main menu.')
        said = []
        with mock.patch.object(companion, 'speak', side_effect=said.append), \
                mock.patch.object(companion, 'VERBOSITY', 'high'), mock.patch.object(companion, 'MAIN_MENU_LEAD', 'Options closed.'):
            companion.announce_main_menu()
        self.assertEqual(spoken(said[-1], False), 'Options closed. Main menu.')

    def test_windows_brought_to_the_front(self):
        import own_chrome_window, window_hiding
        self.assertEqual(spoken(own_chrome_window.SHOWN_NOW, False),
                         'Your Chrome is in front. Press Alt+Tab to come back to Voice Companion.')
        self.assertTrue(own_chrome_window.SHOWN_NOW.endswith('To hide it again, say hide browser window.'))
        self.assertEqual(spoken(window_hiding.SHOWN, False),
                         'Thunderbird is in front now. Press Alt+Tab to come back to Voice Companion.')

    def test_radio_presets_and_station_choices(self):
        from media_hub import MediaHub
        with tempfile.TemporaryDirectory() as folder:
            hub = MediaHub(folder, player=mock.Mock(kind=None))
            (Path(folder) / 'radio-presets.json').write_text(json.dumps([{'name': 'WGN', 'url': 'http://a'},
                                                                         {'name': 'WQXR', 'url': 'http://b'}]))
            message = hub.command('list presets', section='radio')
            self.assertEqual(message, 'WGN (W), 1 of 2. Say next or previous, then that one to play. Say delete preset to remove it.')
            self.assertEqual(spoken(message, False), 'WGN (W), 1 of 2.')
            message = hub.command('next', section='radio')
            self.assertEqual((message, spoken(message, False)),
                             ('WQXR (W), 2 of 2. Say play preset or delete preset.', 'WQXR (W), 2 of 2.'))
            hub.preset_browsing = False
            hub.stations = [{'name': 'WGN'}, {'name': 'WGN Two'}]
            hub.station_choices, hub.station_choice_index = [0, 1], 0
            message = hub.command('next', section='radio')
            self.assertEqual((message, spoken(message, False)),
                             ('WGN Two (W), 2 of 2. Say that one to play it.', 'WGN Two (W), 2 of 2.'))

    def test_podcast_episodes(self):
        from media_hub import MediaHub
        with tempfile.TemporaryDirectory() as folder:
            hub = MediaHub(folder, player=mock.Mock(kind=None))
            hub.shows = [{'name': 'Vet Talk', 'feed': 'http://feed'}]
            with mock.patch.object(hub, '_feed_episodes', return_value=[{'title': 'One', 'url': 'http://1'}]):
                message = hub.open_podcast(1)
            self.assertEqual(spoken(message, False), 'Vet Talk. Found 1 episode. Episode 1: One.')
            self.assertTrue(spoken(message, True).endswith('Say next or previous to browse, that one to play, or download this episode.'))
            with mock.patch.object(hub, '_feed_episodes', side_effect=OSError):
                self.assertEqual(spoken(hub.open_podcast(1), False), 'The podcast feed is unavailable. Try again later.')

    def test_user_guide_topics(self):
        from onboard_help import HelpSession
        help = HelpSession(HERE / 'START HERE - Veteran.txt')
        message = help.start()
        self.assertTrue(spoken(message, True).endswith('Say help with followed by a topic name to jump there.'))
        self.assertTrue(spoken(message, False).startswith('User guide. '))
        self.assertTrue(spoken(message, False).endswith(', 1 of ' + str(len(help.topics)) + '.'), spoken(message, False))

    def test_what_always_stays(self):
        import account_picker, startup_speech
        # How to answer a list that did not understand you, and error recovery steps.
        for text in (account_picker.LIST_HINT, companion.COMMAND_FAILED, companion.MAIN_MENU_FIRST,
                     startup_speech.HOW_TO['off'], startup_speech.HOW_TO['failed']):
            self.assertFalse(hints.has_hint(text), text)
            self.assertEqual(spoken(text, False), text)

    def test_no_hint_hides_a_question_or_a_recovery_step(self):
        """Every hint(...) in the app, read from the source: none holds answer words or recovery steps."""
        banned = ('yes or no', 'say yes', 'say no', 'press y', 'try again', 'yes to', 'could not', 'did not work')
        found = 0
        for path in HERE.glob('*.py'):
            if path.name.startswith('test_') or path.name == 'hints.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, 'id', '') in ('hint', 'marked_hint', 'with_hint'):
                    found += 1
                    words = ' '.join(c.value for arg in node.args for c in ast.walk(arg)
                                     if isinstance(c, ast.Constant) and isinstance(c.value, str)).casefold()
                    for word in banned:
                        self.assertNotIn(word, words, f'{path.name}:{node.lineno}')
        self.assertGreaterEqual(found, 20)


class SpeechPathTests(unittest.TestCase):
    """A marked message through every path that speaks, with hints off: the hint is gone everywhere."""
    MESSAGE = 'Saved.' + hint(' Say read it to hear it.')

    def setUp(self):
        self.out = {}
        record = lambda name: (lambda text, *a, **k: self.out.setdefault(name, []).append(str.__str__(text)))
        class Voice:
            problem = None
            enabled = True
            def __init__(self, name): self.speak = record(name)
        self.voices = {name: Voice(name) for name in ('keyboard', 'espeak', 'ai')}
        window = mock.Mock(); window.show.side_effect = record('window')
        transcript = mock.Mock(); transcript.said.side_effect = record('transcript')
        for name, value in (('PREFERENCES', dict(DEFAULTS, speak_hints=False)), ('TEXT_MODE', False), ('APP_WINDOW', window),
                            ('TRANSCRIPT', transcript), ('KEYBOARD_BATCH', False), ('KEYBOARD_NAVIGATION', False),
                            ('KEYBOARD_SPEECH', None), ('ESPEAK_SPEECH', None), ('AI_SPEECH', None), ('web_session', None),
                            ('VERBOSITY', 'high'), ('voice', None)):
            p = mock.patch.object(companion, name, value, create=(name == 'voice')); p.start(); self.addCleanup(p.stop)
        for name, effect in (('mail_log', record('mail log')), ('update_audio_ducking', None),
                             ('sapi_speak', lambda voice, text, *a, **k: record('sapi')(text)), ('sync_app_context', None)):
            p = mock.patch.object(companion, name, side_effect=effect); p.start(); self.addCleanup(p.stop)

    def check(self, *outputs):
        for name in outputs:
            self.assertTrue(self.out.get(name), (name, self.out))
            for text in self.out[name]:
                self.assertEqual(text, 'Saved.', (name, self.out))
        self.out.clear()

    def test_each_synthesizer_window_transcript_and_log(self):
        companion.speak(self.MESSAGE); self.check('sapi', 'window', 'transcript', 'mail log')
        with mock.patch.object(companion, 'ESPEAK_SPEECH', self.voices['espeak']):
            companion.speak(self.MESSAGE); self.check('espeak', 'window', 'transcript')
        with mock.patch.object(companion, 'AI_SPEECH', self.voices['ai']):
            companion.speak(self.MESSAGE); self.check('ai')
        with mock.patch.object(companion, 'KEYBOARD_SPEECH', self.voices['keyboard']), \
                mock.patch.object(companion, 'KEYBOARD_NAVIGATION', True):
            companion.speak(self.MESSAGE); self.check('keyboard', 'window')
            companion.speak_keyboard_feedback(self.MESSAGE); self.check('keyboard', 'window', 'transcript')

    def test_status_web_dictation_and_prompt_paths(self):
        companion.speak_status(self.MESSAGE); self.check('sapi')
        companion.speak_web_result(self.MESSAGE, 0); self.check('sapi')
        with mock.patch.object(companion, 'web_session', mock.Mock(page_revision=2, last_dictated_text=None,
                                                                    backend=mock.Mock(last_dictated_text=None))):
            companion.speak_web_result(self.MESSAGE, 1); self.check('sapi')
        companion.dictation_feedback(self.MESSAGE); self.check('sapi')
        companion.mail_progress(self.MESSAGE); self.check('sapi')
        for level in ('high', 'medium', 'low'):
            with mock.patch.object(companion, 'VERBOSITY', level):
                companion.speak_prompt(self.MESSAGE); self.check('sapi')

    def test_a_batched_keyboard_message_is_kept_without_its_hint(self):
        with mock.patch.object(companion, 'KEYBOARD_BATCH', True), mock.patch.object(companion, 'KEYBOARD_BATCH_TEXT', None):
            companion.speak(self.MESSAGE)
            self.assertEqual(companion.KEYBOARD_BATCH_TEXT, 'Saved.')
            self.assertFalse(hints.has_hint(companion.KEYBOARD_BATCH_TEXT))

    def test_the_window_key_feedback_and_its_transcript(self):
        import app_window, speech_transcript
        said = []
        window = mock.Mock(keyboard_output=mock.Mock(problem=None, speak=said.append))
        window.show.side_effect = said.append
        with mock.patch.object(speech_transcript.TRANSCRIPT, 'said', side_effect=said.append):
            app_window.CompanionWindow.feedback(window, self.MESSAGE)
        self.assertEqual([str.__str__(x) for x in said], ['Saved.'] * 3)
        said.clear()
        app_window.CompanionWindow.feedback(window, hint('Only a tip.'))
        self.assertEqual(said, [])

    def test_startup_and_account_removal_join_their_parts_and_keep_marks(self):
        import startup_speech
        text = startup_speech.announcement('1.0', 'on', notices=['  Notice.' + hint(' Tip.') + ' '])
        self.assertIn('Tip.', text)
        self.assertNotIn('Tip.', spoken(text, False))
        self.assertIn('The microphone is on.', spoken(text, False))
        self.assertNotIn('Say wake up', spoken(text, False))
        self.assertIn('Say wake up', spoken(text, True))
        self.assertIn('Press F1 twice for help.', spoken(startup_speech.announcement('1.0', 'off'), False))


class VerbosityTests(unittest.TestCase):
    """Verbosity medium and low shorten only marked hints. Before, they cut everything after " Say "."""
    WRONGLY_CUT = (
        'The user guide could not open. Say help to try again.',
        'No email account is connected. Say add account.',
        'I could not find that document. Say list documents to hear the names.',
        'Commands only is on. Say normal mode or dictation mode to write.',
        'I could not open that draft. Say list email drafts to hear the names.',
        'Website request canceled. Say open website followed by the address to try again.',
        'Chrome is not set up yet. Set it up now? Say yes or no, or press Y or N.',
        'Delete preset WGN? Say yes or no.',
        'Voice name was not unique. Say list voices and try the full name.',
    )

    def test_recovery_steps_and_answer_words_are_never_cut(self):
        for level in ('medium', 'low'):
            for text in self.WRONGLY_CUT:
                self.assertEqual(prompt_text(text, level), text, (level, text))

    def test_the_real_speak_prompt_path_says_them_whole(self):
        said = []
        with mock.patch.object(companion, 'speak', side_effect=said.append):
            for level in ('medium', 'low'):
                with mock.patch.object(companion, 'VERBOSITY', level):
                    companion.speak_prompt('The user guide could not open. Say help to try again.')
                    self.assertEqual(said[-1], 'The user guide could not open. Say help to try again.')

    def test_marked_hints_get_shorter_and_stay_marked(self):
        message = 'Dictation started.' + hint(' Speak naturally. Say save note when finished. Say list notes to open a saved note.')
        self.assertEqual(prompt_text(message, 'high'), message)
        self.assertEqual(prompt_text(message, 'medium'), 'Dictation started. Speak naturally.')
        self.assertEqual(spoken(prompt_text(message, 'medium'), False), 'Dictation started.')
        self.assertEqual(prompt_text(message, 'low'), 'Dictation started.')
        fallback = 'Downloads.' + hint(' Say pause download. Press F1 twice for help.', instead=' I did not understand that.')
        self.assertEqual(prompt_text(fallback, 'low'), 'Downloads. I did not understand that.')
        self.assertEqual(spoken(prompt_text(fallback, 'medium'), False), 'Downloads. I did not understand that.')

    def test_main_menu_still_shortens(self):
        self.assertEqual(prompt_text(companion.MAIN_MENU_PROMPT, 'low'), 'Main menu.')
        self.assertTrue(prompt_text(companion.MAIN_MENU_PROMPT, 'medium').startswith('Main menu. What would you like to do?'))


class MoreRealMessageTests(unittest.TestCase):
    def test_thunderbird_account_ready(self):
        import thunderbird_accounts as words
        message = words.ready_message(['sam@gmail.com'], 'sam@gmail.com')
        self.assertTrue(message.endswith('is connected and selected. Say check email to open it.'), message)
        self.assertTrue(spoken(message, False).endswith('is connected and selected.'))
        message = words.ready_message(['a@gmail.com', 'b@gmail.com'], None)
        self.assertEqual(spoken(message, False), 'Thunderbird finished adding a@gmail.com and b@gmail.com. They are connected.')
        self.assertEqual(spoken(words.also_connected_message(['a@gmail.com']), False),
                         'Thunderbird also has a@gmail.com. It is connected to Voice Companion now.')

    def test_removed_accounts_keep_what_happened(self):
        import account_picker
        result = mock.Mock(removed=[('gmail', 'sam@gmail.com')], selected=None, changed_selection=False,
                           remaining=[('yahoo', 'x@yahoo.com')])
        message = account_picker.retired_message(result)
        self.assertIn('again, say add account and choose Thunderbird.', message)
        off = spoken(message, False)
        self.assertIn('removed from Voice Companion.', off)
        self.assertIn('Your drafts and contacts are kept.', off)
        self.assertNotIn('say add account', off)

    def test_reading_on_in_long_text(self):
        from reading_navigation import ReadingCursor
        cursor = ReadingCursor(); cursor.set_text('word ' * 2000, reset=True)
        piece = cursor.read()
        self.assertTrue(piece.endswith(' Say continue reading for more.'))
        self.assertFalse(spoken(piece, False).endswith('more.'))
        self.assertTrue(spoken(piece, False).endswith('word'))

    def test_web_text_entry_and_document_reader_link(self):
        import document_reader, web_assistant
        self.assertEqual(spoken(web_assistant.SKIP_AD_READY, False), 'Skip ad button ready.')
        self.assertEqual(spoken(web_assistant.WINDOW_BACK, False), ' It is in front. Press Alt+Tab to come back to Voice Companion.'.strip())

    def test_document_undo_tips(self):
        from document_editor import VoiceDocument, Paragraph
        with tempfile.TemporaryDirectory() as folder:
            doc = VoiceDocument(Path(folder)); doc.paragraphs = [Paragraph('Hello there.'), Paragraph('Second.')]
            message = doc.process('delete paragraph')
            self.assertIn('Say undo to restore it.', message, message)
            self.assertNotIn('Say undo', spoken(message, False))
            self.assertTrue(spoken(message, False).startswith('Deleted paragraph'), message)


class ScreenFallbackTests(unittest.TestCase):
    """A misheard word on a screen: with hints off you still hear that it was not understood."""
    def test_downloads_attachments_and_youtube_fallbacks(self):
        import attachment_screen, download_screen, youtube_screen
        for module in (attachment_screen, download_screen, youtube_screen):
            source = Path(module.__file__).read_text(encoding='utf-8')
            self.assertIn("instead=' I did not understand that.'", source, module.__name__)


from test_contacts_screen import CompanionHarness  # noqa: E402
from test_calendar_screen import CalendarHarness  # noqa: E402


class ContactsHintTests(CompanionHarness):
    def test_unknown_words_with_hints_on_and_off(self):
        mode = self.say('Contacts', 'awake')
        app = companion
        app.handle('zebra quantum lantern', mode)
        self.assertEqual(spoken(self.speech.call_args.args[0], True),
                         'Address manager. Say next contact, find and a name, email contact, add contact, edit contact, '
                         'or delete contact. Press F1 twice for help, or Escape for the main menu.')
        self.assertEqual(spoken(self.speech.call_args.args[0], False), 'Address manager. I did not understand that.')


class CalendarHintTests(CalendarHarness):
    def test_the_save_question_keeps_its_answer_words(self):
        mode = self.press('Ctrl+N', self.open())
        mode = companion.handle('tomorrow at 3 PM', mode)
        mode = companion.handle('Dentist', mode)
        question = self.speech.call_args.args[0]
        self.assertEqual(spoken(question, True), 'Add Dentist, Tomorrow, Tuesday, October 27, three PM to four PM, to the '
                                                 'me@gmail.com calendar? Say Yes to save or No to cancel. '
                                                 'To use another calendar, say change calendar.')
        self.assertEqual(spoken(question, False), 'Add Dentist, Tomorrow, Tuesday, October 27, three PM to four PM, to the '
                                                  'me@gmail.com calendar? Say Yes to save or No to cancel.')

    def test_unknown_words(self):
        mode = self.open()
        companion.handle('zebra quantum lantern', mode)
        self.assertEqual(spoken(self.speech.call_args.args[0], False), 'Schedule manager. I did not understand that.')


if __name__ == '__main__':
    unittest.main()
