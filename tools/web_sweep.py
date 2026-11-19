"""Deep web sweep: Companion's own WebSession drives real Chrome over a local test site.

  python3 tools/web_sweep.py           Chrome in front
  python3 tools/web_sweep.py --held    Chrome behind Companion: clicks and keys get no answer
"""
import os, sys, time, json, tempfile, threading, collections, traceback, http.server, socketserver
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / 'voice_companion'
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'tools/linux-test-stubs')]
SITE = Path(__file__).resolve().parent / 'web_sweep' / 'site'
HELD = '--held' in sys.argv          # make Chrome hold back clicks and key presses, as on Will's computer
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=str(SITE), **k)
    def log_message(s, *a): pass
    def do_GET(s):
        if s.path.startswith('/slow'):
            time.sleep(2); s.send_response(302); s.send_header('Location', '/page2.html'); s.end_headers(); return
        if s.path.startswith('/redirect'):
            s.send_response(302); s.send_header('Location', '/page2.html'); s.end_headers(); return
        if s.path.startswith('/file.zip'):
            s.send_response(200); s.send_header('Content-Type', 'application/zip'); s.send_header('Content-Disposition', 'attachment; filename="file.zip"'); s.end_headers(); s.wfile.write(b'PK\x05\x06' + bytes(18)); return
        # The pages are kept as .html.txt: they hold a table to read, and the repository keeps
        # tables out of its documents (test_no_tables). They are served as web pages.
        page = SITE / (s.path.split('?')[0].lstrip('/') or 'index.html')
        if page.suffix == '.html' and Path(str(page) + '.txt').is_file():
            body = Path(str(page) + '.txt').read_bytes()
            s.send_response(200); s.send_header('Content-Type', 'text/html; charset=utf-8')
            s.send_header('Content-Length', str(len(body))); s.end_headers(); s.wfile.write(body); return
        return super().do_GET()
srv = socketserver.ThreadingTCPServer(('127.0.0.1', 0), H); srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % srv.server_address[1]
import web_assistant
from web_assistant import WebSession, BrowserBackend
if HELD:
    from playwright.sync_api import Locator, Keyboard, ElementHandle
    def held(name):
        def run(self, *a, **k):
            time.sleep(min(k.get('timeout', 1000) or 1000, 1500) / 1000.0)
            raise type('TimeoutError', (Exception,), {})('held back (sweep)')
        return run
    for cls in (Locator, ElementHandle):
        for n in ('click', 'press'): setattr(cls, n, held(n))
folder = tempfile.mkdtemp(prefix='vc-web-')
backend = BrowserBackend(folder, 'chrome', headless=True)
session = WebSession(folder, backend)
BAD = ('could not be used', 'did not finish cleanly', 'did not complete', 'went wrong', 'not ready', 'problem in voice companion',
       'could not reach', 'traceback', 'error')
issues = collections.OrderedDict(); slow = []
def call(label, fn, *a):
    start = time.monotonic()
    try: said = fn(*a)
    except Exception as exc:
        tb = traceback.extract_tb(exc.__traceback__); f = next((x for x in reversed(tb) if 'voice_companion' in x.filename), tb[-1])
        said = 'EXCEPTION %s %s at %s:%d' % (type(exc).__name__, str(exc)[:80], Path(f.filename).name, f.lineno)
    took = time.monotonic() - start
    text = str(said or '')
    if took > 2.5: slow.append('%5.1fs %s -> %s' % (took, label, text[:90]))
    low = text.lower()
    if text.startswith('EXCEPTION') or any(b in low for b in BAD):
        issues.setdefault(text[:150], []).append(label)
    return text
def page(name):
    return call('open ' + name, session.open, BASE + name)
PAGES = ['index.html', 'form.html', 'dialogs.html', 'spa.html', 'modal.html', 'frames.html', 'cookie.html', 'long.html', 'refresh.html', 'popup.html']
NAV = ['Down'] * 6 + ['Up', 'Tab', 'Tab', 'ShiftTab', 'Home', 'End', 'PageTop', 'PageBottom', 'Next', 'Prior'] + ['Quick:' + k for k in 'khfbxcetrldgmps'] + ['Space', 'Escape', 'Refresh', 'Back', 'Forward']
COMMANDS = ['list links', 'list headings', 'read page', 'next heading', 'previous heading', 'where am i', 'read current line', 'list fields', 'go back', 'refresh', 'next link', 'list landmarks']
for name in PAGES:
    page(name)
    for key in NAV:
        call(name + ' key ' + key, session.keyboard, key)
        if not (session.snapshot or {}).get('url', '').endswith(name): page(name)
    for cmd in COMMANDS:
        call(name + ' say ' + cmd, session.command, cmd)
        if not (session.snapshot or {}).get('url', '').endswith(name): page(name)
    # every link, button and control on the page, activated one by one from a fresh page
    page(name)
    items = [e for e in session.browse.elements if web_assistant.kind(e) in ('link', 'button', 'checkbox', 'radio', 'edit', 'combobox')][:25]
    for i, item in enumerate(items):
        page(name)
        target = next((e for e in session.browse.elements if e.get('label') == item.get('label') and web_assistant.kind(e) == web_assistant.kind(item)), None)
        if target is None: continue
        session.browse.set_position(target['start'])
        label = '%s activate %s "%s"' % (name, web_assistant.kind(item), (item.get('label') or '')[:30])
        said = call(label, session.keyboard, 'Activate')
        if session.pending: call(label + ' then yes', session.command, 'yes')
        if web_assistant.kind(item) in ('edit',) and session.keyboard_field is not None:
            call(label + ' type', session.command, 'type dogs') ; call(label + ' Done', session.keyboard, 'Done')
for sig, where in issues.items(): print('ISSUE %3d  %s\n           e.g. %s' % (len(where), sig, ' | '.join(where[:4])))
for s in slow: print('SLOW', s)
print('TOTAL issues:', len(issues), 'slow:', len(slow))
try: backend.close()
except Exception: pass
print('BROWSER LOG:'); print((Path(folder)/'browser-log.txt').read_text() if (Path(folder)/'browser-log.txt').exists() else '(none)')
