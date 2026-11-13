"""Microphone level: Companion makes sure the microphone is loud enough before it listens.

Windows often sets headset microphones, wired and wireless, very low. Will's Jabra Evolve
was at 19 percent, and speech was not understood until he raised it to about 70 in Sound
settings (Will, November 12, 2026). Companion now does that for the person.

This is not automatic gain: the level never moves up and down with the voice. When
Companion starts listening, and every few seconds while it listens, the Windows level of
the default microphone is checked. If it is below the level chosen in Options, it is set to
exactly that level. A level that is already higher is never lowered. "Leave as Windows has
it" turns this off. A muted microphone is never unmuted by Companion; the person is told.
"""
import os
import re
import threading
import time

OFF = 'leave as Windows has it'
LEVEL_CHOICES = (OFF, '50 percent', '60 percent', '70 percent', '80 percent', '90 percent', '100 percent')
DEFAULT_LEVEL = '70 percent'
CHECK_SECONDS = 10.0
TOLERANCE = 0.01

_NUMBER_WORDS = {'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90, 'one hundred': 100,
                 'a hundred': 100, 'hundred': 100, 'full': 100, 'maximum': 100, 'max': 100}


def target(choice):
    """The chosen level as 0.0 to 1.0, or None when Companion leaves the level alone."""
    choice = spoken_level(choice) or DEFAULT_LEVEL
    if choice == OFF:
        return None
    return int(choice.split()[0]) / 100.0


def spoken_level(value):
    """A level choice from speech or Options: "Seventy.", "80 percent", "100%", "off". None when not a choice."""
    text = re.sub(r'[^a-z0-9% ]+', ' ', str(value or '').lower()).replace('%', ' percent ')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return None
    if text in ('off', 'leave', 'leave it', 'leave as windows has it', 'leave it as windows has it', 'windows', 'do not change',
                "don't change", 'dont change', 'none', 'no change'):
        return OFF
    text = re.sub(r' ?percent$', '', text).strip()
    for words, number in _NUMBER_WORDS.items():
        if text == words:
            text = str(number)
    if text.isdigit():
        choice = '%d percent' % int(text)
        return choice if choice in LEVEL_CHOICES else None
    return None


def percent(level):
    return int(round(float(level) * 100))


def short_name(name):
    """ "Headset Microphone (Jabra Evolve 65)" says "Jabra Evolve 65 microphone"."""
    name = str(name or '').strip()
    inner = re.search(r'\(([^()]+)\)\s*$', name)
    if inner:
        name = inner.group(1).strip()
    name = re.sub(r'^\d+\s*-\s*', '', name)
    if not name:
        return 'Your microphone'
    return name if 'microphone' in name.lower() or 'mic' in name.lower().split() else name + ' microphone'


class MicrophoneKeeper:
    """Checks the default microphone's Windows level on its own thread; never makes speech wait."""

    def __init__(self, backend_factory, choice=lambda: DEFAULT_LEVEL, notify=None, log=None, clock=time.monotonic):
        self.backend_factory = backend_factory
        self.choice = choice
        self.notify = notify or (lambda text: None)
        self.log = log or (lambda text: None)
        self.clock = clock
        self.listening = False
        self.wake = threading.Event()
        self.closed = False
        self.thread = None
        self.told_raise = set()     # devices whose raise was already said this session
        self.told_mute = None       # device last said to be muted, until it is unmuted
        self.last = None            # (name, level, muted) from the last check, for "microphone level"
        self.problem = None

    # ----- from the main loop -----
    def listening_changed(self, listening):
        """The microphone was turned on (check at once) or off (stop checking)."""
        self.listening = bool(listening)
        if self.listening:
            self.told_mute = None
            self.wake.set()

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name='Microphone level', daemon=True)
            self.thread.start()
        return self

    def close(self):
        self.closed = True
        self.wake.set()

    def _run(self):
        initialize_com()
        while not self.closed:
            self.wake.wait(CHECK_SECONDS)
            self.wake.clear()
            if self.closed:
                return
            if self.listening:
                self.check()

    # ----- one check; tests call it directly -----
    def check(self):
        """Raise the default microphone to the chosen level when it is below it. Never raises."""
        wanted = target(self.choice())
        try:
            backend = self.backend_factory()
            name, level, muted = backend.default()
        except Exception as exc:
            if self.problem is None:
                self.log('Microphone level could not be read: ' + str(exc))
            self.problem = str(exc)
            return None
        self.problem = None
        said = None
        if wanted is not None and level < wanted - TOLERANCE:
            try:
                backend.set_level(wanted)
            except Exception as exc:
                self.log('Microphone level could not be set: ' + str(exc))
            else:
                self.log('Microphone level for %s raised from %d to %d percent' % (name, percent(level), percent(wanted)))
                if name not in self.told_raise:
                    self.told_raise.add(name)
                    said = '%s was at %d percent, so Voice Companion raised it to %d percent.' % (
                        short_name(name), percent(level), percent(wanted))
                level = wanted
        if muted and self.told_mute != name:
            self.told_mute = name
            mute = '%s is muted in Windows or on the headset. Unmute it so Voice Companion can hear you.' % short_name(name)
            said = (said + ' ' + mute) if said else mute
        elif not muted and self.told_mute == name:
            self.told_mute = None
        self.last = (name, level, muted)
        if said:
            self.notify(said)
        return said

    def report(self):
        """What "microphone level" says."""
        wanted = target(self.choice())
        try:
            name, level, muted = self.backend_factory().default()
        except Exception:
            return 'Voice Companion could not read the microphone level. Check that a microphone is plugged in.'
        text = '%s is at %d percent%s.' % (short_name(name), percent(level), ', and muted' if muted else '')
        if wanted is None:
            return text + ' Voice Companion leaves it as Windows has it. To have Companion raise it, say microphone level 70.'
        return text + ' Voice Companion raises it to at least %d percent while it listens.' % percent(wanted)


