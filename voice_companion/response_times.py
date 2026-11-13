"""How quickly Voice Companion answers keys and voice commands.

Keys and spoken commands should be answered at once (Will, November 12, 2026:
"response times on both ends should be snappier"). This module lets the main
loop wake the moment a key arrives, and writes a line to response-times.txt
whenever an answer took longer than SLOW_SECONDS, naming the slow step. Only
key names, the screen and times are written: never typed text or spoken words.
"""
import collections
import queue
import threading
import time

SLOW_SECONDS = 0.25
KEEP_LINES = 300
FILE_NAME = 'response-times.txt'


class CommandQueue(queue.Queue):
    """The window's command queue. Remembers when each item arrived and wakes
    the main loop at once (arrived), instead of after its next short wait."""

    def __init__(self, maxsize=0, clock=time.monotonic):
        super().__init__(maxsize)
        self.clock = clock
        self.arrived = threading.Event()
        self.times = collections.deque()
        self.oldest_taken = None   # arrival time of the first item taken since the last reset

    def _put(self, item):
        self.queue.append(item)
        self.times.append(self.clock())
        self.arrived.set()

    def _get(self):
        arrived = self.times.popleft() if self.times else None
        if self.oldest_taken is None:
            self.oldest_taken = arrived
        return self.queue.popleft()

    def take_oldest(self):
        """Arrival time of the first item taken since the last call, or None."""
        with self.mutex:
            value, self.oldest_taken = self.oldest_taken, None
        return value


def key_label(command):
    """A safe name for what was pressed: a key name, or a kind of input. Never the text."""
    if isinstance(command, tuple) and command:
        if command[0] == 'keyboard':
            key = str(command[1])
            return 'web page key' if key.startswith('Web:Pass:') else key
        return str(command[0]).replace('_', ' ')
    return 'typed command'


_STAGES = {}
_STAGES_LOCK = threading.Lock()


def add(stage, seconds):
    """Time spent in one step of the key being answered now (such as stopping the voice)."""
    with _STAGES_LOCK:
        _STAGES[stage] = _STAGES.get(stage, 0.0) + max(0.0, seconds)


def take():
    """The steps timed since the last take(), as [(name, seconds)], and start again."""
    with _STAGES_LOCK:
        steps = list(_STAGES.items())
        _STAGES.clear()
    return steps


class Log:
    """response-times.txt in Voice Companion's data folder. Never raises. Safe from any thread."""

    def __init__(self, folder=None, clock=time.monotonic, wall=time.strftime):
        self.folder, self.clock, self.wall = folder, clock, wall
        self.lines = None
        self.lock = threading.Lock()

    def slow(self, what, screen, steps):
        """steps: [(name, seconds)]. Written when they add up to more than SLOW_SECONDS."""
        total = sum(seconds for _, seconds in steps if seconds)
        if total <= SLOW_SECONDS or self.folder is None:
            return False
        parts = ', '.join('%s %.2f' % (name, seconds) for name, seconds in steps if seconds and seconds >= 0.01)
        line = '%s %s on %s: %.2f seconds (%s)' % (self.wall('%Y-%m-%d %H:%M:%S'), what, screen or 'unknown screen', total, parts)
        with self.lock:
            return self._write(line)

    def _write(self, line):
        try:
            from pathlib import Path
            path = Path(self.folder) / FILE_NAME
            if self.lines is None:
                try:
                    self.lines = path.read_text(encoding='utf-8').splitlines()[-KEEP_LINES:]
                except (OSError, UnicodeError):
                    self.lines = []
            self.lines = (self.lines + [line])[-KEEP_LINES:]
            from storage import write_text_atomic
            write_text_atomic(path, '\n'.join(self.lines) + '\n')
        except Exception:
            return False
        return True
