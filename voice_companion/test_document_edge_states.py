"""Documents, notes and files at their edges (bug sweep, November 4, 2026): empty documents,
blank paragraphs, the very start and end, selections of nothing, and damaged files.

Each test here failed before its fix."""
import unittest

import companion as app
from document_editor import Paragraph, VoiceDocument
from test_document_save_as import DocumentFlowCase


class EditorSelectionByVoice(DocumentFlowCase):
    """The guide (5.3) says "Extend selection by word" and "Select to end of line" work in documents.
    In the Word processor they were typed into the text, or said the words were not found."""

    def open_letter(self):
        app.document = VoiceDocument(self.default, title='Letter')
        app.document.paragraphs = [Paragraph('Hello there. How are you?'), Paragraph('Second paragraph here.')]
        app.document.save()
        app.handle('go to beginning of document', 'document')
        self.said.clear()

    def texts(self):
        return [p.text for p in app.document.paragraphs]

    def test_extend_selection_grows_the_selection_and_types_nothing(self):
        self.open_letter()
        app.handle('select word', 'document')
        self.assertEqual(app.handle('Extend selection by word.', 'document'), 'document')
        self.assertEqual(self.last(), 'Selected there.')
        self.assertEqual(app.document.selected_text(), 'Hello there.')
        app.handle('extend selection to previous word', 'document')
        self.assertEqual(app.document.selected_text(), 'Hello there.')   # already at the first word
        self.assertEqual(self.last(), 'Nothing more to select.')
        self.assertEqual(self.texts(), ['Hello there. How are you?', 'Second paragraph here.'])

    def test_extend_selection_can_cross_into_the_next_paragraph(self):
        self.open_letter()
        app.handle('select line', 'document')
        app.handle('extend selection by line', 'document')
        self.assertEqual(app.document.selected_text(), 'Hello there. How are you?\nSecond paragraph here.')

    def test_select_to_an_end(self):
        self.open_letter()
        app.handle('next word', 'document')
        app.handle('Select to end of line.', 'document')
        self.assertEqual(app.document.selected_text(), 'there. How are you?')
        app.handle('clear selection', 'document')
        app.handle('select to the beginning of the line', 'document')
        self.assertEqual(app.document.selected_text(), 'Hello ')
        app.handle('clear selection', 'document')
        app.handle('select to the end', 'document')
        self.assertEqual(app.document.selected_text(), 'there. How are you?\nSecond paragraph here.')
        self.assertEqual(self.texts(), ['Hello there. How are you?', 'Second paragraph here.'])

    def test_the_selection_can_then_be_copied_or_deleted(self):
        self.open_letter()
        app.handle('next word', 'document')
        app.handle('select to end of line', 'document')
        app.handle('delete selection', 'document')
        self.assertEqual(self.texts(), ['Hello', 'Second paragraph here.'])

    def test_an_empty_document_says_there_is_nothing_to_select(self):
        app.document = VoiceDocument(self.default, title='Empty')
        for said in ('extend selection by word', 'select to the end', 'select to end of line'):
            app.handle(said, 'document')
            self.assertEqual(self.last(), 'The document is empty. There is no text to select.', said)
        self.assertEqual(self.texts(), [])

    def test_an_email_draft_works_the_same(self):
        from email_draft import VoiceEmail
        app.email_draft = VoiceEmail(self.root / 'Email Drafts', recipient='sam@example.com', subject='Hi',
                                     compose_step='body')
        app.email_draft.append_text('Dear Sam. See you soon.')
        app.handle('go to beginning of document', 'email_draft')
        app.handle('select word', 'email_draft')
        app.handle('extend selection by word', 'email_draft')
        self.assertEqual(app.email_draft.selected_text(), 'Dear Sam.')
        self.assertEqual([p.text for p in app.email_draft.paragraphs], ['Dear Sam. See you soon.'])


if __name__ == '__main__':
    unittest.main()
