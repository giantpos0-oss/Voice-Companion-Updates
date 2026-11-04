"""Documents when something goes wrong: a file open in Word, a full disk (sweep, October 31, 2026).

The change must stay in the document, the app must keep running, and the person
must hear what happened and what to do next, never Python's own error text.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

import companion as app
from document_editor import VoiceDocument
from email_draft import VoiceEmail
from test_document_save_as import DocumentFlowCase

LOCKED = PermissionError(13, 'The process cannot access the file because it is being used by another process')


class LockedFileWhileEditing(DocumentFlowCase):
    """Every kind of change, said or pressed, while Word has the file open."""
    def open_letter(self):
        app.document = VoiceDocument(self.default, title='Letter')
        app.document.append_text('Dear Bob. How are you?')
        app.document.save()
        self.said.clear()

    def test_no_change_stops_the_app_or_reads_out_the_raw_error(self):
        ways = ('make it 14 points', 'type literally hello', 'new line', 'scratch that', 'delete paragraph',
                'replace Dear with Hi', 'delete word', 'cut paragraph', 'change font to Arial', 'delete sentence',
                'Ctrl+B', 'Ctrl+I', 'Ctrl+U', 'Enter')
        for way in ways:
            with self.subTest(way=way):
                self.open_letter()
                with patch.object(Path, 'replace', side_effect=LOCKED):
                    mode = self.press(way, 'document') if way.startswith('Ctrl+') or way == 'Enter' else app.handle(way, 'document')
                self.assertEqual(mode, 'document')
                heard = ' '.join(self.said)
                self.assertIn(app.UNSAVED_DOCUMENT, heard)
                self.assertNotIn('process cannot access', heard)


class LockedDraftWhileEditing(DocumentFlowCase):
    def test_a_change_in_an_email_draft_says_the_draft_was_not_saved(self):
        for way in ('replace Dear with Hi', 'delete word', 'Ctrl+B'):
            with self.subTest(way=way):
                app.email_draft = VoiceEmail(self.root / 'Email Drafts', recipient='sam@example.com', subject='Hi',
                                             compose_step='body')
                app.email_draft.append_text('Dear Sam. See you soon.')
                self.said.clear()
                with patch.object(Path, 'replace', side_effect=LOCKED):
                    mode = self.press(way, 'email_draft') if way.startswith('Ctrl+') else app.handle(way, 'email_draft')
                self.assertEqual(mode, 'email_draft')
                heard = ' '.join(self.said)
                self.assertIn(app.UNSAVED_DRAFT, heard)
                self.assertNotIn('process cannot access', heard)

    def test_word_processor_from_a_draft_that_cannot_be_saved_stays_in_the_draft(self):
        app.email_draft = VoiceEmail(self.root / 'Email Drafts', recipient='sam@example.com', subject='Hi',
                                     compose_step='body')
        app.email_draft.append_text('Dear Sam.')
        self.said.clear()
        with patch.object(Path, 'replace', side_effect=LOCKED):
            mode = app.handle('word processor', 'email_draft')
        self.assertEqual(mode, 'email_draft')
        self.assertIn(app.UNSAVED_DRAFT, ' '.join(self.said))


class UndoWhileTheFileIsLocked(DocumentFlowCase):
    """Undo with Word holding the file: Redo must still bring the words back."""
    def test_redo_brings_back_what_a_locked_undo_took_away(self):
        app.document = VoiceDocument(self.default, title='Letter')
        app.handle('Dear Bob.', 'document')
        app.handle('new paragraph', 'document')
        app.handle('See you on Friday.', 'document')
        with patch.object(Path, 'replace', side_effect=LOCKED):
            app.handle('undo', 'document')
        self.assertIn(app.UNSAVED_DOCUMENT, self.last())
        self.assertNotIn('See you on Friday.', [p.text for p in app.document.paragraphs])
        app.handle('redo', 'document')
        self.assertIn('Redid', self.last())
        self.assertIn('See you on Friday.', [p.text for p in app.document.paragraphs])
        # The redone words reach the file once Word lets go.
        from document_reader import open_document
        self.assertIn('See you on Friday.', open_document(app.document.path).text)

    def test_undo_twice_while_locked_undoes_two_steps(self):
        app.document = VoiceDocument(self.default, title='Letter')
        for words in ('One.', 'Two.', 'Three.'):
            app.handle('new paragraph', 'document'); app.handle(words, 'document')
        with patch.object(Path, 'replace', side_effect=LOCKED):
            app.handle('undo', 'document')
            app.handle('undo', 'document')
        app.handle('redo', 'document'); app.handle('redo', 'document')
        self.assertEqual([p.text for p in app.document.paragraphs if p.text], ['One.', 'Two.', 'Three.'])


class SavedWordsReachTheDisk(DocumentFlowCase):
    """A power cut or a laptop battery that dies just after a save must not leave an empty file."""
    def test_the_new_copy_is_on_the_disk_before_it_replaces_the_old_file(self):
        import os
        events = []
        real_fsync, real_replace = os.fsync, Path.replace
        def fsync(fd):
            events.append('fsync'); return real_fsync(fd)
        def replace(path, target):
            events.append('replace ' + Path(path).name); return real_replace(path, target)
        made = VoiceDocument(self.default, title='Letter'); made.append_text('Dear Bob.')
        with patch('os.fsync', side_effect=fsync), patch.object(Path, 'replace', replace):
            made.save()
        self.assertIn('replace Letter.writing.docx', events)
        self.assertEqual(events[events.index('replace Letter.writing.docx') - 1], 'fsync')


class DocumentsFromTheOldFolder(unittest.TestCase):
    """Before October 19, 2026, documents were kept in the app's own folder. Documents now go to
    Documents, Voice Companion; the old folder is never touched."""
    def setUp(self):
        import os, tempfile
        from contextlib import ExitStack
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        environment = {k: v for k, v in os.environ.items() if k != 'VOICE_COMPANION_DATA_DIR'}
        self.stack.enter_context(patch.dict(os.environ, environment, clear=True))
        app_folder = self.root / 'AppData'
        self.stack.enter_context(patch.object(app, 'APP', app_folder))
        self.stack.enter_context(patch.object(app, 'DEFAULT_APP', app_folder))
        self.stack.enter_context(patch.object(app.os, 'name', 'posix'))
        self.stack.enter_context(patch.object(Path, 'home', return_value=self.root / 'Home'))
        self.legacy = app_folder / 'Documents'; self.legacy.mkdir(parents=True)
        (self.legacy / 'Letter.docx').write_bytes(b'old letter')
        (self.legacy / 'List.docx').write_bytes(b'old list')

    def test_old_folder_is_left_alone(self):
        # Will, November 3, 2026: the one-time copy from the old folder was removed. Every tester
        # already has the new folder. The old copies are never touched or removed.
        folder = app.documents_folder()
        self.assertEqual(folder, self.root / 'Home' / 'Documents' / 'Voice Companion')
        self.assertFalse(folder.exists())
        self.assertEqual(sorted(p.name for p in self.legacy.iterdir()), ['Letter.docx', 'List.docx'])


class RecentDocumentsOnAFullDisk(DocumentFlowCase):
    def test_a_full_disk_does_not_empty_the_recent_documents_list(self):
        import errno, json
        first = VoiceDocument(self.default, title='Letter'); first.append_text('Dear Bob.')
        app.task_navigation().remember(first.path)
        recent = self.root / 'recent-documents.json'
        self.assertEqual(json.loads(recent.read_text(encoding='utf-8')), [str(first.path.resolve())])
        def full_disk(path, *a, **k):
            open(path, 'w').close()   # Windows has already emptied the file when the write fails
            raise OSError(errno.ENOSPC, 'There is not enough space on the disk')
        second = VoiceDocument(self.default, title='List'); second.append_text('Milk.')
        with patch.object(Path, 'write_text', full_disk), patch('os.fsync', side_effect=OSError(errno.ENOSPC, 'full')):
            app.task_navigation().remember(second.path)
        self.assertEqual(json.loads(recent.read_text(encoding='utf-8')), [str(first.path.resolve())])
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith('recent')), ['recent-documents.json'])


class KeyboardEditsInATable(DocumentFlowCase):
    """Backspace at the start of a cell, or Delete at the end of one, in the typing window.
    Joining or splitting cells broke the table, so every later save failed and the app stopped."""
    def make_table(self):
        import queue
        from unittest.mock import Mock
        app.document = VoiceDocument(self.default, title='Table')
        app.handle('Intro.', 'document')
        app.handle('create table with two rows and two columns', 'document')
        app.handle('A1', 'document')
        app.document.save()
        self.window = Mock(commands=queue.Queue())
        self.stack.enter_context(patch.object(app, 'APP_WINDOW', self.window))
        self.saved = self.default / 'Table.docx'
        self.before_bytes = self.saved.read_bytes()
        self.said.clear()

    def edit(self, after):
        context = app.app_context('document')
        before = context['text']
        self.window.commands.put(('text_edit', {'source': context['source'], 'before': before, 'after': after(before),
                                                'caret': 0, 'seq': 1}))
        return app.handle('read document', 'document')

    def test_joining_or_splitting_cells_is_refused_and_the_app_keeps_running(self):
        for name, after in (('Backspace at the start of the second cell', lambda text: text.replace('A1\n', 'A1', 1)),
                            ('Delete at the end of the line before the table', lambda text: text.replace('Intro.\n', 'Intro.', 1)),
                            ('Enter inside a cell', lambda text: text.replace('A1', 'A\n1', 1)),
                            ('a selection across cells, deleted', lambda text: text.replace('Intro.\nA1\n', 'Intro.', 1))):
            with self.subTest(name):
                self.make_table()
                cells = [(p.text, p.table_id, p.row, p.column) for p in app.document.paragraphs]
                self.assertEqual(self.edit(after), 'document')
                self.assertEqual([(p.text, p.table_id, p.row, p.column) for p in app.document.paragraphs], cells)
                self.assertIn('table', ' '.join(self.said).lower())
                app.document.save()   # the table can still be saved
                self.assertEqual(app.document.path, self.saved)

    def test_typing_inside_a_cell_still_works(self):
        self.make_table()
        self.assertEqual(self.edit(lambda text: text.replace('A1', 'A1 and more', 1)), 'document')
        self.assertIn('A1 and more', [p.text for p in app.document.paragraphs])


if __name__ == '__main__':
    unittest.main()
