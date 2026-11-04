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


if __name__ == '__main__':
    unittest.main()
