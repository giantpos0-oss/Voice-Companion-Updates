"""Email with the keyboard only (nightly sweep, November 6, 2026).

A blind user who never speaks a command: Escape, Tab, Control keys and Delete on every
email screen must do what the guide and Help say, never lose typed text, and reach the
same result as the voice command.
"""
import unittest

import attachment_screen
import companion as app
import screen_menus
import test_attachment_voice
from email_draft import VoiceEmail
from input_parity import SCREEN_KEYS


class DraftFieldKeyTests(test_attachment_voice.PlacesTestCase):
    """The To, CC, BCC and Subject boxes of a draft."""

    def new_draft(self, **fields):
        draft = VoiceEmail(self.root / 'data' / 'Email Drafts', **fields)
        draft.save()
        app.email_draft = draft
        return draft

    def field_key(self, field, value, key):
        """What the window sends for a key pressed in a header box (app_window: email_field_tab)."""
        request = app.commit_email_field_tab({'field': field, 'value': value, 'backward': False, 'key': key}, 'email_draft')
        return app.handle_keyboard(request, 'email_draft') if request else 'email_draft'

    def test_escape_with_a_subject_typed_keeps_it_and_asks(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='subject')
        self.assertEqual(self.field_key('subject', 'Lunch on Friday', 'Escape'), 'draft_leave')
        self.assertEqual(draft.subject, 'Lunch on Friday')
        self.assertEqual(app.handle_keyboard(app.navigation_key('Enter', 'draft_leave'), 'draft_leave'), 'awake')
        self.assertEqual(VoiceEmail.open_existing(self.root / 'data' / 'Email Drafts', draft.title).subject, 'Lunch on Friday')

    def test_escape_with_only_an_address_typed_asks_before_closing(self):
        draft = self.new_draft(compose_step='recipient')
        self.assertEqual(self.field_key('recipient', 'sam@example.com', 'Escape'), 'draft_leave')
        self.assertEqual(draft.recipient, 'sam@example.com')
        self.assertEqual(app.handle_keyboard(app.navigation_key('Escape', 'draft_leave'), 'draft_leave'), 'email_draft')
        self.assertIs(app.email_draft, draft)

    def test_escape_always_leaves_even_when_the_box_holds_a_half_address(self):
        # A half typed address cannot be kept; Escape must still go back, never trap the user.
        self.new_draft(compose_step='recipient')
        self.assertNotEqual(self.field_key('recipient', 'sam', 'Escape'), 'email_draft')
        self.assertNotIn('could not understand', ' '.join(self.said))

    def test_control_r_and_undo_in_the_cc_box_are_not_taken_as_an_address(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='cc')
        for key in ('Ctrl+R', 'Ctrl+Z', 'Ctrl+Y'):
            with self.subTest(key=key):
                self.said.clear()
                self.field_key('cc', '', key)
                self.assertNotIn('could not understand one complete email address', ' '.join(self.said))
                self.assertEqual(draft.cc, [])
        for field in ('cc', 'bcc'):
            with self.subTest(field=field):
                draft.compose_step = field
                self.assertNotIn('could not understand', draft.process('read email draft'))
                self.assertNotIn('could not understand', draft.process('undo'))
                self.assertEqual(getattr(draft, field), [])

    def test_a_subject_that_starts_like_a_command_is_the_subject(self):
        # They went into the message body, or opened Help, and the subject stayed empty.
        for subject in ('Read this before Friday', 'Save the date', 'Use the side door', 'Undo the damage',
                        'Redo the roof', 'Name tags for Saturday', 'Start dictation class', 'Help with the move'):
            for typed in (True, False):
                with self.subTest(subject=subject, typed=typed):
                    draft = self.new_draft(recipient='sam@example.com', compose_step='subject')
                    mode = app.handle_keyboard(subject, 'email_draft') if typed else app.handle(subject, 'email_draft')
                    self.assertEqual(mode, 'email_draft')
                    self.assertEqual(draft.subject, subject)
                    self.assertEqual([p.text for p in draft.paragraphs if p.text], [])

    def test_whole_commands_still_work_in_the_subject_box(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='subject')
        app.handle_keyboard('Read subject', 'email_draft')
        self.assertEqual(self.last(), 'Subject: not entered.')
        app.handle_keyboard('Save draft', 'email_draft')
        self.assertIn('saved locally', self.last())
        self.assertEqual(app.handle_keyboard('help with writing email', 'email_draft'), 'help')
        self.assertEqual(draft.subject, '')

    def test_a_real_address_in_the_cc_box_is_still_recorded(self):
        draft = self.new_draft(recipient='sam@example.com', compose_step='cc')
        self.assertIn('CC recorded as ann@example.com', draft.process('ann@example.com'))


if __name__ == '__main__':
    unittest.main()
