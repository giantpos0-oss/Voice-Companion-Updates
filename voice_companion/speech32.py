"""32-bit Windows voices, such as NeoSpeech "VW Paul", for the 64-bit Voice Companion.

Will, November 2026: his voices VW James, VW Kate and VW Paul never showed in the
voice list. They are 32-bit only, and Windows offers a 64-bit program only the
64-bit voices. Now a small 32-bit program, VoiceCompanion-Speech32.exe
(speech32_host.py), speaks with them, as NVDA does.

- with_32bit_voices(voice) wraps a SAPI.SpVoice. When this computer has no voice
  that exists only in the 32-bit part of the registry, it returns the voice
  unchanged, so nothing is different from before.
- Otherwise it returns a HybridVoice. It looks like SAPI.SpVoice (Speak, Pause,
  Resume, WaitUntilDone, Rate, Volume, Voice, GetVoices). GetVoices lists the
  64-bit voices and then each 32-bit-only voice, never one name twice (the
  64-bit one wins). Choosing a 32-bit voice starts the helper. Every call then
  goes to the helper; choosing a 64-bit voice goes back to the 64-bit voice.
- The helper never stops speech for good. When it is missing, does not start,
  ends or stops answering, the 64-bit voice speaks again. It says once, in plain
  words, which voice is speaking now, and the reason goes into
  speech-helper-log.txt in the data folder. The chosen voice is kept, so it is
  tried again at the next start or when it is chosen again.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

PREFIX = 'speech32:'
HELPER_NAME = 'VoiceCompanion-Speech32.exe'
TOKENS_PATH = r'SOFTWARE\Microsoft\Speech\Voices\Tokens'
SPEAK_ASYNC, SPEAK_PURGE = 1, 2
ANNOUNCE_AGAIN_SECONDS = 60.0
VENDOR_WORDS = frozenset(('microsoft', 'vw', 'neospeech', 'voiceware', 'desktop', 'code', 'factory', 'sapi', 'sapi5'))


class Token32:
    """A voice the helper speaks with: Id is PREFIX + its registry token Id."""

    def __init__(self, voice_id, description):
        self.Id = voice_id
        self.description = description

    def GetDescription(self):
        return self.description

    def __eq__(self, other):
        return getattr(other, 'Id', None) == self.Id

    def __hash__(self):
        return hash(self.Id)

    def __repr__(self):
        return 'Token32(%r)' % self.description


class VoiceList:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.Count = len(self.tokens)

    def Item(self, index):
        return self.tokens[index]


def token_name(token_id):
    """The last part of a token Id: 'HKEY_LOCAL_MACHINE\\...\\Tokens\\VW Paul' -> 'vw paul'."""
    text = str(token_id)
    if text.startswith(PREFIX):
        text = text[len(PREFIX):]
    return text.replace('/', '\\').rstrip('\\').rsplit('\\', 1)[-1].casefold()


def short_name(description):
    """'VW Paul' -> 'Paul'; 'Microsoft David Desktop - English (United States)' -> 'David'."""
    part = str(description or '').split(' - ')[0].strip()
    words = [word for word in part.split() if word.casefold() not in VENDOR_WORDS]
    return ' '.join(words) or part or 'The voice'


# ---------------------------------------------------------------------- the registry
def _tokens_in_view(registry, view):
    found = {}
    try:
        key = registry.OpenKey(registry.HKEY_LOCAL_MACHINE, TOKENS_PATH, 0, registry.KEY_READ | view)
    except OSError:
        return found
    with key:
        index = 0
        while True:
            try:
                name = registry.EnumKey(key, index)
            except OSError:
                break
            index += 1
            description = name
            try:
                with registry.OpenKey(key, name) as token:
                    value = registry.QueryValueEx(token, '')[0]
                    if isinstance(value, str) and value.strip():
                        description = value.strip()
            except OSError:
                pass
            found[name] = description
    return found


def thirty_two_bit_only_voices(registry=None):
    """Voices in the 32-bit view of the registry and not in the 64-bit view."""
    if registry is None:
        try:
            import winreg as registry
        except ImportError:
            return []
    try:
        v32 = _tokens_in_view(registry, registry.KEY_WOW64_32KEY)
        v64 = {name.casefold() for name in _tokens_in_view(registry, registry.KEY_WOW64_64KEY)}
    except Exception:
        return []
    return [Token32(PREFIX + 'HKEY_LOCAL_MACHINE\\' + TOKENS_PATH + '\\' + name, description)
            for name, description in sorted(v32.items(), key=lambda item: item[1].casefold())
            if name.casefold() not in v64]


# ---------------------------------------------------------------------- notices
def data_folder():
    return Path(os.getenv('VOICE_COMPANION_DATA_DIR') or
                Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'VoiceCompanion')


def log_problem(text, folder=None):
    """Adds one line to speech-helper-log.txt; keeps the last 200 lines. Never raises."""
    try:
        from storage import write_text_atomic
        path = Path(folder or data_folder()) / 'speech-helper-log.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_text(encoding='utf-8', errors='replace').splitlines() if path.exists() else []
        line = time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + str(text)
        write_text_atomic(path, '\n'.join((old + [line])[-200:]) + '\n')
    except Exception:
        pass


_announced = {}
_announced_lock = threading.Lock()


KILL_GRACE_SECONDS = 3.0   # the helper exits by itself within 2 seconds of its input closing


def first_notice(message, clock=time.monotonic):
    """True the first time a message is due. The window's voice and the keyboard voice
    each have a helper; when both fail together, the user hears it once."""
    with _announced_lock:
        now = clock()
        last = _announced.get(message)
        if last is not None and now - last < ANNOUNCE_AGAIN_SECONDS:
            return False
        _announced[message] = now
        return True


# ---------------------------------------------------------------------- the helper process
def helper_path():
    custom = os.getenv('VOICE_COMPANION_SPEECH32')
    if custom:
        return Path(custom)
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    return base / HELPER_NAME


def helper_command():
    return [str(helper_path()), '--parent', str(os.getpid())]


class Speech32Client:
    """Talks to one VoiceCompanion-Speech32.exe. Nothing here waits on the helper for
    longer than the caller asks, so a helper that stops answering never stops the app."""
    START_SECONDS = 15.0   # the first start of a one-file program can be slow (virus scan)
    HANG_SECONDS = 5.0     # a request not answered this long: the helper has stopped working

    def __init__(self, command=None, popen=subprocess.Popen, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.pending = {}
        self.next_id = 0
        self.outbox = queue.Queue()
        self.started = clock()
        self.ready = False
        self.ready_event = threading.Event()
        self.problem = None          # None, or (kind, detail); kind is 'start' or 'stopped'
        self.process = None
        try:
            self.process = popen(command or helper_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, shell=False,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, ValueError) as exc:
            self._fail('start', type(exc).__name__ + ': ' + str(exc))
            return
        threading.Thread(target=self._read, daemon=True, name='Speech32 answers').start()
        threading.Thread(target=self._write, daemon=True, name='Speech32 requests').start()

    # ---------------------------------------------------------------- threads
    def _read(self):
        stream = self.process.stdout
        try:
            for line in iter(stream.readline, b''):
                try:
                    message = json.loads(line.decode('utf-8', errors='replace'))
                except ValueError:
                    continue
                if not isinstance(message, dict):
                    continue
                if message.get('event') == 'ready':
                    if message.get('ok'):
                        with self.lock:
                            self.ready = True
                            self.ready_at = self.clock()
                    else:
                        self._fail('start', str(message.get('error') or 'The voice could not be made.'))
                    self.ready_event.set()
                    continue
                with self.lock:
                    entry = self.pending.pop(message.get('id'), None)
                if entry is not None:
                    entry[1].append(message)
                    entry[2].set()
        except (OSError, ValueError):
            pass
        code = self.process.poll()
        self._fail('stopped' if self.ready else 'start',
                   'The helper ended' + ('' if code is None else ' with exit code %s' % code) + '.')
        self.ready_event.set()

    def _write(self):
        while True:
            line = self.outbox.get()
            if line is None:
                break
            try:
                self.process.stdin.write(line)
                self.process.stdin.flush()
            except (OSError, ValueError) as exc:
                self._fail('stopped' if self.ready else 'start', 'Could not send to the helper: ' + type(exc).__name__)
                break
        try:
            self.process.stdin.close()
        except (OSError, ValueError):
            pass

    def _fail(self, kind, detail):
        with self.lock:
            if self.problem is None:
                self.problem = (kind, detail)
            for entry in self.pending.values():
                entry[2].set()
            self.pending.clear()

    # ---------------------------------------------------------------- from the app
    def failure(self):
        """None while the helper works; otherwise (kind, detail)."""
        if self.problem is not None:
            return self.problem
        now = self.clock()
        with self.lock:
            ready, ready_at = self.ready, getattr(self, 'ready_at', None)
            oldest = min((entry[0] for entry in self.pending.values()), default=None)
        if not ready:
            if now - self.started > self.START_SECONDS:
                self._fail('start', 'No answer within %d seconds.' % self.START_SECONDS)
        elif oldest is not None and now - max(oldest, ready_at) > self.HANG_SECONDS:
            self._fail('stopped', 'No answer within %d seconds.' % self.HANG_SECONDS)
        elif self.process is not None and self.process.poll() is not None:
            self._fail('stopped', 'The helper ended with exit code %s.' % self.process.poll())
        return self.problem

    def send(self, cmd, **fields):
        """Sends one request and returns at once: (answer list, answered event)."""
        holder, answered = [], threading.Event()
        with self.lock:
            if self.problem is not None:
                answered.set()
                return holder, answered
            self.next_id += 1
            request_id = self.next_id
            self.pending[request_id] = (self.clock(), holder, answered)
        fields.update(id=request_id, cmd=cmd)
        self.outbox.put((json.dumps(fields, ensure_ascii=True) + '\n').encode('ascii'))
        return holder, answered

    def ask(self, cmd, timeout, **fields):
        """The answer, or None when none came within timeout seconds."""
        holder, answered = self.send(cmd, **fields)
        answered.wait(timeout)
        return holder[0] if holder else None

    def wait_ready(self, timeout):
        self.ready_event.wait(timeout)
        return self.ready and self.problem is None

    def close(self, wait=1.0):
        """Asks the helper to stop; ends it if it does not."""
        if self.process is None:
            return
        if self.problem is None:
            self.send('quit')
        self.outbox.put(None)
        try:
            self.process.wait(wait)
        except Exception:
            self.kill()

    def kill(self):
        self._fail('stopped', 'Closed by Voice Companion.')
        self.outbox.put(None)
        if self.process is None:
            return
        process = self.process
        # Close its input first: the helper then exits by itself, and its one-file launcher
        # deletes the folder it unpacked in %TEMP%. A hard kill ends only the launcher and
        # leaves that folder behind (review, November 11, 2026). Kill only if it has not
        # gone after a moment, on a thread of its own, so nothing here waits.
        try:
            process.stdin.close()
        except Exception:
            pass

        def finish():
            try:
                process.wait(KILL_GRACE_SECONDS)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            try:
                process.stdout.close()
            except Exception:
                pass
        threading.Thread(target=finish, name='speech32-close', daemon=True).start()


def helper_voices(client_factory=None, wait=None):
    """For the voice check: ([(Id, name), ...], problem or None)."""
    client = (client_factory or Speech32Client)()
    try:
        if not client.wait_ready(client.START_SECONDS if wait is None else wait):
            problem = client.failure() or ('start', 'No answer.')
            return [], problem[1]
        answer = client.ask('list', 5.0)
        if not answer or not answer.get('ok'):
            return [], (answer or {}).get('error') or 'The helper did not list its voices.'
        return [(str(v.get('id', '')), str(v.get('name', ''))) for v in answer.get('voices', [])], None
    finally:
        client.close()


def machine_bits(path):
    """32 or 64 from a Windows program's header; None when it is not one."""
    with open(path, 'rb') as file:
        header = file.read(4096)
    if header[:2] != b'MZ' or len(header) < 0x40:
        return None
    offset = int.from_bytes(header[0x3c:0x40], 'little')
    if header[offset:offset + 4] != b'PE\0\0':
        return None
    machine = int.from_bytes(header[offset + 4:offset + 6], 'little')
    return {0x14c: 32, 0x8664: 64, 0xaa64: 64}.get(machine)


