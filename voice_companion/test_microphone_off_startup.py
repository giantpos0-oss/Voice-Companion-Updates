"""Starting with the microphone off (Will, October 2026).

0.2.166 started asleep, saying "Say wake up", with no microphone to hear it, and the
keyboard could be left in Thunderbird, which Companion starts for mail. Now it starts
on the main menu, takes the keyboard, and a stall writes freeze-report.txt."""
import queue
from pathlib import Path
import time
import unittest
from unittest import mock

import companion
from test_core_email_fixes import CompanionTestCase


class MicrophoneOffStartupTests(CompanionTestCase):
    def setUp(self):
        super().setUp()
        for name, value in dict(MICROPHONE_OFF=True, STARTUP_UPDATE_PENDING=False, SLEEP_RETURN_MODE='sleep').items():
            p = mock.patch.object(companion, name, value); p.start(); self.addCleanup(p.stop)

    def test_ready_message_says_how_to_use_keys_and_turn_the_microphone_on(self):
        prompt = companion.startup_prompt()
        self.assertNotIn('Say wake up', prompt)
        self.assertIn('Press F9 to turn it on', prompt)
        self.assertIn('arrow keys, Enter and Escape', prompt)
        companion.MICROPHONE_OFF = False
        self.assertIn('Say wake up', companion.startup_prompt())

    def test_answering_no_to_the_startup_update_goes_to_the_main_menu(self):
        service = mock.Mock(); service.check.return_value = True; service.events = queue.Queue()
        service.events.put(('available', {'version': '0.2.168-test'}))
        with mock.patch.object(companion, 'UPDATES', service), mock.patch.object(companion, 'PREFERENCES', {'check_updates': True}):
            self.assertEqual(companion.startup_update_mode(), 'update_offer')
            self.assertEqual(companion.handle('no', 'update_offer'), 'awake')
        self.assertEqual(companion.SLEEP_RETURN_MODE, 'awake')
        # One message: a second one would stop the first (test_startup_announcement.py).
        self.assertTrue(self.said[-1].startswith(companion.MICROPHONE_STILL_OFF), self.said)
        self.assertTrue(self.said[-1].endswith(companion.MAIN_MENU_PROMPT), self.said)

    def test_a_stalled_main_loop_writes_a_freeze_report_once(self):
        import faulthandler
        real_dump = faulthandler.dump_traceback

        def slow_dump(file, all_threads=True):
            # A busy computer: the thread stacks take a while. The report must never be seen half written
            # (it once failed in the full test run while other work was going on).
            time.sleep(.4)
            real_dump(file=file, all_threads=all_threads)
        with mock.patch.dict(companion.FREEZE_WATCH, {'beat': time.monotonic() - 100, 'reported': False}), \
                mock.patch.object(faulthandler, 'dump_traceback', slow_dump):
            companion.start_freeze_watch(limit=1, interval=.05)
            report = self.folder / 'freeze-report.txt'
            end = time.monotonic() + 10
            while not report.exists() and time.monotonic() < end: time.sleep(.01)
            text = report.read_text(encoding='utf-8')
            self.assertIn('stopped responding', text)
            self.assertIn('File', text)   # the stacks of every thread follow
            report.unlink(); time.sleep(.2)
            self.assertFalse(report.exists())     # once per freeze, not every few seconds
            companion.FREEZE_WATCH['beat'] = time.monotonic() + 3600   # the loop is moving again: stop watching
            time.sleep(.2)
        companion.FREEZE_WATCH['watcher'] = object()   # retire this test's watcher

    def test_a_replaced_watcher_does_nothing_after_it_wakes(self):
        # Found in the 0.2.215 checks: an older watcher woke during the freeze test, saw its freeze,
        # and marked it reported (in its own folder), so the test's watcher never wrote its report.
        import tempfile
        with tempfile.TemporaryDirectory() as old_folder, mock.patch.object(companion, 'APP', Path(old_folder)), \
                mock.patch.dict(companion.FREEZE_WATCH, {'beat': None, 'reported': False}):
            companion.start_freeze_watch(limit=0.1, interval=.3)       # the old watcher, asleep
            time.sleep(.05)
            companion.FREEZE_WATCH['watcher'] = object()               # replaced while it sleeps
            companion.FREEZE_WATCH['beat'] = time.monotonic() - 100
            time.sleep(.5)
            self.assertFalse(companion.FREEZE_WATCH['reported'])
            self.assertFalse((Path(old_folder) / 'freeze-report.txt').exists())

    def test_an_old_watcher_never_writes_into_a_later_folder(self):
        # The 0.2.214 ReadSpeaker trial failed on Windows: a watcher from an earlier test wrote
        # freeze-report.txt into the tutorial test's folder when that test ran long.
        import tempfile
        with mock.patch.dict(companion.FREEZE_WATCH, {'beat': None, 'reported': False}):
            companion.start_freeze_watch(limit=0.2, interval=.05)
            with tempfile.TemporaryDirectory() as later, mock.patch.object(companion, 'APP', Path(later)):
                companion.FREEZE_WATCH['beat'] = time.monotonic() - 100
                time.sleep(.4)
                self.assertFalse((Path(later) / 'freeze-report.txt').exists())
            companion.FREEZE_WATCH['watcher'] = object()
            time.sleep(.1)


if __name__ == '__main__':
    unittest.main()
