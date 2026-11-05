"""Will, November 4, 2026: save several attachments at once. In the Attachments list, Space tags
files one by one and Control+A tags them all; Control+S then saves every tagged file in Downloads,
and Control+D saves them in a folder you name. File manager's tags attach several files at once."""
import unittest

import attachment_screen
import companion as app
import test_attachment_flows
import test_attachment_voice


class AttachmentTagTests(test_attachment_voice.PlacesTestCase):
    def list_mode(self):
        return self.press('L', self.opened_message())

    def test_space_tags_and_control_s_saves_every_tagged_file(self):
        mode = self.list_mode()
        self.press('Space', mode)
        self.assertEqual(self.last(), 'Tagged. 1 attachment tagged.')
        self.press('Down', mode); self.press('Down', mode); self.press('Space', mode)
        self.assertEqual(self.last(), 'Tagged. 2 attachments tagged.')
        self.assertTrue(attachment_screen.describe().endswith(', tagged.'))
        self.press('Ctrl+Shift+T', mode)
        self.assertEqual(self.last(), '2 attachments tagged: report.pdf, setup.exe.')
        self.press('Ctrl+S', mode)
        self.assertIn('Saved 2 attachments in your Downloads folder: report.pdf, setup.exe.', self.last())
        self.assertEqual(attachment_screen.TAGGED, set())   # tags clear once saved

    def test_control_a_tags_all_and_control_d_asks_for_one_folder(self):
        mode = self.list_mode()
        self.press('Ctrl+A', mode)
        self.assertTrue(self.last().startswith('Tagged all. 3 attachments tagged.'))
        self.press('Ctrl+D', mode)
        self.assertIn('Save 3 attachments to a folder', self.last())
        app.handle_keyboard('Music', mode)
        self.assertIn('Saved 3 attachments in your Music folder', self.last())
        self.assertEqual(len(list(self.places['music'].iterdir())), 3)

    def test_space_again_untags_and_nothing_tagged_saves_the_current_file(self):
        mode = self.list_mode()
        self.press('Space', mode); self.press('Space', mode)
        self.assertEqual(self.last(), 'Untagged. No files tagged.')
        self.press('Ctrl+Shift+A', mode)
        self.assertTrue(self.last().startswith('Tags cleared.'))
        self.press('Ctrl+S', mode)
        self.assertEqual(self.last(), 'Saved report.pdf in your Downloads folder.')

    def test_tag_by_voice(self):
        mode = self.list_mode()
        app.handle('Tag.', mode)
        self.assertEqual(self.last(), 'Tagged. 1 attachment tagged.')
        app.handle('Untag.', mode)
        self.assertEqual(self.last(), 'Untagged. No files tagged.')

    def test_tags_end_with_the_list(self):
        mode = self.list_mode()
        self.press('Ctrl+A', mode)
        self.press('Escape', mode)
        self.press('L', 'mailbox')
        self.assertEqual(attachment_screen.TAGGED, set())


class AttachSeveralTests(test_attachment_flows.FlowTestCase):
    def test_control_a_then_enter_attaches_every_file_and_leaves_folders_out(self):
        draft = self.draft()
        mode = self.settle_files(self.press('Ctrl+O', 'email_draft'))
        self.press('Ctrl+A', mode)
        self.press('End', mode)   # Enter on a folder opens it; Enter on a file attaches every tagged file
        self.assertEqual(self.press('Enter', mode), 'email_draft')
        self.assertEqual(sorted(a['name'] for a in draft.attachments), ['letter.txt', 'photo.jpg'])
        self.assertIn('Old letters is a folder, so it was left out.', self.last())
        self.assertEqual(app.FILE_MANAGER.selected, set())   # tags clear once attached

    def test_only_folders_are_still_refused(self):
        self.draft()
        mode = self.settle_files(self.press('Ctrl+O', 'email_draft'))
        app.FILE_MANAGER.choose('Old letters'); self.press('Space', mode)
        self.assertEqual(self.press('Ctrl+O', mode), 'files')
        self.assertIn('Old letters is a folder. Choose files, not folders.', self.last())


if __name__ == '__main__':
    unittest.main()