def check_helper(path=None, start=True):
    """The packaged check (--check-speech32): the helper is there, is a 32-bit program,
    starts, and lists its voices. Raises RuntimeError with the reason; returns the voices."""
    path = Path(path or helper_path())
    if not path.is_file():
        raise RuntimeError('The 32-bit speech helper is missing: ' + str(path))
    bits = machine_bits(path)
    if bits != 32:
        raise RuntimeError('The 32-bit speech helper is not a 32-bit program (%s).' % (bits or 'unknown'))
    if not start:
        return []
    voices, problem = helper_voices(lambda: Speech32Client([str(path), '--parent', str(os.getpid())]))
    if problem:
        raise RuntimeError('The 32-bit speech helper did not answer: ' + problem)
    return voices


# ---------------------------------------------------------------------- the voice the app uses
class HybridVoice:
    """Looks like SAPI.SpVoice; speaks with the helper while a 32-bit voice is chosen."""
    ANSWER_SECONDS = 0.25   # the longest one question to the helper waits

    def __init__(self, native, extra, client_factory=None, notify=None, log=log_problem):
        self._native = native
        self._extra = list(extra)
        self._client_factory = client_factory or (lambda: Speech32Client())
        self._notify = notify
        self._notice = None   # a fallback notice not yet safely heard
        self._log = log
        self._client = None
        self._chosen = None          # the 32-bit Token32 chosen, or None for a 64-bit voice
        self._fallen = False         # the chosen 32-bit voice failed: the 64-bit voice speaks
        self._rate = None
        self._volume = None
        self._unconfirmed = []       # words sent before the helper was ready
        self._voice_answer = None    # the helper's answer to choosing the voice, when it comes

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._native, name)

    def __setattr__(self, name, value):
        if name.startswith('_') or name in ('Rate', 'Volume', 'Voice'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._native, name, value)

    # ---------------------------------------------------------------- voices
    def _native_tokens(self):
        tokens = self._native.GetVoices()
        return [tokens.Item(i) for i in range(tokens.Count)]

    def GetVoices(self):
        native = self._native_tokens()
        names = {token_name(t.Id) for t in native}
        descriptions = {str(t.GetDescription()).casefold() for t in native}
        extra = []
        for token in self._extra:
            key = (token_name(token.Id), token.GetDescription().casefold())
            if key[0] in names or key[1] in descriptions:
                continue
            names.add(key[0])
            descriptions.add(key[1])
            extra.append(token)
        return VoiceList(native + extra)

    @property
    def Voice(self):
        return self._chosen if self._chosen is not None else self._native.Voice

    @Voice.setter
    def Voice(self, token):
        voice_id = str(getattr(token, 'Id', '') or '')
        if voice_id.startswith(PREFIX):
            chosen = next((t for t in self._extra if t.Id == voice_id), None) or \
                Token32(voice_id, token.GetDescription() if hasattr(token, 'GetDescription') else token_name(voice_id))
            self._use32(chosen)
            return
        if self._chosen is not None:
            self._leave32()
        native = token
        if not hasattr(token, '_oleobj_'):
            # A stand-in token (SpeechWorker's VoiceToken): give SAPI its own token.
            native = next((t for t in self._native_tokens() if str(t.Id) == voice_id), token)
        self._native.Voice = native

    def _use32(self, token):
        same = self._chosen is not None and self._chosen.Id == token.Id
        was_native = self._chosen is None or self._fallen
        self._chosen = token
        if same and self._client is not None and self._client.failure() is None:
            return
        if was_native:
            self._native.Speak('', SPEAK_ASYNC | SPEAK_PURGE)   # two voices must never talk at once
        if self._client is None or self._client.failure() is not None:
            if self._client is not None:
                self._client.kill()
            self._client = self._client_factory()
            self._unconfirmed = []
        self._fallen = False
        self._voice_answer = self._client.send('voice', voice=token.Id[len(PREFIX):])[0]
        self._client.send('rate', value=self.Rate)
        self._client.send('volume', value=self.Volume)
        self._active()   # a missing helper is noticed at once

    def _leave32(self):
        if self._client is not None and self._client.failure() is None:
            self._client.send('stop')
        self._chosen = None
        self._fallen = False
        self._unconfirmed = []

    def _active(self):
        """The helper when it should speak, or None for the 64-bit voice."""
        if self._chosen is None or self._fallen or self._client is None:
            return None
        problem = self._client.failure()
        if problem is None and self._voice_answer:
            answer, self._voice_answer = self._voice_answer[0], None
            if not answer.get('ok'):
                # The helper runs, but this voice will not load in it: never speak with
                # another voice without saying so.
                self._client.send('stop')
                problem = ('start', str(answer.get('error') or 'The voice could not be chosen.'))
        if problem is not None:
            self._fall_back(*problem)
            return None
        if self._client.ready:
            self._unconfirmed = []
        return self._client

    def _fall_back(self, kind, detail):
        client, self._client, self._fallen = self._client, None, True
        self._voice_answer = None
        if client is not None:
            client.kill()
        chosen = self._chosen.GetDescription() if self._chosen is not None else 'The voice'
        try:
            current = self._native.Voice.GetDescription()
        except Exception:
            current = 'the Windows voice'
        message = '%s %s, so Companion is using %s.' % (
            short_name(chosen), 'could not start' if kind == 'start' else 'stopped working', short_name(current))
        self._log('%s (%s): %s %s' % (chosen, kind, detail, message))
        replay, self._unconfirmed = (self._unconfirmed if kind == 'start' else []), []
        try:
            if first_notice(message):
                self._native.Speak(message, SPEAK_ASYNC | SPEAK_PURGE)
                # The very next speech often purges (keyboard echo, the app-wide speech
                # stop), which would cut this off unheard (review, November 11, 2026).
                # Keep it until something is spoken that cannot cut it off.
                self._notice = message
                if self._notify:
                    self._notify(message)
            for text in replay:
                self._native.Speak(text, SPEAK_ASYNC)   # never lose a sentence that was not heard
        except Exception:
            pass

    # ---------------------------------------------------------------- speech
    def Speak(self, text, flags=0):
        was_fallen = self._fallen
        client = self._active()
        if client is None:
            if self._fallen and not was_fallen:
                # The helper failed just now: do not cut off the notice that says so.
                flags = int(flags) & ~SPEAK_PURGE
            notice = getattr(self, '_notice', None)
            if notice and str(text):
                self._notice = None
                if int(flags) & SPEAK_PURGE:
                    # This would purge the notice: say it first, in the same speech.
                    text = notice + ' ' + str(text)
            return self._native.Speak(text, flags)
        flags = int(flags)
        if flags & SPEAK_PURGE:
            self._unconfirmed = []
        client.send('speak', text=str(text), flags=flags)
        if not client.ready and str(text):
            self._unconfirmed.append(str(text))
        if not flags & SPEAK_ASYNC:
            # Asked to wait until spoken, as SAPI does without the async flag.
            while self._active() is client and not self.WaitUntilDone(200):
                pass
        return 0

    def Pause(self):
        client = self._active()
        if client is None:
            return self._native.Pause()
        client.send('pause')

    def Resume(self):
        client = self._active()
        if client is None:
            return self._native.Resume()
        client.send('resume')

    def WaitUntilDone(self, milliseconds=0):
        client = self._active()
        if client is None:
            return self._native.WaitUntilDone(milliseconds)
        milliseconds = max(0, int(milliseconds))
        deadline = time.monotonic() + milliseconds / 1000
        while True:
            if not client.ready:
                if client.wait_ready(min(0.05, max(0, deadline - time.monotonic()))):
                    continue
                done = not self._unconfirmed
            else:
                step = max(0, min(1000, int((deadline - time.monotonic()) * 1000)))
                answer = client.ask('done', self.ANSWER_SECONDS + step / 1000, ms=step)
                # No answer counts as done: nothing may wait on a helper that is not answering.
                done = bool(answer.get('done', True)) if answer else True
            if done or time.monotonic() >= deadline or self._active() is not client:
                return done

    @property
    def Rate(self):
        return self._rate if self._rate is not None else self._native.Rate

    @Rate.setter
    def Rate(self, value):
        self._rate = int(value)
        self._native.Rate = self._rate
        if self._client is not None and self._client.failure() is None:
            self._client.send('rate', value=self._rate)

    @property
    def Volume(self):
        return self._volume if self._volume is not None else self._native.Volume

    @Volume.setter
    def Volume(self, value):
        self._volume = int(value)
        self._native.Volume = self._volume
        if self._client is not None and self._client.failure() is None:
            self._client.send('volume', value=self._volume)

    def close(self, wait=True):
        """Ends the helper: asks it first when wait is true; at once otherwise."""
        client, self._client = self._client, None
        if client is not None:
            client.close() if wait else client.kill()


def release(voice):
    """For a voice that is dropped: a HybridVoice ends its helper at once; others need nothing.
    Safe from any thread, even while the voice's own thread is stuck inside it."""
    if isinstance(voice, HybridVoice):
        voice.close(wait=False)


def with_32bit_voices(native, registry=None, **options):
    """The voice the app should use: native itself when no 32-bit-only voice exists."""
    extra = (registry or thirty_two_bit_only_voices)()
    return HybridVoice(native, extra, **options) if extra else native
