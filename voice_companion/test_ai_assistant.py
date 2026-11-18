"""The AI assistant (Will, November 16, 2026): Reading Assistant, Writing Assistant,
Describe Image and Ask a Question. The AI service is faked at its boundary: the request
function gets the task and payload and returns what the service would."""
import io
import json
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path

import ai_assistant as ai


def wait(session):
    for _ in range(200):
        if session.job is None or session.job.done.is_set():
            break
        time.sleep(0.01)
    return session.poll()


class Service:
    def __init__(self, answers=None, error=None):
        self.answers = answers or {}
        self.error = error
        self.asked = []

    def __call__(self, task, payload):
        self.asked.append((task, payload))
        if self.error:
            raise ai.AssistantError(self.error)
        return self.answers.get(task, {'ok': True, 'text': 'Answer for ' + task})


class Document:
    def __init__(self, text):
        self.text = text

    def apply(self, new):
        self.text = new
        return 'Done. Say undo to put your own text back.'

    def fix(self, original, replacement):
        if original not in self.text:
            return False
        self.text = self.text.replace(original, replacement, 1)


def writing(text='I saw teh dog yesterdy.', service=None):
    document = Document(text)
    service = service or Service()
    source = {'kind': 'write', 'label': 'this document', 'text': document.text, 'apply': document.apply, 'fix': document.fix}
    return ai.Session(source, 'document', service), document, service


class MenuTests(unittest.TestCase):
    def test_each_place_offers_what_fits_it(self):
        session, _, _ = writing()
        self.assertEqual(session.opening(), 'AI assistant, for this document. Check for errors, 1 of 7.')
        reading = ai.Session({'kind': 'read', 'label': 'this email', 'text': 'Hi'}, 'mailbox', Service())
        self.assertEqual(reading.choices, ['Summarise', 'Simplify'])
        self.assertEqual(ai.Session({'kind': 'image', 'image_path': 'x.png'}, 'files', Service()).choices,
                         ['Describe the image', 'Ask about the image'])

    def test_arrows_home_end_and_letters(self):
        session, _, _ = writing()
        self.assertEqual(session.move(1), 'Friendlier, 2 of 7.')
        self.assertEqual(session.move(to='last'), 'Simplify, 7 of 7.')
        self.assertEqual(session.move(1), 'Simplify, 7 of 7.')
        self.assertEqual(session.letter('s'), 'Shorter, 5 of 7.')
        self.assertEqual(session.letter('s'), 'Summarise, 6 of 7.')
        self.assertEqual(session.letter('z'), 'No choice starts with Z.')

    def test_spoken_choices_tolerate_speech(self):
        self.assertEqual(ai.spoken_choice('Summarize this email.'), ai.SUMMARISE)
        self.assertEqual(ai.spoken_choice('Make it more professional.'), ai.PROFESSIONAL)
        self.assertEqual(ai.spoken_choice('Check for errors', 'read'), None, 'not offered while reading')
        self.assertTrue(ai.opens_assistant('AI assistant.'))


class ReadingTests(unittest.TestCase):
    def test_summarise_says_the_summary_and_escape_goes_back_to_the_menu(self):
        service = Service({'summarise': {'ok': True, 'text': 'The meeting moved to Friday.'}})
        session = ai.Session({'kind': 'read', 'label': 'this email', 'text': 'Long email text.'}, 'mailbox', service)
        self.assertEqual(session.choose(), ai.WORKING)
        self.assertEqual(wait(session), 'The meeting moved to Friday.')
        self.assertEqual(service.asked, [('summarise', {'text': 'Long email text.'})])
        self.assertEqual(session.level, 'result')
        self.assertEqual(session.back(), 'Summarise, 1 of 2.')
        self.assertIsNone(session.back(), 'Escape from the menu leaves the assistant')

    def test_problems_are_said_plainly(self):
        session = ai.Session({'kind': 'read', 'text': 'x'}, 'mailbox', Service(error='Voice Companion could not reach the AI assistant.'))
        session.choose(ai.SIMPLIFY)
        self.assertEqual(wait(session), 'Voice Companion could not reach the AI assistant.')
        self.assertEqual(session.level, 'menu')

    def test_nothing_to_read(self):
        session = ai.Session({'kind': 'read', 'text': '  '}, 'mailbox', Service())
        self.assertEqual(session.choose(), ai.NO_TEXT)

    def test_escape_while_working_stops_and_the_late_answer_is_ignored(self):
        def slow(task, payload):
            time.sleep(0.2); return {'ok': True, 'text': 'late'}
        session = ai.Session({'kind': 'read', 'text': 'x'}, 'mailbox', slow)
        session.choose()
        self.assertEqual(session.back(), ai.STOPPED)
        time.sleep(0.3)
        self.assertIsNone(session.poll())

    def test_a_slow_answer_says_still_working(self):
        now = [100.0]
        gate = __import__('threading').Event()
        session = ai.Session({'kind': 'read', 'text': 'x'}, 'mailbox', lambda t, p: gate.wait(5) and {'ok': True, 'text': 'y'},
                             clock=lambda: now[0])
        session.choose()
        self.assertIsNone(session.poll())
        now[0] += ai.STILL_WORKING_SECONDS
        self.assertEqual(session.poll(), ai.STILL)
        gate.set(); session.job.done.wait(2)
        self.assertEqual(session.poll(), 'y')


