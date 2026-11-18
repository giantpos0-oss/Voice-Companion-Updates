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


@unittest.skipUnless(hasattr(signal, 'SIGALRM') and SWEEP.exists(), 'runs on Linux, from the repository')
class EveryKeyTests(unittest.TestCase):
    def test_no_key_on_any_screen_fails(self):
        done = subprocess.run([sys.executable, str(SWEEP)], capture_output=True, text=True, timeout=600)
        report = done.stdout.strip().splitlines()
        self.assertTrue(report and report[-1].startswith('TOTAL distinct failures:'), done.stdout[-2000:] + done.stderr[-2000:])
        self.assertEqual(report[-1], 'TOTAL distinct failures: 0', '\n'.join(report[-40:]))


if __name__ == '__main__':
    unittest.main()