def initialize_com():
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)
    except Exception:
        pass


class WindowsMicrophone:
    """The default recording device (the one Companion listens to), through Windows Core Audio."""

    CLSID_MMDeviceEnumerator = '{BCDE0395-E52F-467C-8E3D-C4579291692E}'
    IID_IMMDeviceEnumerator = '{A95664D2-9614-4F35-A746-DE8DB63617E6}'
    IID_IAudioEndpointVolume = '{5CDF2C82-841E-4546-9722-0CF74078229A}'
    PKEY_FRIENDLY_NAME = ('{A45C254E-DF1C-4EFD-8020-67D146A850E0}', 14)

    def __init__(self):
        if os.name != 'nt':
            raise OSError('The microphone level can be set only on Windows.')
        import ctypes
        import uuid
        self.ctypes = ctypes

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16), ('Data3', ctypes.c_uint16),
                        ('Data4', ctypes.c_ubyte * 8)]

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [('fmtid', GUID), ('pid', ctypes.c_uint32)]

        self.GUID, self.PROPERTYKEY = GUID, PROPERTYKEY
        self.guid = lambda text: GUID.from_buffer_copy(uuid.UUID(text).bytes_le)
        self.context = self.guid('{9B1E4C7A-2F35-4D86-A1C0-7E5D3B2F6A18}')
        self.ole = ctypes.OleDLL('ole32')
        initialize_com()
        self.enumerator = ctypes.c_void_p()
        self.ole.CoCreateInstance(ctypes.byref(self.guid(self.CLSID_MMDeviceEnumerator)), None, 23,
                                  ctypes.byref(self.guid(self.IID_IMMDeviceEnumerator)), ctypes.byref(self.enumerator))

    def _call(self, pointer, index, argtypes, *args, restype=None):
        ctypes = self.ctypes
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        function = ctypes.WINFUNCTYPE(restype or ctypes.HRESULT, ctypes.c_void_p, *argtypes)(table[index])
        return function(pointer, *args)

    def _release(self, pointer):
        if pointer:
            try:
                self._call(pointer, 2, (), restype=self.ctypes.c_ulong)
            except Exception:
                pass

    def _endpoint(self):
        ctypes = self.ctypes
        device, volume = ctypes.c_void_p(), ctypes.c_void_p()
        # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eCapture = 1, eConsole = 0): the device
        # Windows gives programs that do not choose one, which is the one Companion records from.
        self._call(self.enumerator, 4, (ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)), 1, 0, ctypes.byref(device))
        try:
            # IMMDevice::Activate(IID_IAudioEndpointVolume, CLSCTX_ALL, NULL, &volume)
            self._call(device, 3, (ctypes.POINTER(self.GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                       ctypes.byref(self.guid(self.IID_IAudioEndpointVolume)), 23, None, ctypes.byref(volume))
            name = self._name(device)
        except Exception:
            self._release(volume)
            self._release(device)
            raise
        return device, volume, name

    def _name(self, device):
        ctypes = self.ctypes
        store = ctypes.c_void_p()
        try:
            self._call(device, 4, (ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)), 0, ctypes.byref(store))  # STGM_READ
            key = self.PROPERTYKEY(self.guid(self.PKEY_FRIENDLY_NAME[0]), self.PKEY_FRIENDLY_NAME[1])
            value = (ctypes.c_ubyte * 24)()   # PROPVARIANT: its type, then the text pointer at byte 8
            self._call(store, 5, (ctypes.POINTER(self.PROPERTYKEY), ctypes.c_void_p), ctypes.byref(key), ctypes.byref(value))
            try:
                kind = int.from_bytes(bytes(value[0:2]), 'little')
                text = ctypes.c_void_p.from_buffer(value, 8).value
                return ctypes.wstring_at(text) if kind == 31 and text else 'Your microphone'   # VT_LPWSTR
            finally:
                try:
                    self.ole.PropVariantClear(ctypes.byref(value))
                except Exception:
                    pass
        except Exception:
            return 'Your microphone'
        finally:
            self._release(store)

    def default(self):
        """(name, level from 0.0 to 1.0, muted) of the default microphone."""
        ctypes = self.ctypes
        device, volume, name = self._endpoint()
        try:
            level, muted = ctypes.c_float(), ctypes.c_int()
            self._call(volume, 9, (ctypes.POINTER(ctypes.c_float),), ctypes.byref(level))   # GetMasterVolumeLevelScalar
            self._call(volume, 15, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(muted))    # GetMute
            return name, max(0.0, min(1.0, float(level.value))), bool(muted.value)
        finally:
            self._release(volume)
            self._release(device)

    def set_level(self, level):
        ctypes = self.ctypes
        device, volume, _ = self._endpoint()
        try:
            self._call(volume, 7, (ctypes.c_float, ctypes.POINTER(self.GUID)),            # SetMasterVolumeLevelScalar
                       ctypes.c_float(max(0.0, min(1.0, float(level)))), ctypes.byref(self.context))
        finally:
            self._release(volume)
            self._release(device)
