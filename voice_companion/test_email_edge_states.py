"""Email in empty and edge states (sweep, November 4, 2026).

Messages with no words where words were expected, senders with no name or
address, empty folders and the last message: each is said plainly, and no
message that has words is ever called blank. The Yahoo tests talk to the
local Yahoo stand-in over a socket through the real imaplib.
"""
import tempfile
import unittest
from unittest.mock import patch

from mail_voice import MailSession
from test_email_attachments import StructureServer
from test_yahoo_mail import ADDRESS, APP_PASSWORD, message
from yahoo_mailbox import YahooMailbox


class YahooSession(unittest.TestCase):
    def setUp(self):
        self.server = StructureServer()
        self.addCleanup(self.server.close)
        self.folder = tempfile.mkdtemp()
        token = patch('mail_voice.account_token', return_value=(ADDRESS, APP_PASSWORD))
        token.start()
        self.addCleanup(token.stop)
        factory = lambda provider, secret: YahooMailbox(ADDRESS, APP_PASSWORD, self.server.factory)
        self.session = MailSession('yahoo', self.folder, factory)

    def use_plain_text(self):
        with open(self.folder + '/preferences.json', 'w', encoding='utf-8') as file:
            file.write('{"email_format": "plain"}')


class BlankHtmlTests(YahooSession):
    # Newsletters and flyers often send a picture as the HTML part and the words as
    # the plain part. "No readable body." hid words that were in the message.
    def test_picture_only_html_reads_the_plain_words(self):
        self.server.add('Inbox', message(body='Your benefits letter is ready.',
                                         html='<html><body><img src="cid:flyer"></body></html>'))
        self.session.process('open inbox')
        said = self.session.process('read message 1')
        self.assertIn('Your benefits letter is ready.', said)
        self.assertNotIn('No readable body', said)

    def test_plain_text_setting_also_reads_the_plain_words(self):
        self.server.add('Inbox', message(body='Your benefits letter is ready.',
                                         html='<html><body><img src="cid:flyer"></body></html>'))
        self.use_plain_text()
        self.session.process('open inbox')
        self.assertIn('Your benefits letter is ready.', self.session.process('read message 1'))

    def test_html_with_words_is_still_read_as_html(self):
        self.server.add('Inbox', message(body='Plain part.', html='<p>Rich part.</p>'))
        self.session.process('open inbox')
        self.assertIn('Rich part.', self.session.process('read message 1'))

    def test_thunderbird_picture_only_html_reads_the_plain_words(self):
        from thunderbird_mailbox import ThunderbirdMailbox
        box = ThunderbirdMailbox(ADDRESS, {'account_id': 'account1'})
        parts = {'html': '<table><tr><td><img src="https://example.com/a.png"></td></tr></table>',
                 'plain': 'Your benefits letter is ready.', 'attachments': []}
        with patch('thunderbird_mailbox.call', return_value=parts):
            body = box.read_message('5')
        self.assertEqual(str(body), 'Your benefits letter is ready.')
        self.assertEqual(body.plain, 'Your benefits letter is ready.')


class EmptySenderTests(YahooSession):
    # Some bounce and system messages say "From: <>": no name and no address.
    # It was spoken as the symbols "<>" in the list and in "Who is it from?".
    def test_a_sender_with_no_name_or_address_is_unknown_sender(self):
        self.server.add('Inbox', message(raw=b'From: <>\nSubject: Returned mail\n\nIt could not be delivered.\n'))
        said = self.session.process('open inbox')
        self.assertIn('Unknown sender. Returned mail.', said)
        self.assertNotIn('<>', said)
        self.assertEqual(self.session.process('who is it from'), 'From: Unknown sender.')

    def test_a_name_without_an_address_is_still_said(self):
        from mail_voice import sender_name
        self.assertEqual(sender_name({'from': 'Sam Lee'}), 'Sam Lee')
        self.assertEqual(sender_name({'from': '"" <>'}), 'Unknown sender')


class EmptyFolderNumberTests(YahooSession):
    # "An empty folder is an empty list, the same for every key and command."
    # A number said in an empty folder said "That number is not on this page."
    def test_message_numbers_in_an_empty_folder_say_empty_list(self):
        self.assertIn('Empty list', self.session.process('open inbox'))
        for command in ('read message 1', 'open message 2', 'select message 1', 'mark message one',
                        'select messages 1 through 3'):
            self.assertIn('Empty list. No messages on this page of Inbox.', self.session.process(command), command)

    def test_a_number_past_the_end_still_says_so(self):
        self.server.add('Inbox', message(subject='Only one'))
        self.session.process('open inbox')
        self.assertEqual(self.session.process('read message 4'), 'That number is not on this page. Say list messages.')


class DraftLeftoverTests(unittest.TestCase):
    # A power cut while a draft is saved can leave "Lunch.writing.json" behind. It was
    # listed as a draft named "Lunch.writing", and opening it said the file was damaged.
    def setUp(self):
        from test_email_new_veteran import CompanionCase
        self.case = CompanionCase('last')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        from email_draft import VoiceEmail
        draft = VoiceEmail(self.case.folder / 'Email Drafts', title='Lunch')
        draft.recipient, draft.subject = 'friend@example.com', 'Lunch'
        draft.save()
        (self.case.folder / 'Email Drafts' / 'Lunch.writing.json').write_text('{"title": "Lu', encoding='utf-8')

    def test_drafts_list_leaves_out_unfinished_save_files(self):
        import companion
        companion.handle('list email drafts', 'awake')
        self.assertEqual(self.case.last(), 'Your email drafts are: Lunch.')
        companion.handle('open email draft', 'awake')
        self.assertIn('Email drafts list. Lunch', self.case.last())
        self.assertIn('1 of 1', self.case.last())

    def test_saved_draft_names_skip_temporary_files(self):
        from email_draft import saved_draft_names
        self.assertEqual(saved_draft_names(self.case.folder / 'Email Drafts'), ['Lunch'])
        self.assertEqual(saved_draft_names(self.case.folder / 'No such folder'), [])


if __name__ == '__main__':
    unittest.main()
