"""The AI assistant in Companion's screens (Will, November 16, 2026): keys, Alt menu items and
voice give the same results everywhere. Only the AI service is faked; the document, the
note, the keys and the voice commands are Companion's own."""
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import companion
import ai_assistant as ai
from document_editor import Paragraph, VoiceDocument


class Screen(SimpleNamespace):
    """A stand-in for an email or web session: anything not given is None."""
    def __getattr__(self, name):
        return None


class Service:
    def __init__(self):
        self.asked = []
        self.answers = {'summarise': {'ok': True, 'text': 'Lunch moved to Friday.'},
                        'simplify': {'ok': True, 'text': 'Plain words.'},
                        'rewrite': {'ok': True, 'text': 'Dear team, I saw the dog.'},
                        'check_errors': {'ok': True, 'corrections': [{'original': 'teh', 'replacement': 'the', 'reason': 'Spelling'},
                                                                    {'original': 'dgo', 'replacement': 'dog', 'reason': 'Typing'}]},
                        'describe_image': {'ok': True, 'text': 'A dog on a beach.'},
                        'help_question': {'ok': True, 'text': 'Press R to reply.'}}

    def __call__(self, task, payload):
        self.asked.append((task, payload))
        return self.answers[task]


class AIScreenTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.said = []
        self.service = Service()
        prefs = dict(companion.PREFERENCES, ai_features=True, ai_assistant_consent=True)
        for name, value in dict(TEXT_MODE=True, APP=self.folder, APP_WINDOW=None, MEDIA_HUB=None, INPUT_MODE='mixed',
                                document=None, email_draft=None, mail_session=None, pending_send=None, help_session=None,
                                web_session=None, FILE_READER=None, FILE_MANAGER=None, SLEEP_RETURN_MODE='awake',
                                AI_SESSION=None, PREFERENCES=prefs).items():
            p = patch.object(companion, name, value, create=True); p.start(); self.addCleanup(p.stop)
        for name in ('speak', 'speak_prompt', 'dictation_feedback', 'speak_status'):
            p = patch.object(companion, name, lambda text, *a, **k: self.said.append(str(text))); p.start(); self.addCleanup(p.stop)
        for target, value in (('ai_request', self.service), ('save_speech_settings', lambda *a: None)):
            p = patch.object(companion, target, value); p.start(); self.addCleanup(p.stop)
        p = patch('app_settings.save_preferences', lambda *a: None); p.start(); self.addCleanup(p.stop)

    def key(self, key, mode):
        request = companion.navigation_key(key, mode)
        return companion.handle_keyboard(request, mode) if request else mode

    def answer(self):
        session = companion.AI_SESSION
        for _ in range(300):
            if session.job is None or session.job.done.is_set():
                break
            time.sleep(0.01)
        companion.ai_poll()
        return self.said[-1]

    def last(self):
        return self.said[-1]

    def document(self, text):
        doc = VoiceDocument(self.folder / 'Docs'); doc.dictating = True
        doc.paragraphs = [Paragraph(text)]
        companion.document = doc
        return doc


