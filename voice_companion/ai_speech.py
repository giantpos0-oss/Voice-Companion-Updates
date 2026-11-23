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


class ContinuousOutput:
    """One sound device stream that plays without stopping (Will, November 17, 2026: quick key
    presses still lagged). Phrases are added to a buffer the device reads from; an interruption
    empties the buffer, so the next phrase starts at once, with no stopping and restarting."""

    def __init__(self, rate=24000):
        # 24 kHz for eSpeak and ReadSpeaker; 44.1 kHz for Supertonic, played as made (Will,
        # November 23, 2026: studio-quality voices, 44 to 48 kHz, are essential).
        self.rate = int(rate)
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.paused = False
        self.stream = None
        self.description = ''

    def callback(self, outdata, frames, time_info, status):
        # Runs on the sound device's thread: only copy bytes here.
        need = len(outdata)
        with self.lock:
            if self.paused:
                chunk = b''
            else:
                chunk = bytes(self.buffer[:need])
                del self.buffer[:need]
        if chunk:
            outdata[:len(chunk)] = chunk
        if len(chunk) < need:
            outdata[len(chunk):need] = bytes(need - len(chunk))

    def add(self, pcm):
        with self.lock:
            self.buffer += pcm

    def clear(self):
        with self.lock:
            self.buffer.clear()

    def queued(self):
        with self.lock:
            return len(self.buffer)

    def open(self, factory=None):
        """Opens the stream: Windows audio (WASAPI) first, for the shortest delay, then the
        default device. Returns False if neither opens."""
        for name, factory, options in self.attempts(factory):
            stream = None
            try:
                stream = factory(samplerate=self.rate, channels=1, dtype='int16', blocksize=self.rate // 50,
                                 latency='low', callback=self.callback, **options)
                stream.start()
            except Exception:
                try:
                    if stream is not None: stream.close()
                except Exception:
                    pass
                continue
            self.stream = stream
            latency = getattr(stream, 'latency', None)
            self.description = name + (' (%d ms)' % round(latency * 1000) if isinstance(latency, (int, float)) else '')
            return True
        return False

    @staticmethod
    def attempts(factory=None):
        """(name, stream maker, options) to try in order."""
        if factory is not None:
            return [('the sound device', factory, {})]
        import sounddevice
        found = []
        try:
            for api in sounddevice.query_hostapis():
                if 'WASAPI' in api.get('name', '') and api.get('default_output_device', -1) >= 0:
                    found.append(('Windows audio (WASAPI)', sounddevice.RawOutputStream,
                                  {'device': api['default_output_device'],
                                   'extra_settings': sounddevice.WasapiSettings(auto_convert=True)}))
        except Exception:
            pass
        return found + [('the default sound device', sounddevice.RawOutputStream, {})]

    def broken(self):
        stream = self.stream
        return stream is None or getattr(stream, 'active', True) is False

    def close(self):
        stream, self.stream = self.stream, None
        self.clear()
        if stream is not None:
            try: stream.abort()
            except Exception: pass
            try: stream.close()
            except Exception: pass


def chunks(audio):
    """A phrase as pieces of sound: a synthesizer may hand back all of it, or pieces as it makes them."""
    if isinstance(audio, (bytes, bytearray, memoryview)):
        yield bytes(audio)
    else:
        yield from audio


def rate_of(audio):
    """The sample rate of sound from a synthesizer: 24 kHz unless it says otherwise."""
    return int(getattr(audio, 'sample_rate', 24000) or 24000)


class RatedBytes(bytes):
    """Sound kept whole (made ahead, or kept) that still knows its sample rate."""
    sample_rate = 24000


