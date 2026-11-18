"""Optional online narrator. No credentials or spoken content are saved to disk."""
from network_security import secure_service_open
import json
import os
import queue
import threading
import time
import urllib.request


def synthesize(text, rate=0, key=None, voice=None,pitch=0):
    key = key if key is not None else os.getenv('VOICE_COMPANION_OPENAI_KEY', '')
    if not key:
        raise ValueError('AI speech is not configured')
    options={} if not pitch else {'instructions':'Speak with '+('higher' if pitch>0 else 'lower')+' vocal pitch, intensity '+str(abs(pitch))+' out of 10. Keep the requested speaking speed.'}
    body = json.dumps(options | {'model': 'gpt-4o-mini-tts',
        'voice': voice or os.getenv('VOICE_COMPANION_AI_VOICE', 'coral'),
        'input': text, 'response_format': 'pcm',
        'speed': max(0.25, min(4.0, 1.0 + rate * 0.075))}).encode()
    request = urllib.request.Request('https://api.openai.com/v1/audio/speech',
        data=body, headers={'Authorization': 'Bearer ' + key,
                           'Content-Type': 'application/json'})
    with secure_service_open(request, timeout=8) as response:
        audio = response.read(16 * 1024 * 1024)
    if not audio or len(audio) % 2:
        raise ValueError('Invalid speech audio')
    return audio


class AISpeech:
    def __init__(self, fallback_factory, synthesizer=synthesize, output_factory=None, engine_name="AI voice", error_callback=None):
        self.engine_name = engine_name
        self.error_callback = error_callback
        self.fallback_factory = fallback_factory
        self.synthesizer = synthesizer
        self.output_factory = output_factory
        self.pending = queue.Queue()
        self.lock = threading.RLock()
        self.generation = 0
        self.paused = False
        self.active = False
        self.enabled = False
        # One output stream kept open between phrases (Will, November 17, 2026: keys lagged).
        # Opening a Windows audio stream for every key press cost a noticeable delay each time.
        self._out = None
        self._out_entered = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def speak(self, text, rate=0, volume=100):
        with self.lock:
            self.pending.put((self.generation, text, rate, volume))

    def interrupt(self):
        with self.lock:
            self.generation += 1
            self.paused = False
            while not self.pending.empty():
                try: self.pending.get_nowait()
                except queue.Empty: break

    def close(self):
        self.interrupt()
        self.pending.put(None)

    # The stream stays open for as long as Companion runs (Will, November 17, 2026: no start-up
    # delay before speech, ever). It is reopened only if the sound device fails.
    _out = None          # class defaults, so a player made without __init__ still works
    _out_entered = False
    _ahead = None        # the next phrase, made while this one plays

    @staticmethod
    def _part(text, start):
        part = text[start:start + 1800]
        if hasattr(text, 'pitch_delta'):
            from capital_feedback import CharacterSpeech
            part = CharacterSpeech(part, getattr(text, 'capital', False), text.pitch_delta)
        return part

    def _prefetch(self, generation):
        """Starts making the next queued phrase while this one plays, so sentences follow each
        other without a pause for the synthesizer (Will: "Exit Voice Companion. Are you sure?")."""
        with self.pending.mutex:
            job = self.pending.queue[0] if self.pending.queue else None
        if job is None or job[0] != generation or (self._ahead is not None and self._ahead['job'] is job):
            return
        holder = {'job': job, 'done': threading.Event()}
        part = self._part(job[1], 0)
        def work():
            try: holder['audio'] = self.synthesizer(part, job[2])
            except Exception as exc: holder['error'] = exc
            finally: holder['done'].set()
        self._ahead = holder
        threading.Thread(target=work, name='Next phrase', daemon=True).start()

    def _made(self, job, part, rate):
        """The sound for the first part of a job: the one made ahead if it is this job."""
        ahead, self._ahead = self._ahead, None
        if ahead is not None and ahead['job'] is job:
            ahead['done'].wait()
            if 'error' in ahead: raise ahead['error']
            return ahead['audio']
        return self.synthesizer(part, rate)

    def _stream(self):
        """The open output stream, opened (or restarted after an interruption) when needed."""
        if self._out is None:
            if self.output_factory is None:
                import sounddevice
                factory, options = sounddevice.RawOutputStream, {'latency': 'low'}
            else:
                factory, options = self.output_factory, {}
            stream = factory(samplerate=24000, channels=1, dtype='int16', blocksize=480, **options)
            if hasattr(stream, 'start'):
                stream.start()
                self._out_entered = False
            else:
                stream = stream.__enter__()
                self._out_entered = True
            self._out = stream
        elif getattr(self._out, 'active', True) is False and hasattr(self._out, 'start'):
            self._out.start()
        return self._out

    def _close_stream(self):
        stream, self._out = self._out, None
        if stream is None: return
        try:
            if self._out_entered: stream.__exit__(None, None, None)
            else:
                if hasattr(stream, 'abort'): stream.abort()
                stream.close()
        except Exception:
            pass

    def pause(self):
        with self.lock: self.paused = True

    def resume(self):
        with self.lock: self.paused = False

    def busy(self):
        with self.lock: return self.active or not self.pending.empty()

    def _wait(self, generation):
        while True:
            with self.lock:
                if generation != self.generation: return False
                if not self.paused: return True
            time.sleep(0.02)

    def _play(self, audio, generation, volume):
        import array
        samples = array.array('h', audio)
        if volume != 100:
            samples = array.array('h', (int(v * volume / 100) for v in samples))
        audio = samples.tobytes()
        try:
            stream = self._stream()
            for start in range(0, len(audio), 960):
                if not self._wait(generation):
                    # Interrupted: drop what is still queued in the device at once.
                    if hasattr(stream, 'abort'): stream.abort()
                    return
                stream.write(audio[start:start + 960])
        except Exception:
            # A device that went away (headset unplugged): open a fresh stream next time.
            self._close_stream()
            raise

    def _run(self):
        fallback = None
        while True:
            job = self.pending.get()
            if job is None:
                self._close_stream()
                return
            generation, text, rate, volume = job
            with self.lock: self.active = True
            try:
                # Small requests let silence commands take effect between audio blocks.
                for start in range(0, len(text), 1800):
                    part = self._part(text, start)
                    if not self._wait(generation): break
                    try:
                        audio = self._made(job, part, rate) if start == 0 else self.synthesizer(part, rate)
                        if start + 1800 >= len(text): self._prefetch(generation)
                        if self._wait(generation): self._play(audio, generation, volume)
                    except Exception as exc:
                        if self.error_callback is not None:
                            try: self.error_callback(exc)
                            except Exception: pass
                        if not self._wait(generation): break
                        if fallback is None: fallback = self.fallback_factory()
                        fallback.Rate, fallback.Volume = rate, volume
                        fallback.Speak(self.engine_name + ' unavailable. Using Windows speech. ' + part, 1)
                        was_paused = False
                        while not fallback.WaitUntilDone(0):
                            with self.lock:
                                if generation != self.generation:
                                    if was_paused: fallback.Resume()
                                    fallback.Speak('', 3)
                                    break
                                paused = self.paused
                            if paused != was_paused:
                                (fallback.Pause if paused else fallback.Resume)()
                                was_paused = paused
                            time.sleep(0.02)
            except Exception:
                # Keep the worker alive if the audio device or fallback fails.
                pass
            finally:
                with self.lock: self.active = False
