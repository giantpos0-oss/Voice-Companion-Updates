"""The Windows voice (SAPI) on a thread of its own, so a voice that stops answering can never stop
Voice Companion.

Will, November 1, 2026: Companion started, said its welcome, then did nothing. The window still echoed
his keys, so it seemed stuck in a typing mode. The main loop had asked the Windows voice to stop
talking (Speak with purge), and the voice never answered: freeze-report.txt showed the main thread
inside ISpeechVoice.Speak. Every key waited behind it.

SpeechWorker looks like the SAPI.SpVoice object the app used before (Speak, Pause, Resume,
WaitUntilDone, Rate, Volume, Voice, GetVoices), so the rest of the app is unchanged. But each call
only puts a job in a queue and returns at once; the voice itself lives on the worker thread. If one
call takes longer than STUCK_SECONDS, that voice is given up and a fresh one is made with the same
rate, volume and voice, so speech comes back by itself. Questions (WaitUntilDone) wait at most
ANSWER_SECONDS and then answer "done", so nothing can wait on a stuck voice.
"""
import collections
import threading
import time


class VoiceToken:
    """A Windows voice, by its Id and name: what GetVoices().Item(i) and .Voice gave before."""

    def __init__(self, voice_id, description):
        self.Id = voice_id
        self.description = description

    def GetDescription(self):
        return self.description

    def __eq__(self, other):
        return isinstance(other, VoiceToken) and other.Id == self.Id

    def __hash__(self):
        return hash(self.Id)

    def __repr__(self):
        return 'VoiceToken(%r)' % self.description


class VoiceList:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.Count = len(self.tokens)

    def Item(self, index):
        return self.tokens[index]


def sapi_voice():
    """The real voice, made on the thread that uses it."""
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


class SpeechWorker:
    STUCK_SECONDS = 6.0     # one call this long: the voice is given up and a new one made
    ANSWER_SECONDS = 0.3    # the longest a question to the voice waits
    READY_SECONDS = 5.0     # at start, how long to wait for the list of voices

    def __init__(self, factory=sapi_voice, clock=time.monotonic, pump=pump):
        self.factory, self.clock, self.pump = factory, clock, pump
        self.lock = threading.Condition()
        self.jobs = collections.deque()
        self.rate, self.volume = 0, 100
        self.voices = []
        self.current = VoiceToken('', 'Windows voice')
        self.generation = 0
        self.busy_since = None
        self.restarts = 0
        self.problem = None
        self.ready = threading.Event()
        self._start()
        self.ready.wait(self.READY_SECONDS)

    # ------------------------------------------------------------------ the worker thread
    def _start(self):
        with self.lock:
            self.generation += 1
            generation = self.generation
            self.busy_since = None
        thread = threading.Thread(target=self._run, args=(generation,), daemon=True,
                                  name='Windows voice %d' % generation)
        thread.start()

    def _run(self, generation):
        try:
            self.busy_since = self.clock()
            voice = self.factory()
            if generation != self.generation:
                return
            tokens = voice.GetVoices()
            found = [VoiceToken(tokens.Item(i).Id, tokens.Item(i).GetDescription()) for i in range(tokens.Count)]
            with self.lock:
                self.voices = found
                if self.restarts == 0:
                    try:
                        self.current = VoiceToken(voice.Voice.Id, voice.Voice.GetDescription())
                    except Exception:
                        pass
                rate, volume, wanted = self.rate, self.volume, self.current.Id
            if wanted:
                self._choose(voice, wanted)
            voice.Rate, voice.Volume = rate, volume
            self.busy_since = None
            self.ready.set()
        except Exception as exc:
            self.problem = type(exc).__name__
            if generation == self.generation:
                # No voice thread is left: count it as stuck from now, so a later call after
                # STUCK_SECONDS tries to make a voice again instead of staying silent for good.
                self.busy_since = self.clock()
            self.ready.set()
            return
        while generation == self.generation:
            with self.lock:
                if not self.jobs:
                    self.lock.wait(0.05)
                job = self.jobs.popleft() if self.jobs and generation == self.generation else None
                if job is not None:
                    self.busy_since = self.clock()
            if job is None:
                self.pump()
                continue
            try:
                self._do(voice, job)
            except Exception as exc:
                self.problem = type(exc).__name__
                answer = job[-1] if job[0] == 'ask' else None
                if answer is not None:
                    answer.set()
            finally:
                if generation == self.generation:
                    self.busy_since = None

    def _choose(self, voice, voice_id):
        tokens = voice.GetVoices()
        for i in range(tokens.Count):
            if tokens.Item(i).Id == voice_id:
                voice.Voice = tokens.Item(i)
                return

    def _do(self, voice, job):
        kind = job[0]
        if kind == 'speak':
            voice.Speak(job[1], job[2])
        elif kind == 'pause':
            voice.Pause()
        elif kind == 'resume':
            voice.Resume()
        elif kind == 'rate':
            voice.Rate = job[1]
        elif kind == 'volume':
            voice.Volume = job[1]
        elif kind == 'voice':
            self._choose(voice, job[1])
        elif kind == 'ask':
            _, method, args, holder, answered = job
            holder.append(getattr(voice, method)(*args))
            answered.set()

    # ------------------------------------------------------------------ from the app's threads
    def stuck(self):
        """True when the voice has not answered one call for STUCK_SECONDS; it is then replaced."""
        since = self.busy_since
        if since is None or self.clock() - since < self.STUCK_SECONDS:
            return False
        self.restarts += 1
        self._start()
        return True

    def _put(self, job, purge=False):
        self.stuck()
        with self.lock:
            if purge:
                # Stop means stop: speech still waiting is dropped, settings are kept. Pause and
                # Resume are kept in pairs: SAPI stays paused until Resume, even after a purge, so
                # a dropped Resume left the voice silent for good (interrupt_speech after Pause).
                self.jobs = collections.deque(j for j in self.jobs if j[0] != 'speak')
            self.jobs.append(job)
            self.lock.notify()

    def Speak(self, text, flags=0):
        self._put(('speak', str(text), int(flags)), purge=bool(int(flags) & 2))
        return 0

    def Pause(self):
        self._put(('pause',))

    def Resume(self):
        self._put(('resume',))

    def WaitUntilDone(self, milliseconds=0):
        """True when nothing is being said. A voice that does not answer counts as done."""
        since = self.busy_since
        if since is not None and self.clock() - since > 0.25:
            self.stuck()
            return True   # the voice is busy with a call that is not answering: never wait on it
        holder, answered = [], threading.Event()
        self._put(('ask', 'WaitUntilDone', (int(milliseconds),), holder, answered))
        if not answered.wait(self.ANSWER_SECONDS + max(0, int(milliseconds)) / 1000) or not holder:
            return True
        return bool(holder[0])

    @property
    def Rate(self):
        return self.rate

    @Rate.setter
    def Rate(self, value):
        self.rate = int(value)
        self._put(('rate', self.rate))

    @property
    def Volume(self):
        return self.volume

    @Volume.setter
    def Volume(self, value):
        self.volume = int(value)
        self._put(('volume', self.volume))

    @property
    def Voice(self):
        return self.current

    @Voice.setter
    def Voice(self, token):
        voice_id = getattr(token, 'Id', None)
        if not voice_id:
            return
        self.current = next((t for t in self.voices if t.Id == voice_id), None) or \
            VoiceToken(voice_id, token.GetDescription() if hasattr(token, 'GetDescription') else str(voice_id))
        self._put(('voice', voice_id))

    def GetVoices(self):
        return VoiceList(self.voices or [self.current])