class WritingTests(unittest.TestCase):
    def test_rewrite_is_kept_only_when_asked(self):
        service = Service({'rewrite': {'ok': True, 'text': 'Dear Sir, I saw the dog.'}})
        session, document, _ = writing(service=service)
        session.choose(ai.PROFESSIONAL)
        self.assertTrue(wait(session).startswith('Dear Sir, I saw the dog. ... Press Enter to use this'))
        self.assertEqual(service.asked[0], ('rewrite', {'text': 'I saw teh dog yesterdy.', 'tone': 'professional'}))
        self.assertEqual(session.back(), 'Kept your own text. More professional, 3 of 7.')
        self.assertEqual(document.text, 'I saw teh dog yesterdy.')
        session.choose(ai.PROFESSIONAL); wait(session)
        self.assertEqual(session.keep_result(), 'Done. Say undo to put your own text back.')
        self.assertEqual(document.text, 'Dear Sir, I saw the dog.')

    def test_corrections_are_kept_or_skipped_one_at_a_time(self):
        answer = {'ok': True, 'corrections': [{'original': 'teh', 'replacement': 'the', 'reason': 'Spelling'},
                                              {'original': 'yesterdy', 'replacement': 'yesterday', 'reason': 'Spelling.'},
                                              {'original': 'not there', 'replacement': 'x', 'reason': 'made up'}]}
        session, document, _ = writing(service=Service({'check_errors': answer}))
        session.choose(ai.CHECK)
        said = wait(session)
        self.assertTrue(said.startswith('Found 2 corrections.'), said)
        self.assertTrue(said.endswith('Change "teh" to "the". Spelling. 1 of 2.'), said)
        self.assertEqual(session.move(1), 'Change "yesterdy" to "yesterday". Spelling. 2 of 2.')
        self.assertEqual(session.skip_correction(), 'Skipped. Change "teh" to "the". Spelling. 1 of 1.')
        self.assertEqual(session.keep_correction(), 'Kept. Done. You kept 1. Check for errors, 1 of 7.')
        self.assertEqual(document.text, 'I saw the dog yesterdy.')

    def test_keep_all(self):
        answer = {'ok': True, 'corrections': [{'original': 'teh', 'replacement': 'the'},
                                              {'original': 'yesterdy', 'replacement': 'yesterday'}]}
        session, document, _ = writing(service=Service({'check_errors': answer}))
        session.choose(ai.CHECK); wait(session)
        self.assertEqual(session.keep_all(), 'Kept 2 corrections. Say undo to take them back one at a time.')
        self.assertEqual(document.text, 'I saw the dog yesterday.')

    def test_no_mistakes(self):
        session, _, _ = writing('All good.', Service({'check_errors': {'ok': True, 'corrections': []}}))
        session.choose(ai.CHECK)
        self.assertEqual(wait(session), 'No mistakes found. Check for errors, 1 of 7.')


class ImageAndHelpTests(unittest.TestCase):
    def test_describe_and_ask_about_a_picture(self):
        folder = Path(tempfile.mkdtemp()); picture = folder / 'card.png'; picture.write_bytes(b'\x89PNG data')
        service = Service({'describe_image': {'ok': True, 'text': 'A handwritten birthday card.'}})
        session = ai.Session({'kind': 'image', 'label': 'card.png', 'image_path': picture}, 'files', service)
        session.choose()
        self.assertEqual(wait(session), 'A handwritten birthday card.')
        self.assertTrue(service.asked[0][1]['image'].startswith('data:image/png;base64,'))
        session.back()
        self.assertEqual(session.choose(ai.ASK_IMAGE), 'Type or say your question about the image, then press Enter.')
        session.ask('Who signed it?'); wait(session)
        self.assertEqual(service.asked[1][1]['question'], 'Who signed it?')

    def test_a_file_that_is_not_a_picture(self):
        session = ai.Session({'kind': 'image', 'image_path': 'notes.txt'}, 'files', Service())
        session.choose()
        self.assertIn('not a picture', wait(session))

    def test_ask_a_question_sends_the_matching_guide_sections(self):
        guide = '1 Getting started\nPress F1.\n25.4 Audio ducking\nLower other sound while Companion talks.\n30 Email\nPress R to reply.'
        service = Service({'help_question': {'ok': True, 'text': 'Press R.'}})
        session = ai.Session({'kind': 'help', 'guide': lambda q: ai.guide_sections(guide, q)}, 'help', service)
        session.choose(); session.ask('How do I reply to an email?')
        self.assertEqual(wait(session), 'Press R.')
        self.assertIn('30 Email', service.asked[0][1]['guide'])
        self.assertNotIn('Audio ducking', service.asked[0][1]['guide'])


class ServiceRequestTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def reply(self, body, status=200):
        def opener(request, timeout):
            self.sent = request
            if status != 200:
                raise urllib.error.HTTPError(request.full_url, status, 'x', {}, io.BytesIO(json.dumps(body).encode()))
            return io.BytesIO(json.dumps(body).encode())
        return opener

    def test_a_good_answer_and_the_install_id(self):
        answer = ai.service_request(self.folder, '0.2.214', 'summarise', {'text': 'x'}, opener=self.reply({'ok': True, 'text': 'y'}))
        self.assertEqual(answer['text'], 'y')
        install = self.sent.get_header('X-companion-install')
        self.assertRegex(install, r'^[0-9a-f]{32}$')
        self.assertEqual(ai.install_id(self.folder), install, 'the same id every time')
        self.assertEqual(json.loads(self.sent.data)['task'], 'summarise')

    def test_the_request_names_itself_so_cloudflare_lets_it_through(self):
        # Will, November 18, 2026: writing help always said it could not do that. Cloudflare turns
        # away Python's own request name ("error code: 1010") before the service sees it.
        ai.service_request(self.folder, '0.2.215', 'summarise', {'text': 'x'}, opener=self.reply({'ok': True, 'text': 'y'}))
        agent = self.sent.get_header('User-agent')
        self.assertEqual(agent, 'VoiceCompanion/0.2.215')

    def test_a_refusal_it_does_not_know_is_written_down_without_the_text(self):
        def refused(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, 'Forbidden', {}, io.BytesIO(b'error code: 1010\n'))
        with self.assertRaises(ai.AssistantError) as caught:
            ai.service_request(self.folder, 'v', 'rewrite', {'text': 'My private letter'}, opener=refused)
        self.assertIn('try again', str(caught.exception))
        log = (Path(self.folder) / 'ai-error.txt').read_text(encoding='utf-8')
        self.assertIn('rewrite: status 403', log)
        self.assertIn('error code: 1010', log)
        self.assertNotIn('private letter', log)

    def test_the_service_own_reason_is_written_down(self):
        with self.assertRaises(ai.AssistantError):
            ai.service_request(self.folder, 'v', 'check_errors', {'text': 'x'},
                               opener=self.reply({'ok': False, 'error': 'ai service 400', 'detail': 'invalid_request: bad'}, 502))
        self.assertIn('check_errors: ai service 400 (invalid_request: bad)', (Path(self.folder) / 'ai-error.txt').read_text(encoding='utf-8'))

    def test_an_unexpected_problem_is_written_down_too(self):
        ai.LOG_FOLDER[0] = self.folder
        self.addCleanup(ai.LOG_FOLDER.__setitem__, 0, None)
        def broken():
            raise KeyError('corrections')
        job = ai.Job(broken)
        self.assertTrue(job.done.wait(2))
        self.assertIn('could not do that', job.error)
        self.assertIn('request: KeyError', (Path(self.folder) / 'ai-error.txt').read_text(encoding='utf-8'))

    def test_the_monthly_limit_is_said_plainly(self):
        with self.assertRaises(ai.AssistantError) as caught:
            ai.service_request(self.folder, 'v', 'summarise', {'text': 'x'},
                               opener=self.reply({'ok': False, 'error': 'monthly limit', 'limit': 200}, 429))
        self.assertIn('all 200 AI requests for this month', str(caught.exception))

    def test_the_picture_limit_is_said_plainly(self):
        with self.assertRaises(ai.AssistantError) as caught:
            ai.service_request(self.folder, 'v', 'describe_image', {'image': 'x'},
                               opener=self.reply({'ok': False, 'error': 'image limit', 'limit': 200}, 429))
        self.assertEqual(str(caught.exception), 'You have used all 200 picture descriptions for this month. They start again '
                         'on the first of next month. Reading and writing help still works.')

    def test_pictures_left_is_said_only_near_the_end(self):
        self.assertEqual(ai.pictures_left_words({'pictures_left': 150}), '')
        self.assertEqual(ai.pictures_left_words({}), '')
        self.assertEqual(ai.pictures_left_words({'pictures_left': 10}), ' You have 10 picture descriptions left this month.')
        self.assertEqual(ai.pictures_left_words({'pictures_left': 1}), ' You have 1 picture description left this month.')
        self.assertIn('last picture description', ai.pictures_left_words({'pictures_left': 0}))

    def test_the_spending_limit_reached_is_said_plainly(self):
        with self.assertRaises(ai.AssistantError) as caught:
            ai.service_request(self.folder, 'v', 'summarise', {'text': 'x'},
                               opener=self.reply({'ok': False, 'error': 'unavailable'}, 503))
        self.assertEqual(str(caught.exception), 'The AI assistant is not available right now. Please try again later.')

    def test_no_internet(self):
        def offline(request, timeout):
            raise urllib.error.URLError('down')
        with self.assertRaises(ai.AssistantError) as caught:
            ai.service_request(self.folder, 'v', 'summarise', {'text': 'x'}, opener=offline)
        self.assertIn('Check your internet connection', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