def whole(audio):
    if isinstance(audio, (bytes, bytearray)) and rate_of(audio) == 24000:
        return audio
    made = RatedBytes(audio if isinstance(audio, (bytes, bytearray)) else b''.join(chunks(audio)))
    made.sample_rate = rate_of(audio)
    return made


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
        self._device = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def speak(self, text, rate=0, volume=100):
        with self.lock:
            self.pending.put((self.generation, text, rate, volume))

    def interrupt(self):
        with self.lock:
            self.generation += 1
            self.paused = False
            device = self._device
            if device is not None:
                device.clear()          # silent within one 20 ms block
                device.paused = False
            while not self.pending.empty():
                try: self.pending.get_nowait()
                except queue.Empty: break
        # A synthesizer that makes a sentence at a time (Supertonic) stops making it now, so the
        # key press is spoken at once instead of after the rest of that sentence.
        hook = getattr(self, 'on_interrupt', None)
        if hook is not None:
            try: hook()
            except Exception: pass

    def close(self):
        self.interrupt()
        self.pending.put(None)

    # The stream stays open for as long as Companion runs (Will, November 17, 2026: no start-up
    # delay before speech, ever). It is reopened only if the sound device fails.
    _out = None          # class defaults, so a player made without __init__ still works
    _out_entered = False
    _ahead = None        # the next phrase, made while this one plays
    _device = None       # ContinuousOutput, when the real sound device is used
    _device_failed = False

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
            try: holder['audio'] = whole(self.synthesizer(part, job[2]))
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

    _out_rate = 24000

    def _stream(self, rate=24000):
        """The open output stream, opened (or restarted after an interruption) when needed, at the
        sample rate of the sound to play (reopened when another voice needs another rate)."""
        if self._out is not None and self._out_rate != rate:
            self._close_stream()
        if self._out is None:
            if self.output_factory is None:
                import sounddevice
                factory, options = sounddevice.RawOutputStream, {'latency': 'low'}
            else:
                factory, options = self.output_factory, {}
            stream = factory(samplerate=rate, channels=1, dtype='int16', blocksize=rate // 50, **options)
            self._out_rate = rate
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

    def _continuous(self, rate=24000):
        """The always-running device stream, or None to use a stream written to directly
        (tests give an output_factory; and the fallback if the callback stream cannot open)."""
        if self.output_factory is not None and not getattr(self.output_factory, 'continuous', False):
            return None
        if self._device is not None and not self._device.broken() and self._device.rate == rate:
            return self._device
        if self._device is not None:
            self._device.close(); self._device = None
        if self._device_failed:
            return None
        device = ContinuousOutput(rate)
        if device.open(self.output_factory):
            self._device = device
            return device
        self._device_failed = True
        return None

    def pause(self):
        with self.lock:
            self.paused = True
            if self._device is not None: self._device.paused = True

    def resume(self):
        with self.lock:
            self.paused = False
            if self._device is not None: self._device.paused = False

    def busy(self):
        with self.lock:
            device = self._device
            return self.active or not self.pending.empty() or (device is not None and device.queued() > 0)

    def _wait(self, generation):
        while True:
            with self.lock:
                if generation != self.generation: return False
                if not self.paused: return True
            time.sleep(0.02)

    @staticmethod
    def _scaled(piece, volume):
        if volume == 100:
            return piece
        import array
        samples = array.array('h', piece[:len(piece) - len(piece) % 2])
        return array.array('h', (int(v * volume / 100) for v in samples)).tobytes()

    def _play(self, audio, generation, volume):
        pieces = chunks(audio)
        rate = rate_of(audio)
        try:
            device = self._continuous(rate)
            if device is not None:
                # Added to the running stream: no waiting for it to finish, so the next phrase
                # follows with no gap. An interruption empties the stream (interrupt()).
                for piece in pieces:
                    if not self._wait(generation):
                        return
                    piece = self._scaled(piece, volume)
                    with self.lock:
                        # Checked under the same lock interrupt() takes, so sound from before a
                        # key press can never slip in after the stream was emptied.
                        if generation != self.generation:
                            return
                        device.add(piece)
                return
            stream = self._stream(rate)
            step = rate // 25 * 2          # 40 ms a write, at any sample rate
            for piece in pieces:
                piece = self._scaled(piece, volume)
                for start in range(0, len(piece), step):
                    if not self._wait(generation):
                        # Interrupted: drop what is still queued in the device at once.
                        if hasattr(stream, 'abort'): stream.abort()
                        return
                    stream.write(piece[start:start + step])
        except Exception:
            # A device that went away (headset unplugged): open a fresh stream next time.
            self._close_stream()
            if self._device is not None:
                self._device.close(); self._device = None
            raise
        finally:
            close = getattr(pieces, 'close', None)
            if close: close()      # a synthesizer still making sound stops here

    def _run(self):
        fallback = None
        while True:
            job = self.pending.get()
            if job is None:
                self._close_stream()
                if self._device is not None: self._device.close()
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
                        last = start + 1800 >= len(text)
                        # Sound handed out in pieces is made while it plays: the next phrase is
                        # started after it, so it never takes the synthesizer first.
                        ahead_first = isinstance(audio, (bytes, bytearray))
                        if last and ahead_first: self._prefetch(generation)
                        if self._wait(generation): self._play(audio, generation, volume)
                        if last and not ahead_first: self._prefetch(generation)
                    except Exception as exc:
                        if self.error_callback is not None:
                            try: self.error_callback(exc)
                            except Exception: pass
                        if not self._wait(generation): break
                        if fallback is None: fallback = self.fallback_factory()
                        fallback.Rate, fallback.Volume = rate, volume
                        # The name of the voice that failed: it may change while Companion runs.
                        name = self.engine_name() if callable(self.engine_name) else self.engine_name
                        fallback.Speak(name + ' unavailable. Using Windows speech. ' + part, 1)
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
