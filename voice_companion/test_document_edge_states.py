"""Documents, notes and files at their edges (bug sweep, November 4, 2026): empty documents,
blank paragraphs, the very start and end, selections of nothing, and damaged files.

Each test here failed before its fix."""
import unittest
import zipfile

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


class EmptyAndBlankWording(DocumentFlowCase):
    """An email draft is a message, not a document; a paragraph of spaces is empty, not silence."""

    def draft(self, text=''):
        from email_draft import VoiceEmail
        app.email_draft = VoiceEmail(self.root / 'Email Drafts', recipient='sam@example.com', subject='Hi',
                                     compose_step='body')
        if text:
            app.email_draft.append_text(text)
        self.said.clear()

    def test_the_ends_of_a_draft_are_the_ends_of_the_message(self):
        self.draft('Dear Sam.')
        app.handle('go to beginning of document', 'email_draft')
        self.assertEqual(self.last(), 'Beginning of message. Dear Sam.')
        app.handle('go to end of document', 'email_draft')
        self.assertEqual(self.last(), 'End of message. Dear Sam.')

    def test_an_empty_draft_says_the_message_body_is_empty(self):
        self.draft()
        for said in ('go to end of document', 'next paragraph', 'read sentence', 'next word', 'go to end of line'):
            app.handle(said, 'email_draft')
            self.assertEqual(self.last(), 'The message body is empty.', said)

    def test_a_paragraph_of_spaces_is_said_as_empty(self):
        app.document = VoiceDocument(self.default, title='Spaces')
        app.document.paragraphs = [Paragraph('Hello.'), Paragraph('   ')]
        app.document.save()
        app.handle('go to end of document', 'document')
        self.assertEqual(self.last(), 'End of document. Empty paragraph.')
        app.handle('where am I', 'document')
        self.assertEqual(self.last(), 'Paragraph 2 of 2. Empty paragraph.')
        app.handle('make this bold', 'document')
        app.handle('undo', 'document')
        self.assertTrue(self.last().endswith('Paragraph 2 of 2. Empty paragraph.'), self.last())


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


class DamagedWordFiles(DocumentFlowCase):
    """A Word file with a broken part must be named as damaged, never stop the app or read out
    Python's own words ("invalid literal for int()")."""

    def make(self, name, xml):
        path = self.elsewhere / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        return path

    def test_broken_parts_say_the_file_is_damaged(self):
        cases = {
            'No body.docx': '<w:document ' + W + '></w:document>',
            'Bad size.docx': '<w:document ' + W + '><w:body><w:p><w:r><w:rPr><w:sz w:val="big"/></w:rPr>'
                             '<w:t>Hi</w:t></w:r></w:p></w:body></w:document>',
            'No size.docx': '<w:document ' + W + '><w:body><w:p><w:r><w:rPr><w:sz/></w:rPr>'
                            '<w:t>Hi</w:t></w:r></w:p></w:body></w:document>',
            'Bad spacing.docx': '<w:document ' + W + '><w:body><w:p><w:pPr><w:spacing w:line="wide"/></w:pPr>'
                                '<w:r><w:t>Hi</w:t></w:r></w:p></w:body></w:document>',
        }
        for name, xml in cases.items():
            with self.subTest(name=name):
                path = self.make(name, xml)
                with self.assertRaises(ValueError) as caught:
                    app.task_navigation().open_document(path)
                self.assertTrue(str(caught.exception).startswith('This document is empty or damaged'), str(caught.exception))
                self.assertIsNone(app.document)

    def test_a_word_file_with_an_empty_body_opens_as_an_empty_document(self):
        path = self.make('Blank.docx', '<w:document ' + W + '><w:body></w:body></w:document>')
        self.assertEqual(app.task_navigation().open_document(path), 'document')
        self.assertEqual(self.last(), 'Opened Blank.docx. Document. The document is empty.')


class DiskFiles:
    """File manager's Shell stand-in that really deletes and renames, as Windows does."""
    def __init__(self, root):
        from test_file_manager import FakeFiles
        self.fake = FakeFiles(root)

    def __getattr__(self, name):
        return getattr(self.fake, name)

    def operate(self, action, paths, destination=None, name=None):
        from pathlib import Path
        for path in map(Path, paths):
            if action == 'delete':
                path.unlink()
            elif action == 'rename':
                path.rename(path.with_name(name))


class FileManagerFocusAfterChanges(unittest.TestCase):
    """After Delete, focus stays where you were (the next item), not the top of the folder.
    After Rename, focus is on the renamed item."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from file_manager import FileManager
        from test_file_manager import settle
        self.settle = settle
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for name in ('a.txt', 'b.txt', 'c.txt', 'd.txt'):
            (self.root / name).write_text(name)
        self.fm = FileManager(DiskFiles(self.root))
        self.fm.refresh(str(self.root)); settle(self.fm)

    def test_delete_keeps_the_place_in_the_list(self):
        self.fm.index = 2
        self.fm.command('delete'); self.fm.command('yes'); self.settle(self.fm)
        self.assertEqual([i.name for i in self.fm.items], ['a.txt', 'b.txt', 'd.txt'])
        self.assertEqual(self.fm.current().name, 'd.txt')

    def test_deleting_the_last_item_lands_on_the_new_last_item(self):
        self.fm.command('end')
        self.fm.command('delete'); self.fm.command('yes'); self.settle(self.fm)
        self.assertEqual(self.fm.current().name, 'c.txt')

    def test_rename_focuses_the_renamed_item(self):
        self.fm.index = 0
        self.fm.command('rename'); self.fm.command('z.txt'); self.settle(self.fm)
        self.assertEqual([i.name for i in self.fm.items], ['b.txt', 'c.txt', 'd.txt', 'z.txt'])
        self.assertEqual(self.fm.current().name, 'z.txt')

    def test_a_typed_name_that_starts_with_name_is_kept_whole(self):
        self.fm.index = 0
        self.fm.command('rename'); self.fm.command('Name tags.txt'); self.settle(self.fm)
        self.assertTrue((self.root / 'Name tags.txt').exists())
        self.fm.command('rename'); self.fm.command('rename to list.txt'); self.settle(self.fm)
        self.assertTrue((self.root / 'list.txt').exists())


class ReaderPickerFailure(DocumentFlowCase):
    """Document reader, Open a document: a damaged Word file picked from the list said so and then
    went to the Document reader menu, so you lost your place. A damaged PDF or text file already
    stayed in the list. Both now stay on the file you picked."""

    def test_a_damaged_word_file_keeps_you_in_the_file_list(self):
        from file_manager import FileManager
        from test_file_manager import FakeFiles, settle
        (self.elsewhere / 'Broken.docx').write_bytes(b'not a zip file')
        (self.elsewhere / 'Good.txt').write_text('Fine.')
        nav = app.task_navigation()
        app.FILE_MANAGER = FileManager(FakeFiles(self.elsewhere))
        app.FILE_MANAGER.refresh(str(self.elsewhere)); settle(app.FILE_MANAGER)
        nav.picker = 'reader'
        self.assertEqual(nav.selected_file(self.elsewhere / 'Broken.docx'), 'files')
        self.assertTrue(self.last().startswith('This file is damaged or empty'), self.last())
        self.assertTrue(self.last().endswith('Broken.docx, file. 1 of 2.'), self.last())
        self.assertEqual(nav.picker, 'reader')
        # The next pick still opens in the Document reader, and Escape comes back to the list.
        self.assertEqual(nav.selected_file(self.elsewhere / 'Good.txt'), 'file_reader')
        self.assertEqual(nav.reader_return, 'reader_picker')


if __name__ == '__main__':
    unittest.main()
