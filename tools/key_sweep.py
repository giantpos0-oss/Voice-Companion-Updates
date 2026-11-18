"""Every key on every screen, from an empty start, in its own process (bug sweep, November 18, 2026).

Prints each kind of failure with where it happened, then "TOTAL distinct failures: N". Anything with real
effects (programs, the network, exiting, shutting down) is blocked. Run by test_every_key_every_screen.py."""
import os, sys, signal, tempfile, traceback, collections, builtins
from pathlib import Path
from unittest.mock import patch, Mock
ROOT = Path(__file__).resolve().parent.parent / 'voice_companion'
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'tools/linux-test-stubs')]
os.chdir(tempfile.mkdtemp())
import companion, subprocess, webbrowser, urllib.request, socket, time
said = []
modes = sys.argv[1:] or None
sys.argv = ['companion']
MODES = ('awake sleep exit exit_confirm settings help search files file_reader document document_name document_save document_menu '
         'document_replace note email_draft draft_leave mailbox attachments contacts calendar downloads web browser_menu youtube media '
         'local_media podcast tutorial chrome_setup ai_assistant update_offer update_download task_input power_menu power_confirm '
         'favorites_menu media_menu notepad_menu office_menu organizer_menu reader_menu reader_recent recent_documents web_tools_menu word_processor').split()
letters = [chr(c) for c in range(65, 91)]
KEYS = (['Up','Down','Left','Right','Home','End','PageUp','PageDown','Enter','Escape','Tab','Shift+Tab','Delete','Backspace','Space',
         'Ctrl+Home','Ctrl+End','Ctrl+Up','Ctrl+Down','Ctrl+Left','Ctrl+Right','Ctrl+Enter','Shift+Enter','Shift+Up','Shift+Down',
         'Ctrl+Shift+Q','Ctrl+Shift+Right','Ctrl+Shift+Left','Alt','Apps','Shift+F10','Insert']
        + ['F%d' % i for i in range(1, 13)] + ['Letter:' + c.lower() for c in letters] + ['Ctrl+' + c for c in letters]
        + ['Alt+' + c for c in letters] + ['Alt+%d' % i for i in range(1, 6)])
failures = collections.OrderedDict()
class Stop(Exception): pass
def alarm(*a): raise Stop('hung over 5 seconds')
signal.signal(signal.SIGALRM, alarm)
blocked = Mock(return_value=Mock(returncode=0, stdout='', stderr='', wait=Mock(return_value=0), poll=Mock(return_value=0)))
patches = [patch.object(companion, n, lambda text, *a, **k: said.append(str(text))) for n in ('speak', 'speak_prompt', 'speak_status', 'dictation_feedback')]
patches += [patch.object(companion, 'TEXT_MODE', True), patch.object(companion, 'APP', Path(tempfile.mkdtemp())),
            patch.object(subprocess, 'Popen', blocked), patch.object(subprocess, 'run', blocked), patch.object(subprocess, 'call', blocked),
            patch.object(subprocess, 'check_output', Mock(return_value=b'')), patch.object(os, 'system', Mock(return_value=0)),
            patch.object(webbrowser, 'open', Mock()), patch.object(urllib.request, 'urlopen', Mock(side_effect=OSError('offline in sweep'))),
            patch.object(socket, 'create_connection', Mock(side_effect=OSError('offline in sweep'))),
            patch.object(sys, 'exit', Mock(side_effect=Stop('exit'))), patch.object(os, '_exit', Mock(side_effect=Stop('exit'))),
            patch.object(time, 'sleep', lambda s: None)]
if hasattr(os, 'startfile'): patches.append(patch.object(os, 'startfile', Mock()))
for p in patches: p.start()
for mode in (modes or MODES):
    for key in KEYS:
        signal.alarm(5)
        try:
            request = companion.navigation_key(key, mode)
            if request: companion.handle_keyboard(request, mode)
        except Stop:
            pass
        except Exception as exc:
            tb = traceback.extract_tb(exc.__traceback__)
            where = next((f for f in reversed(tb) if 'voice_companion' in f.filename), tb[-1])
            sig = '%s: %s at %s:%d in %s' % (type(exc).__name__, str(exc)[:90], Path(where.filename).name, where.lineno, where.name)
            failures.setdefault(sig, []).append('%s/%s' % (mode, key))
        finally:
            signal.alarm(0)
for sig, where in failures.items():
    print('%3d  %s\n      e.g. %s' % (len(where), sig, ', '.join(where[:6])))
print('TOTAL distinct failures:', len(failures))
