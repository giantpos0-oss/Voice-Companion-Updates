"""VoiceCompanion-Speech32.exe: the Windows voice in a 32-bit program.

Some older SAPI 5 voices exist only as 32-bit programs, for example NeoSpeech
"VW Paul", "VW Kate" and "VW James" (Will, November 2026). Voice Companion is a
64-bit program, and Windows only offers a 64-bit program the 64-bit voices. So
these voices never appeared. This small program is built with 32-bit Python. It
makes the voice the 32-bit way and speaks for Voice Companion (speech32.py),
as NVDA and other screen readers do.

Protocol: one JSON object per line, on standard input and output, ASCII only.
- At start it writes {"event": "ready", "ok": true, "bits": 32} once the voice is
  made, or {"event": "ready", "ok": false, "error": "..."} and stops.
- Every request has an "id" and a "cmd". Every request gets one answer with the
  same "id" and "ok" (true or false, with "error"), in the order they came:
  - list: {"voices": [{"id": token Id, "name": description}, ...]}
  - voice {"voice": token Id}: chooses by Id, or by the last part of the Id
    (the token name). The answer has "id_chosen" and "name".
  - rate {"value": -10..10}, volume {"value": 0..100}
  - speak {"text", "flags"}: SAPI flags as a number. Always spoken without
    waiting (flag 1 is added), so the helper keeps answering.
  - stop: ends speech now and drops what is waiting, even when paused.
  - pause, resume: safe to repeat.
  - done {"ms": 0..1000}: WaitUntilDone; answers {"done": true or false}.
  - quit: answers, then stops.
- It stops by itself when standard input closes or when the program named by
  --parent <process id> ends, so it never outlives Voice Companion.

It must stay small: it never imports Voice Companion's own modules.
"""
import json
import os
import queue
import sys
import threading
import time

SPEAK_ASYNC = 1
SPEAK_PURGE = 2
LONGEST_WAIT_MS = 1000


def sapi_voice():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.Dispatch('SAPI.SpVoice')


def pump():
    try:
        import pythoncom
        pythoncom.PumpWaitingMessages()
    except Exception:
        pass


def token_name(token_id):
    return str(token_id).replace('/', '\\').rstrip('\\').rsplit('\\', 1)[-1].casefold()


class Host:
    def __init__(self, voice):
        self.voice = voice
        self.paused = False

    def tokens(self):
        found = self.voice.GetVoices()
        return [found.Item(i) for i in range(found.Count)]

    def handle(self, request):
        cmd = request.get('cmd')
        voice = self.voice
        if cmd == 'list':
            return {'voices': [{'id': str(t.Id), 'name': str(t.GetDescription())} for t in self.tokens()]}
        if cmd == 'voice':
            wanted = str(request.get('voice', ''))
            tokens = self.tokens()
            token = next((t for t in tokens if str(t.Id) == wanted), None) or \
                next((t for t in tokens if token_name(t.Id) == token_name(wanted)), None)
            if token is None:
                return {'ok': False, 'error': 'That voice is not installed.'}
            voice.Voice = token
            return {'id_chosen': str(token.Id), 'name': str(token.GetDescription())}
        if cmd == 'rate':
            voice.Rate = max(-10, min(10, int(request.get('value', 0))))
            return {}
        if cmd == 'volume':
            voice.Volume = max(0, min(100, int(request.get('value', 100))))
            return {}
        if cmd == 'speak':
            flags = int(request.get('flags', 0)) | SPEAK_ASYNC
            voice.Speak(str(request.get('text', '')), flags)
            return {}
        if cmd == 'stop':
            if self.paused:
                voice.Resume()
                self.paused = False
            voice.Speak('', SPEAK_ASYNC | SPEAK_PURGE)
            return {}
        if cmd == 'pause':
            if not self.paused:
                voice.Pause()
                self.paused = True
            return {}
        if cmd == 'resume':
            if self.paused:
                voice.Resume()
                self.paused = False
            return {}
        if cmd == 'done':
            wait = max(0, min(LONGEST_WAIT_MS, int(request.get('ms', 0))))
            return {'done': bool(voice.WaitUntilDone(wait))}
        if cmd == 'quit':
            return {}
        return {'ok': False, 'error': 'Unknown request.'}


def write(stream, message):
    stream.write((json.dumps(message, ensure_ascii=True) + '\n').encode('ascii'))
    stream.flush()


def read_lines(source, requests, finish):
    """Reads requests on a thread of its own, so the end of input is seen even while
    the voice is busy."""
    try:
        for line in iter(source.readline, b''):
            requests.put(line)
    except (OSError, ValueError):
        pass
    finish(requests)


def finish_softly(requests):
    """None in the queue ends serve() once the request before it is answered."""
    requests.put(None)


def finish_for_sure(requests, grace=2.0):
    """In the real program: if the voice is stuck inside a call, serve() never reads the
    end mark, so the program leaves by itself a moment later."""
    requests.put(None)
    timer = threading.Timer(grace, os._exit, args=(0,))
    timer.daemon = True
    timer.start()


def parent_alive(pid):
    if sys.platform != 'win32':
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) != 0   # 0: the process has ended
    finally:
        kernel32.CloseHandle(handle)


def watch_parent(pid, requests, finish, alive=parent_alive, every=1.0):
    while alive(pid):
        time.sleep(every)
    finish(requests)


def serve(source, output, make_voice=sapi_voice, pump=pump, parent=None, finish=finish_softly):
    """Runs until quit, the end of input, or the parent program ends. Returns the exit code."""
    try:
        host = Host(make_voice())
    except Exception as exc:
        write(output, {'event': 'ready', 'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)})
        return 2
    write(output, {'event': 'ready', 'ok': True, 'bits': 64 if sys.maxsize > 2 ** 32 else 32})
    requests = queue.Queue()
    threading.Thread(target=read_lines, args=(source, requests, finish), daemon=True, name='Requests').start()
    if parent:
        threading.Thread(target=watch_parent, args=(parent, requests, finish), daemon=True, name='Parent').start()
    while True:
        try:
            line = requests.get(timeout=0.05)
        except queue.Empty:
            pump()
            continue
        if line is None:
            return 0
        request_id = None
        try:
            request = json.loads(line.decode('utf-8'))
            if not isinstance(request, dict):
                raise ValueError('A request must be an object.')
            request_id = request.get('id')
            answer = {'id': request_id, 'ok': True}
            answer.update(host.handle(request))
        except Exception as exc:
            answer = {'id': request_id, 'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}
        try:
            write(output, answer)
        except (OSError, ValueError):
            return 0
        if answer.get('ok') and request.get('cmd') == 'quit':
            return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parent = None
    if '--parent' in argv:
        try:
            parent = int(argv[argv.index('--parent') + 1])
        except (IndexError, ValueError):
            parent = None
    code = serve(sys.stdin.buffer, sys.stdout.buffer, parent=parent, finish=finish_for_sure)
    # Leave at once: a voice that stopped answering must not keep this program open.
    sys.stdout.flush()
    os._exit(code)


if __name__ == '__main__':
    main()
