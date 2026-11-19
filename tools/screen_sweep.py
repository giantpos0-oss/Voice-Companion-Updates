"""Every key on real screens with content (a document, a note, an email draft, the file manager in a sandbox
folder, menus), reached by real commands from the main menu. Prints failures, keys that said nothing, and
"TOTAL distinct failures: N". File deletes outside the sandbox are refused (bug sweep, November 18, 2026)."""
import os, sys, signal, tempfile, traceback, collections, shutil
from pathlib import Path
from unittest.mock import patch, Mock
ROOT = Path(__file__).resolve().parent.parent / 'voice_companion'
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'tools/linux-test-stubs')]
SANDBOX = Path(tempfile.mkdtemp(prefix='vc-sweep-'))
HOME = SANDBOX / 'home'; (HOME / 'Documents').mkdir(parents=True)
for name, text in (('Alpha notes.txt', 'Alpha line one.\n\nAlpha line three.'), ('Budget.txt', 'Rent 900\nFood 300'), ('empty.txt', '')):
    (HOME / 'Documents' / name).write_text(text)
(HOME / 'Documents' / 'Sub folder').mkdir()
os.environ['HOME'] = os.environ['USERPROFILE'] = str(HOME)
os.chdir(SANDBOX)
only = sys.argv[1:]
sys.argv = ['companion']
import companion, subprocess, webbrowser, urllib.request, socket, time
companion.SAFETY_NET = True
said = []
class Stop(Exception): pass
def alarm(*a): raise Stop('hung')
signal.signal(signal.SIGALRM, alarm)
real_remove, real_rmtree, real_rename, real_replace = os.remove, shutil.rmtree, os.rename, os.replace
def inside(path): 
    try: return Path(path).resolve().is_relative_to(SANDBOX)
    except Exception: return False
def guard(real):
    def run(path, *a, **k):
        if not inside(path): raise PermissionError('sweep: outside the sandbox ' + str(path))
        return real(path, *a, **k)
    return run
blocked = Mock(return_value=Mock(returncode=0, stdout='', stderr='', wait=Mock(return_value=0), poll=Mock(return_value=0)))
patches = [patch.object(companion, n, lambda text, *a, **k: said.append(str(text))) for n in ('speak', 'speak_prompt', 'speak_status', 'dictation_feedback')]
patches += [patch.object(companion, 'TEXT_MODE', True), patch.object(companion, 'APP', SANDBOX / 'app'),
            patch.object(subprocess, 'Popen', blocked), patch.object(subprocess, 'run', blocked), patch.object(subprocess, 'call', blocked),
            patch.object(subprocess, 'check_output', Mock(return_value=b'')), patch.object(os, 'system', Mock(return_value=0)),
            patch.object(webbrowser, 'open', Mock()), patch.object(urllib.request, 'urlopen', Mock(side_effect=OSError('offline in sweep'))),
            patch.object(socket, 'create_connection', Mock(side_effect=OSError('offline in sweep'))),
            patch.object(sys, 'exit', Mock(side_effect=Stop('exit'))), patch.object(os, '_exit', Mock(side_effect=Stop('exit'))),
            patch.object(os, 'remove', guard(real_remove)), patch.object(os, 'unlink', guard(real_remove)),
            patch.object(shutil, 'rmtree', guard(real_rmtree)), patch.object(os, 'rename', guard(real_rename)),
            patch.object(os, 'replace', lambda a, b: real_replace(a, b) if inside(b) else (_ for _ in ()).throw(PermissionError('sweep'))),
            patch.object(Path, 'home', classmethod(lambda cls: HOME)), patch.object(time, 'sleep', lambda s: None)]
for p in patches: p.start()
(SANDBOX / 'app').mkdir()
SCENARIOS = {
  'document': ['create a document', 'Sweep test', 'confirm', 'First line of text.', 'Second line here.'],
  'word_processor': ['word processor'],
  'email_draft': ['write an email', 'sam@example.com', 'confirm', 'Lunch', 'confirm', 'See you at noon.'],
  'reader': ['document reader'],
  'media': ['media menu'],
  'organizer': ['organizer menu'],
  'contacts': ['address book'],
  'calendar': ['schedule manager'],
  'favorites': ['favorites'],
  'power': ['power menu'],
  'note': ['notepad', 'new note', 'Buy milk and bread.'],
  'files': ['file manager'],
  'help': ['help'],
  'settings': ['options'],
  'awake': [],
}
letters = [chr(c) for c in range(65, 91)]
KEYS = (['Up','Down','Left','Right','Home','End','PageUp','PageDown','Enter','Escape','Tab','Shift+Tab','Delete','Backspace','Space',
         'Ctrl+Home','Ctrl+End','Ctrl+Up','Ctrl+Down','Ctrl+Left','Ctrl+Right','Ctrl+Enter','Shift+Up','Shift+Down','Shift+Left','Shift+Right',
         'Ctrl+Shift+Right','Ctrl+Shift+Left','Ctrl+Shift+Q','Alt','Apps','Insert'] + ['F%d' % i for i in range(1, 13)]
        + ['Letter:' + c.lower() for c in letters] + ['Ctrl+' + c for c in letters] + ['Alt+' + c for c in letters])
failures = collections.OrderedDict(); silent = collections.defaultdict(list)
def run(text, mode):
    signal.alarm(8)
    try: return companion.handle(text, mode, typed=True) or mode
    finally: signal.alarm(0)
def setup(name):
    mode = 'awake'
    for step in SCENARIOS[name]: mode = run(step, mode)
    return mode
for name in (only or SCENARIOS):
    try: target = setup(name)
    except Exception as exc: print('SETUP FAILED', name, type(exc).__name__, exc); continue
    print('scenario', name, '->', target)
    for key in KEYS:
        mode = target
        try:
            if companion.navigation_key('Escape', 'awake') is None: pass
        except Exception: pass
        try:
            if setup(name) != target: continue
        except Exception: continue
        before = len(said)
        signal.alarm(8)
        try:
            request = companion.navigation_key(key, mode)
            if request: companion.handle_keyboard(request, mode)
            if len(said) == before and request is not None: silent[name].append(key)
        except Stop: pass
        except Exception as exc:
            tb = traceback.extract_tb(exc.__traceback__)
            where = next((f for f in reversed(tb) if 'voice_companion' in f.filename), tb[-1])
            failures.setdefault('%s: %s at %s:%d in %s' % (type(exc).__name__, str(exc)[:90], Path(where.filename).name, where.lineno, where.name), []).append(name + '/' + key)
        finally: signal.alarm(0)
    errors = list((SANDBOX / 'app').glob('*error*.txt'))
    for e in errors:
        failures.setdefault('logged in ' + e.name + ': ' + e.read_text()[-300:].replace('\n', ' | '), []).append(name); e.unlink()
for sig, where in failures.items(): print('%3d  %s\n      e.g. %s' % (len(where), sig, ', '.join(where[:8])))
for name, keys in silent.items(): print('SILENT', name, len(keys), ' '.join(keys[:40]))
print('TOTAL distinct failures:', len(failures))