class WritingAssistantTests(AIScreenTestCase):
    def test_control_shift_q_check_for_errors_keep_and_skip_then_undo(self):
        doc = self.document('I saw teh dgo.')
        mode = self.key('Ctrl+Shift+Q', 'document')
        self.assertEqual(mode, 'ai_assistant')
        self.assertEqual(self.last(), 'AI assistant, for this document. Check for errors, 1 of 7.')
        mode = self.key('Enter', mode)
        self.assertEqual(self.last(), ai.WORKING)
        self.assertTrue(self.answer().endswith('Change "teh" to "the". Spelling. 1 of 2.'))
        mode = self.key('Enter', mode)          # keep
        self.assertEqual(doc.paragraphs[0].text, 'I saw the dgo.')
        mode = self.key('Delete', mode)         # skip
        self.assertTrue(self.last().startswith('Skipped. Done. You kept 1.'), self.last())
        self.assertEqual(doc.paragraphs[0].text, 'I saw the dgo.')
        mode = self.key('Escape', mode)
        self.assertEqual((mode, self.last()), ('document', 'AI assistant closed.'))
        companion.handle('undo', 'document')
        self.assertEqual(doc.paragraphs[0].text, 'I saw teh dgo.', 'a kept correction is one undo step')

    def test_voice_and_keys_do_the_same_rewrite(self):
        doc = self.document('i saw teh dog')
        mode = companion.handle('Make it more professional.', 'document')
        self.assertEqual(mode, 'ai_assistant')
        self.assertTrue(self.answer().startswith('Dear team, I saw the dog.'))
        self.assertEqual(self.service.asked[0], ('rewrite', {'text': 'i saw teh dog', 'tone': 'professional'}))
        mode = companion.handle('use it', mode)
        self.assertEqual(doc.paragraphs[0].text, 'Dear team, I saw the dog.')
        self.assertEqual(self.last(), 'Done. Say undo to put your own text back.')
        # The same through the menu with keys: Down to the choice, Enter, Enter to keep.
        doc.paragraphs = [Paragraph('i saw teh dog')]
        companion.ai_refresh_source()
        for key in ('Home', 'Down', 'Down'):
            mode = self.key(key, mode)
        self.assertEqual(self.last(), 'More professional, 3 of 7.')
        mode = self.key('Enter', mode); self.answer()
        mode = self.key('Enter', mode)
        self.assertEqual(doc.paragraphs[0].text, 'Dear team, I saw the dog.')

    def test_only_the_selected_text_is_rewritten(self):
        from document_editor import TextSelection
        doc = self.document('Keep this. i saw teh dog')
        doc.selection = TextSelection(0, 11, 0, len('Keep this. i saw teh dog'))
        mode = self.key('Ctrl+Shift+Q', 'document')
        self.assertTrue(self.last().startswith('AI assistant, for the selected text.'))
        mode = companion.handle('make it more professional', mode); self.answer()
        companion.handle('use it', mode)
        self.assertEqual(doc.paragraphs[0].text, 'Keep this. Dear team, I saw the dog.')

    def test_a_dictated_word_stays_text_in_a_document(self):
        doc = self.document('')
        self.assertEqual(companion.handle('Summary', 'document'), 'document')
        self.assertIsNone(companion.AI_SESSION)
        self.assertIn('Summary', doc.paragraphs[-1].text)

    def test_sentences_that_start_like_a_choice_stay_text(self):
        # Writing comes first: "Check this." or "Describe it." in a letter is text, not a command.
        for said in ('Check this.', 'Describe it.', 'Simplify it.', 'Plain language.', 'Give me a summary.', 'More professional.'):
            with self.subTest(said=said):
                doc = self.document('')
                self.assertEqual(companion.handle(said, 'document'), 'document')
                self.assertIsNone(companion.AI_SESSION)
                self.assertIn(said.rstrip('.'), doc.paragraphs[-1].text)

    def test_a_whole_command_with_a_period_still_works(self):
        self.document('I saw teh dgo.')
        self.assertEqual(companion.handle('Check for errors.', 'document'), 'ai_assistant')

    def test_a_note(self):
        companion.note_buffer[:] = ['I saw teh dgo.']
        self.addCleanup(companion.note_buffer.clear)
        mode = companion.handle('check for errors', 'note'); self.answer()
        companion.handle('keep all', mode)
        self.assertEqual(' '.join(companion.note_buffer), 'I saw the dog.')


class ReadingAssistantTests(AIScreenTestCase):
    def test_summarise_an_open_email_by_voice_and_read_it_line_by_line(self):
        companion.mail_session = Screen(view='message', body_text='Hello all. Lunch is now on Friday.\nBring food.')
        mode = companion.handle('Summarize this email.', 'mailbox')
        self.assertEqual(self.answer(), 'Lunch moved to Friday.')
        self.assertEqual(self.service.asked[0], ('summarise', {'text': 'Hello all. Lunch is now on Friday.\nBring food.'}))
        mode = self.key('Escape', mode)
        self.assertEqual(self.last(), 'Summarise, 1 of 2.')
        mode = self.key('Escape', mode)
        self.assertEqual(mode, 'mailbox')

    def test_the_email_list_says_to_open_an_email(self):
        companion.mail_session = Screen(view='list', body_text='')
        self.assertEqual(self.key('Ctrl+Shift+Q', 'mailbox'), 'mailbox')
        self.assertEqual(self.last(), 'Open an email first, then press Control+Shift+Q.')

    def test_a_web_page(self):
        companion.web_session = Screen(snapshot={'text': 'A long article.'})
        with patch.object(companion, 'web_writing_field', lambda: False):
            mode = companion.handle('simplify this page', 'web')
        self.assertEqual(self.answer(), 'Plain words.')


