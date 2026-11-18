"""Every key on every screen does something or says something; none of them stops with an error.
Bug sweep, November 18, 2026: in 0.2.215 most keys on the AI screen failed with NameError, and a
screen whose object had closed failed on every key. tools/key_sweep.py presses each key on each
screen, from an empty start, in its own process so it changes nothing here."""
import signal
import subprocess
import sys
import unittest
from pathlib import Path

SWEEP = Path(__file__).resolve().parent.parent / 'tools' / 'key_sweep.py'
SCREENS = SWEEP.with_name('screen_sweep.py')


@unittest.skipUnless(hasattr(signal, 'SIGALRM') and SWEEP.exists(), 'runs on Linux, from the repository')
class EveryKeyTests(unittest.TestCase):
    def test_no_key_on_any_screen_fails(self):
        done = subprocess.run([sys.executable, str(SWEEP)], capture_output=True, text=True, timeout=600)
        report = done.stdout.strip().splitlines()
        self.assertTrue(report and report[-1].startswith('TOTAL distinct failures:'), done.stdout[-2000:] + done.stderr[-2000:])
        self.assertEqual(report[-1], 'TOTAL distinct failures: 0', '\n'.join(report[-40:]))

    def test_no_key_on_a_screen_with_content_fails_or_says_nothing(self):
        done = subprocess.run([sys.executable, str(SCREENS)], capture_output=True, text=True, timeout=900)
        report = [line for line in done.stdout.splitlines() if not line.startswith('Heard:')]
        self.assertTrue(report and report[-1].startswith('TOTAL distinct failures:'), done.stdout[-2000:] + done.stderr[-2000:])
        self.assertEqual(report[-1], 'TOTAL distinct failures: 0', '\n'.join(report[-40:]))
        self.assertFalse([line for line in report if line.startswith('SILENT')], '\n'.join(report[-40:]))
        self.assertIn('scenario document -> document', report, 'a new document is named and opened')


if __name__ == '__main__':
    unittest.main()
