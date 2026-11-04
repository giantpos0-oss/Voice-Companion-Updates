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


class MissingCharsetTests(YahooSession):
    # Some mail programs send accented letters without saying which character set they
    # used. "Café" was read as "Caf" and two unknown symbols. Thunderbird reads these as
    # UTF-8, or as Windows Western text when they are not UTF-8.
    def read(self, raw):
        self.server.add('Inbox', message(raw=raw))
        self.session.process('open inbox')
        return self.session.process('read message 1')

    def test_utf8_letters_without_a_character_set_are_read(self):
        said = self.read(b'From: a@example.com\nSubject: Menu\n\nCaf\xc3\xa9 au lait at noon.\n')
        self.assertIn('Café au lait at noon.', said)
        self.assertNotIn('�', said)

    def test_html_without_a_character_set_is_read(self):
        said = self.read(b'From: a@example.com\nSubject: Menu\nContent-Type: text/html\n\n<p>Jos\xc3\xa9 is here.</p>\n')
        self.assertIn('José is here.', said)

    def test_western_letters_without_a_character_set_are_read(self):
        said = self.read(b'From: a@example.com\nSubject: Menu\nContent-Type: text/plain; charset=us-ascii\n'
                         b'Content-Transfer-Encoding: 8bit\n\nCaf\xe9 \x93open\x94 today.\n')
        self.assertIn('Café “open” today.', said)

    def test_a_declared_character_set_is_kept(self):
        said = self.read(b'From: a@example.com\nSubject: Menu\nContent-Type: text/plain; charset=iso-8859-1\n\nCaf\xe9\n')
        self.assertIn('Café', said)


class NoSubjectReplyTests(YahooSession):
    # "(no subject)" is only how the list shows a blank subject. A reply or forward to
    # such a message was sent with the subject "Re: (no subject)", words the sender never wrote.
    def test_yahoo_reply_and_forward_to_a_blank_subject(self):
        uid = self.server.add('Inbox', message(raw=b'From: Sam <sam@example.com>\nSubject: \n\nCall me.\n'))
        box = YahooMailbox(ADDRESS, APP_PASSWORD, self.server.factory)
        reply = box.response_context(str(uid), 'reply', ADDRESS, 'INBOX')
        self.assertEqual(reply['subject'], 'Re:')
        forward = box.response_context(str(uid), 'forward', ADDRESS, 'INBOX')
        self.assertEqual(forward['subject'], 'Fwd:')
        self.assertEqual(forward['original_subject'], '')
        # The list still says it plainly.
        self.assertIn('No subject', self.session.process('open inbox'))

    def test_thunderbird_reply_to_a_blank_subject(self):
        from thunderbird_mailbox import ThunderbirdMailbox
        box = ThunderbirdMailbox(ADDRESS, {'account_id': 'account1'})
        info = {'author': 'Sam <sam@example.com>', 'subject': '', 'recipients': [ADDRESS], 'headerMessageId': 'm1'}
        with patch('thunderbird_mailbox.call', return_value=info):
            self.assertEqual(box.response_context('5', 'reply', ADDRESS)['subject'], 'Re:')
        with patch('thunderbird_mailbox.call', return_value={'author': 'Sam <sam@example.com>', 'subject': 'Plans'}):
            self.assertEqual(box.response_context('5', 'reply', ADDRESS)['subject'], 'Re: Plans')


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


class AccountRemovedTests(unittest.TestCase):
    # A helper removes the account while the inbox is open. The next command said only
    # "This email account is not connected." with nothing to do next.
    def test_inbox_command_after_the_account_is_removed_says_what_to_do(self):
        folder = tempfile.mkdtemp()
        session = MailSession('yahoo', folder)
        session.rows = [{'id': '1', 'from': 'Sam <sam@example.com>', 'subject': 'Hi'}]
        session.current = 1
        said = session.process('list messages')
        self.assertIn('not connected', said)
        self.assertIn('Say add account', said)
        self.assertEqual(session.rows[0]['subject'], 'Hi')   # the list you had is kept


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