class ImageAndHelpTests(AIScreenTestCase):
    def test_describe_a_picture_in_file_manager(self):
        picture = self.folder / 'beach.jpg'; picture.write_bytes(b'\xff\xd8 picture')
        companion.FILE_MANAGER = SimpleNamespace(current=lambda: SimpleNamespace(path=str(picture)))
        mode = self.key('Ctrl+Shift+Q', 'files')
        self.assertEqual(self.last(), 'AI assistant, for beach.jpg. Describe the image, 1 of 2.')
        mode = self.key('Enter', mode)
        self.assertEqual(self.answer(), 'A dog on a beach.')
        self.assertTrue(self.service.asked[0][1]['image'].startswith('data:image/jpeg;base64,'))

    def test_the_file_manager_menu_picture_group(self):
        import file_manager
        self.assertIn('picture', file_manager.GROUPS)
        labels = [label for label, _, _ in file_manager.GROUPS['picture'][1]]
        self.assertEqual(labels, ['AI assistant', 'Describe the image', 'Ask about the image'])
        # Enter on Describe the image in that group hands it to the app, which describes the picture.
        picture = self.folder / 'cat.png'; picture.write_bytes(b'\x89PNG picture')
        companion.FILE_MANAGER = SimpleNamespace(current=lambda: SimpleNamespace(path=str(picture)), busy=False, pending=None,
                                                 items=[1], command=lambda text: '__ai__:describe the image')
        mode = companion.handle('enter', 'files', typed=True)
        self.assertEqual(mode, 'ai_assistant')
        self.assertEqual(self.answer(), 'A dog on a beach.')

    def test_a_file_that_is_not_a_picture(self):
        companion.FILE_MANAGER = SimpleNamespace(current=lambda: SimpleNamespace(path=str(self.folder / 'notes.txt')))
        self.assertEqual(self.key('Ctrl+Shift+Q', 'files'), 'files')
        self.assertTrue(self.last().startswith('Move to a picture first.'))

    def test_ask_a_question_in_help(self):
        mode = companion.handle('ask a question', 'help')
        self.assertEqual(self.last(), 'Type or say your question about Voice Companion, then press Enter.')
        mode = companion.handle('How do I reply to an email?', mode)
        self.assertEqual(self.answer(), 'Press R to reply.')
        self.assertIn('reply', self.service.asked[0][1]['guide'].lower())


class ConsentAndSettingTests(AIScreenTestCase):
    def test_first_use_asks_and_no_closes_it(self):
        companion.PREFERENCES['ai_assistant_consent'] = False
        companion.mail_session = Screen(view='message', body_text='Hi.')
        mode = self.key('Ctrl+Shift+Q', 'mailbox')
        self.assertEqual(self.last(), ai.CONSENT)
        self.assertTrue(companion.yes_no_open(mode))
        mode = self.key('N', mode)
        self.assertEqual((mode, self.last()), ('mailbox', 'The AI assistant was not used.'))
        self.assertEqual(self.service.asked, [])

    def test_yes_remembers_and_carries_on_with_the_choice(self):
        companion.PREFERENCES['ai_assistant_consent'] = False
        companion.mail_session = Screen(view='message', body_text='Hi.')
        mode = companion.handle('summarise this', 'mailbox')
        mode = self.key('Y', mode)
        self.assertEqual(self.answer(), 'Lunch moved to Friday.')
        self.assertTrue(companion.PREFERENCES['ai_assistant_consent'])

    def test_ai_features_off(self):
        companion.PREFERENCES['ai_features'] = False
        self.document('Text.')
        self.assertEqual(self.key('Ctrl+Shift+Q', 'document'), 'document')
        self.assertEqual(self.last(), ai.NOT_ON)

    def test_letters_and_window_context(self):
        self.document('Text.')
        mode = self.key('Ctrl+Shift+Q', 'document')
        self.assertTrue(companion.app_context(mode)['menu_letters'])
        self.key('Letter:s', mode)
        self.assertEqual(self.last(), 'Shorter, 5 of 7.')
        self.key('Letter:s', mode)
        self.assertEqual(self.last(), 'Summarise, 6 of 7.')
        self.key('Letter:c', mode)
        self.assertEqual(self.last(), 'Check for errors, 1 of 7.')


if __name__ == '__main__':
    unittest.main()
