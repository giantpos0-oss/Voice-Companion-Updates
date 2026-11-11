"""The hands-on tutorial: each step asks for a real key or spoken command, checks it, and
answers the way the app would.

How it works:
- A lesson is a list of steps. Each step says what to do ("Press Down Arrow").
- While the tutorial is open, every key and every spoken or typed command comes here
  first (companion.navigation_key and companion._handle send them). Nothing reaches
  the real screens.
- A step checks the input. Right: short praise, the app's answer, the next step.
  Wrong: what was heard, what to do, and try again. After two misses it offers to
  show how or to skip.
- The screens in a lesson are simulations. Menus use the real menu classes
  (TaskNavigation, ScreenMenu) with a stand-in app that only records what was chosen.
  Writing uses the real document and email editors in a temporary folder that is
  deleted when the lesson ends. Nothing is sent, deleted, saved in your folders,
  changed in Options or opened on the web.
- Progress is kept in tutorial-progress.json in the app's data folder, so the
  tutorial can continue where you stopped.
"""
import json
import re
import shutil
import tempfile
from pathlib import Path

from menu_navigation import announce_item, bounded_index, next_match, spoken_key

MODE = 'tutorial'
# Keys reach _handle as this prefix and the key name, so they can never be taken for words.
KEY_PREFIX = '@tutorial-key:'
PROGRESS_FILE = 'tutorial-progress.json'

# Every phrase that ever opened a tutorial opens this one, so no old habit is stranded.
START_PHRASES = ('start tutorial', 'audio tutorial', 'practice tutorial', 'open tutorial', 'start the tutorial',
                 'open the tutorial', 'start lessons', 'start practice', 'start practice tutorial',
                 'open practice tutorial', 'interactive tutorial', 'start interactive tutorial',
                 'hands on tutorial', 'start hands on tutorial')
# These words alone are commands only on the main menu and in Help; in a document they are text.
ALONE_PHRASES = ('tutorial', 'lessons', 'practice')

REPEAT = ('repeat', 'repeat that', 'say that again', 'repeat step', 'repeat the step', 'what was that',
          'repeat instructions')
SKIP = ('skip', 'skip it', 'skip this', 'skip step', 'skip this step', 'skip the step')
SHOW = ('show me', 'show me how', 'how do i do that', 'how do i do it', 'what do i do', 'what do i say',
        'i do not know', 'i don t know', 'tell me how')
STOP = ('stop tutorial', 'stop the tutorial', 'stop practice', 'end tutorial', 'end the tutorial', 'quit tutorial',
        'exit tutorial', 'leave tutorial', 'close tutorial', 'close the tutorial', 'main menu', 'back to main menu',
        'go to main menu')
HELP = ('help', 'tutorial help', 'what can i say', 'what can i do', 'what are my choices', 'what are my options')
NEXT_LESSON = ('next lesson', 'next', 'continue', 'go on', 'okay', 'ok', 'that one', 'yes', 'yes please', 'confirm',
               'start lesson', 'start the lesson', 'start next lesson')
AGAIN = ('repeat lesson', 'repeat the lesson', 'start again', 'try again', 'again', 'lesson again')
LESSON_LIST = ('lesson list', 'list lessons', 'lessons', 'courses', 'course list', 'tutorial menu', 'choose a lesson',
               'choose lesson', 'back to lessons')
RESUME = ('continue where i stopped', 'continue where i left off', 'resume', 'continue tutorial', 'where i stopped',
          'pick up where i left off')
IN_ORDER = ('go in order', 'in order', 'start from the beginning', 'from the beginning', 'start at the beginning')
PICK = ('that one', 'okay', 'ok', 'confirm', 'confirm that', 'open', 'open it', 'yes', 'start', 'start it')
# Keys that keep their tutorial job (stop, main menu, help, exit) unless a step asks for them.
SPECIAL_KEYS = ('Escape', 'F1', 'Double:F1', 'Alt+F4')
PRAISE = ('Right.', 'Good.', 'Well done.', 'Correct.', 'That is it.')
# Words people add that most screens do not understand ("Next, please.").
POLITE = re.compile(r'^(?:(?:please|now|okay|ok|um|uh)\s+)+|(?:\s+(?:please|now|thanks|thank you))+$')

INTRO = ('Tutorial. You practice each step with the real keys and commands. '
         'Nothing here sends mail, changes your files, changes your settings, or opens websites. '
         'At any time, say repeat, skip, show me, or stop tutorial. Escape stops the tutorial. ')
HELP_TEXT = ('Tutorial help. Say repeat to hear the step again. Say show me to hear exactly how. '
             'Say skip to go on. Say stop tutorial, or press Escape, to stop. Your place is saved. '
             'F1 goes to the main menu. ')


def plain(text):
    """Words without punctuation or capitals, as the app compares commands."""
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', str(text).casefold())).strip()


def canonical_key(key):
    """One name for each key, whichever way the window sent it ('Letter:r' and 'R' are R)."""
    key = str(key)
    if key == 'settings':
        return 'Alt+O'      # Alt+O comes from the window as 'settings'
    if key.startswith('Letter:'):
        return key[7:].upper()
    return {'Return': 'Enter', 'space': 'Space', 'ISO_Left_Tab': 'ShiftTab', 'Shift+Tab': 'ShiftTab'}.get(key, key)


def key_words(key):
    """A key in the guide's words: 'Control+N', 'Down Arrow', 'F1 twice'."""
    key = canonical_key(key)
    if key == 'Control':
        return 'Control'
    return spoken_key(key)


def window_key(keysym, char, state):
    """The key name for a Tk key event while the tutorial is open, or None to ignore it.

    Modifier keys alone are ignored, except Control, which stops speech. A lone Alt is
    sent by the window when Alt is let go (screen_menus.alt_menu_key)."""
    from key_state import modifiers
    control, shift, alt = modifiers(state)
    if keysym in ('Control_L', 'Control_R'):
        return 'Control'
    if keysym in ('Shift_L', 'Shift_R', 'Alt_L', 'Alt_R', 'Caps_Lock', 'Num_Lock', 'Super_L', 'Super_R',
                  'Meta_L', 'Meta_R', 'Win_L', 'Win_R', 'ISO_Level3_Shift', 'Scroll_Lock'):
        return None
    if keysym == 'ISO_Left_Tab' or keysym == 'Tab' and shift and not control and not alt:
        return 'ShiftTab'
    names = {'Return': 'Enter', 'KP_Enter': 'Enter', 'space': 'Space', 'Page_Up': 'Prior', 'Page_Down': 'Next',
             'comma': 'comma', 'period': 'period'}
    name = names.get(keysym, keysym)
    if len(name) == 1:
        name = name.upper()
    prefix = ('Ctrl+' if control else '') + ('Alt+' if alt else '')
    if shift and (prefix or len(name) > 1 or name.isalpha()):
        # Shift alone with a letter is a capital letter key; with a named key it is part of the key.
        prefix += 'Shift+'
    return prefix + name


class Sandbox:
    """A stand-in for the app, for the real menu classes. It records speech and choices and does nothing else."""

    def __init__(self, app):
        self._app = app
        self.said = []
        self.requests = []
        self.PREFERENCES = {}
        self.MEDIA_SECTION = 'radio'
        self.document = self.email_draft = self.web_session = self.FILE_MANAGER = self.FILE_READER = None
        self.NAMED_LIST = self.ACCOUNT_PICKER = self.pending_send = self.MEDIA_HUB = None
        self.help_session = self.mail_session = object()
        self.tutorial_session = object()
        self.account_setup = False
        self.MAIN_MENU_INDEX = None
        self.MAIN_MENU_CHOICES = app.MAIN_MENU_CHOICES
        self.ACCOUNT_TYPE_PROMPT = getattr(app, 'ACCOUNT_TYPE_PROMPT', '')
        self.APP = Path(tempfile.gettempdir())

    def speak(self, text):
        self.said.append(text if isinstance(text, str) else str(text))

    def handle(self, command, mode, typed=False):
        self.requests.append(command)
        return mode

    def normalized_command(self, value):
        return self._app.normalized_command(value)

    def spoken_control(self, value):
        return self._app.spoken_control(value)

    def speech_control(self, value):
        return self._app.speech_control(value)

    def speech_setting_request(self, value):
        return self._app.speech_setting_request(value)

    def options_return_notice(self, mode):
        return self._app.options_return_notice(mode)

    def flush_note(self, *args, **kwargs):
        return None

    def media(self):
        """A player with nothing open, so the Media player menu says so and plays nothing."""
        from types import SimpleNamespace
        return SimpleNamespace(player=SimpleNamespace(kind=None))

    def take(self):
        """What was said since the last call, as one message, with its hint marks kept (hints.py)."""
        from hints import join
        text = join(' ', self.said)
        self.said.clear()
        return text


class Sim:
    """A simulated screen. feed() returns what the screen says, or None when it ignores the input."""
    title = ''
    chosen = None    # the command the user chose, when a choice was made

    def feed(self, kind, value):
        return None

    def menu(self):
        return None

    def close(self):
        pass


class MainMenuSim(Sim):
    """The main menu, with the real choices and the real words (checked against companion in the tests)."""
    title = 'Main menu'

    def __init__(self, app):
        self.app = app
        self.choices = app.MAIN_MENU_CHOICES
        self.index = 0      # the main menu opens on its first item (companion.announce_main_menu)

    def names(self):
        return [name for name, _ in self.choices]

    def item(self, index):
        return announce_item(self.choices[index][0], index, len(self.choices))

    def menu(self):
        return self.names(), self.index, lambda i: setattr(self, 'index', i)

    def choose(self, index):
        self.chosen = self.choices[index][1]
        self.index = None
        return 'That opens ' + self.choices[index][0] + '.'

    def feed(self, kind, value):
        count = len(self.choices)
        if kind == 'key':
            key = canonical_key(value)
            if key in ('Down', 'Right', 'Up', 'Left'):
                step = 1 if key in ('Down', 'Right') else -1
                new = bounded_index(self.index, step, count)
                if new == self.index:
                    return 'Start of list.' if step < 0 else 'End of list.'
                self.index = new
                return self.item(new)
            if key in ('Home', 'End'):
                new = 0 if key == 'Home' else count - 1
                if new == self.index:
                    return 'Start of list.' if key == 'Home' else 'End of list.'
                self.index = new
                return self.item(new)
            if len(key) == 1 and key.isalpha():
                new = next_match(self.names(), self.index, key)
                if new is None:
                    return 'No menu item starts with ' + key + '.'
                if new == self.index:
                    return 'End of matching items.'
                self.index = new
                return self.item(new)
            if key == 'Enter':
                if self.index is None:
                    return 'Say next or previous to choose an option.'
                return self.choose(self.index)
            if key == 'Alt':
                # The main menu is already a menu: Alt says where you are (ScreenMenu.other_alt).
                if self.index is None:
                    self.index = 0
                return 'Main menu. ' + self.item(self.index)
            return None
        command = plain(value)
        if command in ('next', 'previous'):
            self.index = bounded_index(self.index, 1 if command == 'next' else -1, count)
            return self.item(self.index)
        if command in self.app.PICK_CONFIRM:
            if self.index is None:
                return 'Say next or previous to choose an option.'
            return self.choose(self.index)
        for index, (name, voice) in enumerate(self.choices):
            if command in (plain(name), voice):
                return self.choose(index)
        return None


class TaskMenuSim(Sim):
    """A list menu (Office tools, Word processor menu, Notepad menu...) run by the real TaskNavigation."""

    def __init__(self, app, mode, title):
        from task_navigation import TaskNavigation
        sandbox = self.sandbox = Sandbox(app)
        sim = self

        class Navigation(TaskNavigation):
            def action(self, command, mode):
                if command.startswith('@group:'):
                    return TaskNavigation.action(self, command, mode)   # a document menu group opens
                sim.chosen = command
                return mode

            def pick(self, kind, mode=None):
                sim.chosen = '@' + kind
                return mode

        self.nav = Navigation(sandbox)
        self.mode = mode
        self.title = title
        self.opening = None

    def open(self):
        self.nav.enter(self.mode, self.title)
        self.opening = self.sandbox.take()
        return self.opening

    def names(self):
        return [name for name, _, _ in self.nav.items(self.mode)]

    def menu(self):
        return self.nav.state(self.mode)

    def feed(self, kind, value):
        if kind == 'key':
            key = canonical_key(value)
            if self.mode == 'document_menu' and len(key) == 1 and key.isalpha():
                key = 'MenuPick:' + key     # the window sends letters so in the document menu
            command = self.nav.keyboard(key, self.mode)
            if command is None and len(key) == 1 and key.isalnum():
                command = 'letter:' + key.lower()
            if command is None:
                return None
        else:
            command = value
        if plain(command) in ('escape', 'go back', 'back'):
            self.chosen = 'escape'
            return 'That goes back.'
        result = self.nav.handle(command, self.mode)
        text = self.sandbox.take()
        if self.sandbox.requests:
            self.chosen = self.sandbox.requests.pop()
            self.sandbox.requests.clear()
        if result is None and not text and self.chosen is None:
            if kind != 'key':
                return None
            # A key the menu hands to the app as its command (Control+N in Notepad is "write a note").
            self.chosen = command
        if self.chosen is not None and not text:
            name = next((n for n, _, c in self.nav.items(self.mode) if c == self.chosen), self.chosen)
            return 'That opens ' + name + '.'
        return text or None


class AltMenuSim(Sim):
    """A screen's Alt menu, run by the real ScreenMenu. Choosing an item records it and does nothing else."""

    def __init__(self, app, mode):
        from screen_menus import MENUS, ScreenMenu
        sandbox = self.sandbox = Sandbox(app)
        sim = self

        class Menu(ScreenMenu):
            def run(self, command, mode):
                sim.chosen = command
                return mode

        # The screen behind the menu is open, as it is when the real menu opens (ScreenMenu.available).
        from types import SimpleNamespace
        sandbox.email_draft = sandbox.FILE_READER = object()
        sandbox.web_session = SimpleNamespace(pending=None, submit_pending=None, list_focus=None, keyboard_field=None)
        self.menu_object = Menu(sandbox)
        self.mode = mode
        self.title = MENUS[mode][0]

    def is_open(self):
        return self.menu_object.mode is not None

    def menu(self):
        if not self.is_open():
            return None
        entries = self.menu_object.entries()
        return [e[0] for e in entries], self.menu_object.index, lambda i: setattr(self.menu_object, 'index', i)

    def label(self, command):
        from screen_menus import items
        return next((label for _, label, _, c in items(self.mode) if c == command), command)

    def feed(self, kind, value):
        if kind == 'key':
            key = canonical_key(value)
            if self.is_open() and len(key) == 1 and key.isalnum():
                key = 'Letter:' + key.lower()
            request = self.menu_object.keyboard(key, self.mode)
            if request is None:
                return None
            self.menu_object.handle(request, self.mode)
        else:
            result = self.menu_object.handle(value, self.mode)
            if result is None:
                return None
        text = self.sandbox.take()
        if self.chosen is not None:
            return (text + ' ' if text else '') + 'That chooses ' + self.label(self.chosen) + '.'
        return text


class EditorSim(Sim):
    """A real document or email draft in a temporary folder. It is deleted when the lesson ends."""

    def __init__(self, kind='document', text='', **fields):
        self.folder = Path(tempfile.mkdtemp(prefix='vc-tutorial-'))
        if kind == 'email':
            from email_draft import VoiceEmail
            self.editor = VoiceEmail(self.folder, title='Practice email', **fields)
        else:
            from document_editor import VoiceDocument
            self.editor = VoiceDocument(self.folder, title='Practice')
        self.editor.dictating = True
        self.kind = kind
        if text:
            self.editor.process(text)

    def feed(self, kind, value):
        if kind == 'key':
            return None
        try:
            result = str(self.editor.process(value))
        except (OSError, ValueError) as error:
            return str(error)
        # Words you write are said back as you wrote them, as the app does (dictation_feedback).
        return result[len('Added: '):] if result.startswith('Added: ') else result

    def text(self):
        return '\n'.join(p.text for p in self.editor.paragraphs)

    def close(self):
        shutil.rmtree(self.folder, ignore_errors=True)


class MemoSim(Sim):
    """Keeps the last words given, such as a document name, for the steps after it."""

    def __init__(self, answer=None):
        self.value = ''
        self.answer = answer

    def feed(self, kind, value):
        if kind == 'key':
            return None
        self.value = ' '.join(str(value).split()).rstrip('.!?,').strip()
        return self.answer(self.value) if self.answer else self.value


PRACTICE_PROBLEM = 'That could not be practiced here. The real app is not affected.'


def feed(sim, kind, value):
    """Give an input to a practice screen. A practice screen that fails never stops the tutorial."""
    try:
        return sim.feed(kind, value)
    except Exception:
        return PRACTICE_PROBLEM


class Step:
    """One thing to do.

    say: what to do, in plain words.
    keys and phrases: the inputs that count (keys as the window sends them).
    reply: what the app says when it is done; a function gets the lesson's sims.
    sim and goal: the step passes when goal(sims) is true after an input; inputs the
    simulated screen understands are answered by it without counting as a miss.
    text: any spoken or typed words count (writing), and are given to the sim.
    screen and command: where this works in the real app and the command it runs,
    so the tests can check the step against the real code.
    """

    def __init__(self, say, keys=(), phrases=(), reply='', how='', sim=None, goal=None, text=False,
                 screen=None, command=None, feed=False, replay=(), example=''):
        self.say = say
        self.keys = tuple(canonical_key(k) for k in keys)
        self.phrases = tuple(phrases)
        self.reply = reply
        self.how = how
        self.sim = sim
        self.goal = goal
        self.text = text
        self.screen = screen
        self.command = command
        self.feed = feed
        # Inputs that redo this step on a fresh simulated screen, when a lesson continues
        # where you stopped. A writing step uses its example words.
        self.replay = tuple(replay)
        self.example = example

    def accepts_key(self, key):
        return canonical_key(key) in self.keys

    def uses_key(self, key):
        """True when this key is part of the step: one of its keys, or a key of its solution."""
        key = canonical_key(key)
        return key in self.keys or any(kind == 'key' and canonical_key(value) == key for kind, value in self.replay)

    def accepts_words(self, words):
        return plain(words) in {plain(p) for p in self.phrases}

    def instruction(self):
        if self.how:
            return self.how
        parts = []
        if self.keys:
            parts.append('press ' + ' or '.join(key_words(k) for k in self.keys[:2]))
        if self.phrases:
            parts.append('say ' + self.phrases[0])
        if not parts:
            return self.say
        text = ', or '.join(parts)
        return text[0].upper() + text[1:] + '.'


class Lesson:
    def __init__(self, key, title, intro, steps, sims=None):
        self.key = key
        self.title = title
        self.intro = intro
        self.steps = steps
        self.make_sims = sims or (lambda: {})


class Course:
    def __init__(self, key, name, aliases, lessons, apps=()):
        self.key = key
        self.name = name
        self.aliases = tuple(aliases)
        self.lessons = lessons
        # Main menu commands this course teaches (see tutorial_lessons.main_menu_apps).
        self.apps = tuple(apps)


class TutorialSession:
    def __init__(self, app, folder=None, courses=None):
        if courses is None:
            from tutorial_lessons import build
            courses = build(app)
        self.app = app
        self.courses = courses
        self.order = [(c, l) for c in courses for l in c.lessons]
        self.folder = Path(folder) if folder is not None else None
        self.state = 'picker'
        self.picker_index = None
        self.position = None         # index in self.order
        self.step_index = 0
        self.misses = 0
        self.sims = {}
        self.previous = ''
        self.progress = self.load()

    # Progress ---------------------------------------------------------------------------
    def progress_path(self):
        return self.folder / PROGRESS_FILE if self.folder is not None else None

    def load(self):
        path = self.progress_path()
        empty = {'done': [], 'current': None}
        if path is None:
            return empty
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return empty       # missing or damaged: start fresh, never stop the app
        if not isinstance(data, dict):
            return empty
        done = data.get('done', [])
        done = [d for d in done if isinstance(d, str)] if isinstance(done, list) else []
        current = data.get('current')
        if not (isinstance(current, dict) and self.find(current.get('lesson')) is not None
                and isinstance(current.get('step'), int)):
            current = None
        return {'done': done, 'current': current}

    def save(self):
        path = self.progress_path()
        if path is None:
            return True
        try:
            from storage import write_text_atomic
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(path, json.dumps(self.progress))
            return True
        except OSError:
            return False

    def lesson_id(self, position):
        course, lesson = self.order[position]
        return course.key + '/' + lesson.key

    def find(self, lesson_id):
        for index in range(len(self.order)):
            if self.lesson_id(index) == lesson_id:
                return index
        return None

    # The lesson list ---------------------------------------------------------------------
    def picker_items(self):
        items = []
        current = self.progress['current']
        if current:
            position = self.find(current['lesson'])
            course, lesson = self.order[position]
            items.append(('Continue where you stopped: ' + course.name + ', ' + lesson.title, ('resume', position)))
        items.append(('Go in order', ('order', None)))
        for course in self.courses:
            done = all(course.key + '/' + l.key in self.progress['done'] for l in course.lessons)
            items.append((course.name + (', done' if done else ''), ('course', course)))
        return items

    def menu(self):
        """(names, index, select) for the list on screen: the lesson list or a simulated menu."""
        if self.state == 'picker':
            names = [name for name, _ in self.picker_items()]
            return names, self.picker_index, lambda i: setattr(self, 'picker_index', i)
        step = self.step()
        if self.state == 'lesson' and step is not None and step.sim:
            return self.sims[step.sim].menu()
        return None

    def say(self, text):
        self.previous = text
        return text

    def start(self):
        self.state = 'picker'
        self.picker_index = 0
        items = self.picker_items()
        return self.say(INTRO + 'Choose where to start. Use Up and Down Arrow and Enter, or say a name, such as email. '
                        + announce_item(items[0][0], 0, len(items)))

    def picker_key(self, key):
        items = self.picker_items()
        names = [name for name, _ in items]
        key = canonical_key(key)
        if key in ('Down', 'Right', 'Up', 'Left'):
            step = 1 if key in ('Down', 'Right') else -1
            new = bounded_index(self.picker_index, step, len(items))
            if new == self.picker_index:
                return self.say('Start of list.' if step < 0 else 'End of list.'), None
            self.picker_index = new
            return self.say(announce_item(names[new], new, len(names))), None
        if key in ('Home', 'End'):
            new = 0 if key == 'Home' else len(items) - 1
            if new == self.picker_index:
                return self.say('Start of list.' if key == 'Home' else 'End of list.'), None
            self.picker_index = new
            return self.say(announce_item(names[new], new, len(names))), None
        if len(key) == 1 and key.isalpha():
            new = next_match(names, self.picker_index, key)
            if new is None:
                return self.say('No item starts with ' + key + '.'), None
            self.picker_index = new
            return self.say(announce_item(names[new], new, len(names))), None
        if key in ('Enter', 'Space'):
            return self.pick(items[self.picker_index or 0][1]), None
        return None

    def picker_words(self, command):
        items = self.picker_items()
        names = [name for name, _ in items]
        if command in ('next', 'previous'):
            return self.picker_key('Down' if command == 'next' else 'Up')
        if command in ('start of list', 'first item', 'top of list'):
            return self.picker_key('Home')
        if command in ('end of list', 'last item', 'bottom of list'):
            return self.picker_key('End')
        if command in PICK:
            return self.pick(items[self.picker_index or 0][1]), None
        if command in RESUME and self.progress['current']:
            return self.pick(items[0][1]), None
        if command in IN_ORDER:
            return self.pick(('order', None)), None
        for course in self.courses:
            if command in (plain(course.name),) + course.aliases:
                return self.pick(('course', course)), None
        return None

    def pick(self, choice):
        kind, value = choice
        if kind == 'resume':
            return self.begin(value, self.progress['current']['step'], resumed=True)
        if kind == 'order':
            first = next((i for i in range(len(self.order)) if self.lesson_id(i) not in self.progress['done']), 0)
            return self.begin(first)
        course = value
        first = next(i for i, (c, _) in enumerate(self.order) if c is course)
        unfinished = next((i for i, (c, _) in enumerate(self.order)
                           if c is course and self.lesson_id(i) not in self.progress['done']), first)
        return self.begin(unfinished)

    # Lessons ------------------------------------------------------------------------------
    def lesson(self):
        return self.order[self.position] if self.position is not None else (None, None)

    def step(self):
        _, lesson = self.lesson()
        if lesson is None or self.state != 'lesson' or self.step_index >= len(lesson.steps):
            return None
        return lesson.steps[self.step_index]

    def close_sims(self):
        for sim in self.sims.values():
            try:
                sim.close()
            except Exception:
                pass
        self.sims = {}

    def make_sims(self):
        """Fresh simulated screens for the lesson."""
        self.close_sims()
        _, lesson = self.lesson()
        self.sims = lesson.make_sims()      # a factory that fails leaves nothing open (see tutorial_lessons)
        for sim in self.sims.values():
            if isinstance(sim, TaskMenuSim):
                sim.open()

    def begin(self, position, step=0, resumed=False):
        self.position = position
        course, lesson = self.lesson()
        self.state = 'lesson'
        self.misses = 0
        try:
            self.make_sims()
        except Exception:
            # Its practice screen could not be built (in the packed app, a module's code may not
            # be readable). Say so plainly; every other lesson still works.
            self.close_sims()
            self.state = 'between'
            return self.say(course.name + ': ' + lesson.title + '. This lesson could not start on this computer. '
                            'Your apps are not affected. Say next lesson to go on, or lesson list to choose another.')
        self.step_index = 0
        # Steps before a resumed one are replayed quietly, so the simulated screen is where you left it.
        while self.step_index < min(step, len(lesson.steps)):
            self.replay(lesson.steps[self.step_index])
            self.step_index += 1
        self.remember()
        number = position_in_course(self.order, position)
        lead = (course.name + '. Lesson ' + str(number[0]) + ' of ' + str(number[1]) + ': ' + lesson.title + '. ')
        if resumed and step:
            lead += 'Continuing where you stopped. '
        else:
            lead += lesson.intro + ' '
        return self.say(lead + self.step_text())

    def replay(self, step):
        """Do a step for the user without speaking, to rebuild the simulated screen."""
        if not step.sim:
            return
        sim = self.sims[step.sim]
        inputs = step.replay
        if not inputs and step.text and step.example:
            inputs = (('voice', step.example),)
        elif not inputs and step.feed:
            inputs = (('voice', step.phrases[0]),) if step.phrases else (('key', step.keys[0]),) if step.keys else ()
        for kind, value in inputs:
            sim.chosen = None
            feed(sim, kind, value)
        sim.chosen = None

    def step_text(self):
        _, lesson = self.lesson()
        return 'Step ' + str(self.step_index + 1) + ' of ' + str(len(lesson.steps)) + '. ' + self.step().say

    def remember(self):
        if self.state == 'lesson':
            self.progress['current'] = {'lesson': self.lesson_id(self.position), 'step': self.step_index}
        self.save()

    def praise(self):
        return PRAISE[(self.step_index + (self.position or 0)) % len(PRAISE)]

    def advance(self, reply, praise=True):
        course, lesson = self.lesson()
        lead = ((self.praise() + ' ') if praise else '') + (reply.strip() + ' ' if reply and reply.strip() else '')
        self.step_index += 1
        self.misses = 0
        if self.step_index < len(lesson.steps):
            self.remember()
            return self.say(lead + self.step_text())
        # The lesson is done.
        lesson_id = self.lesson_id(self.position)
        if lesson_id not in self.progress['done']:
            self.progress['done'].append(lesson_id)
        self.close_sims()
        self.state = 'between'
        following = self.position + 1
        if following < len(self.order):
            self.progress['current'] = {'lesson': self.lesson_id(following), 'step': 0}
            self.save()
            next_course, next_lesson = self.order[following]
            where = next_lesson.title if next_course is course else next_course.name + ', ' + next_lesson.title
            return self.say(lead + 'Lesson done: ' + lesson.title + '. Next is ' + where +
                            '. Press Enter, or say next lesson, to start it. Say lesson list to choose another. '
                            'Escape stops the tutorial.')
        self.progress['current'] = None
        self.save()
        return self.say(lead + 'Lesson done: ' + lesson.title + '. You finished the last lesson. '
                        'Say lesson list to practice again, or press Escape to stop.')

    def heard(self, kind, value, typed=False):
        if kind == 'key':
            return 'You pressed ' + key_words(value) + '.'
        return ('You typed: ' if typed else 'I heard: ') + str(value).strip() + '.'

    def miss(self, heard, note=''):
        step = self.step()
        self.misses += 1
        text = 'Not quite. ' + heard + ' ' + (note + ' ' if note else '') + step.instruction() + ' Try again.'
        if self.misses >= 2:
            text += ' Or say show me to hear how, or skip to go on. You can also press Y to hear how, or N to skip.'
        return self.say(text)

    def show(self):
        step = self.step()
        self.misses = 0
        text = 'Here is how. ' + (step.how or step.instruction())
        if isinstance(step.reply, str) and step.reply:
            text += ' The app then says: ' + step.reply
        return self.say(text + ' Now you try.')

    def stop(self):
        """Stop the tutorial and keep the place. Returns the words to say with the main menu."""
        if self.state == 'lesson':
            self.remember()
        saved = self.save()
        self.close_sims()
        self.state = 'closed'
        if not saved:
            return 'Tutorial stopped. Your place could not be saved.'
        if not self.progress['current']:
            return 'Tutorial stopped.'
        return 'Tutorial stopped. Your place is saved. Say start tutorial to continue.'

    def close(self):
        self.close_sims()

    # Input --------------------------------------------------------------------------------
    def expects_key(self, key):
        step = self.step()
        if step is None:
            return False
        if step.uses_key(key):
            return True
        return bool(step.goal is not None and canonical_key(key) not in SPECIAL_KEYS)

    def expects_words(self, text):
        step = self.step()
        if step is None:
            return False
        # A step on a simulated screen also takes that screen's words, but the app's own
        # requests (stop talking, the time) come first there, as on the real screen.
        return step.accepts_words(text) or step.text

    def passes_through(self, key):
        """True for keys that keep their real job when this step does not ask for them:
        F3 (what is playing), F12 (time and date), F9 (microphone), Control+F12 (sleep),
        Control+P (pause audio) and the display keys. They change nothing in your work."""
        key = canonical_key(key)
        everywhere = key in ('F3', 'F12', 'Double:F12', 'F9', 'Ctrl+F12', 'Ctrl+P') or key.startswith('Display:')
        step = self.step()
        return everywhere and not (step is not None and step.uses_key(key))

    def key(self, key):
        """A key press. Returns (words to say, leave) where leave is None, 'main menu' or 'exit'."""
        key = canonical_key(key)
        if key == 'Control':
            step = self.step()
            if step is not None and step.accepts_key('Control'):
                return self.advance(self.reply(step, 'key', key)), None
            return '', None             # Control only stops speech, as everywhere
        if self.state == 'picker':
            result = self.picker_key(key)
            if result is not None:
                return result
        elif self.state == 'between':
            if key in ('Enter', 'Space'):
                return self.begin(self.position + 1) if self.position + 1 < len(self.order) else self.start(), None
        elif self.state == 'lesson':
            step = self.step()
            if step.accepts_key(key) and step.goal is None:
                return self.advance(self.reply(step, 'key', key)), None
            if self.misses >= 2 and key in ('Y', 'N') and not step.uses_key(key):
                return (self.show() if key == 'Y' else self.skip()), None
            if step.goal is not None and (key not in SPECIAL_KEYS or step.uses_key(key)):
                result = self.goal_input(step, 'key', key)
                if result is not None:
                    return result, None
        if key == 'Escape':
            return self.stop(), 'main menu'
        if key == 'F1':
            return self.stop(), 'main menu'
        if key == 'Alt+F4':
            return self.stop(), 'exit'
        if key == 'Double:F1':
            return self.help(), None
        if self.state == 'lesson':
            return self.miss(self.heard('key', key)), None
        if self.state == 'between':
            return self.say('Press Enter to start the next lesson, or Escape to stop.'), None
        return self.say('Use Up and Down Arrow to choose, and Enter to start. Escape stops the tutorial.'), None

    def words(self, text, typed=False):
        """Spoken or typed words. Returns (words to say, leave)."""
        command = plain(text)
        if not command:
            return self.say('I did not hear anything. ' + (self.step_text() if self.step() else '')), None
        step = self.step()
        if step is not None:
            if step.accepts_words(text):
                return self.advance(self.reply(step, 'voice', text)), None
            if step.text and command not in STOP + REPEAT + SKIP + SHOW:
                return self.advance(self.reply(step, 'voice', text)), None
            if step.goal is not None and command not in STOP + REPEAT + SKIP + SHOW:
                result = self.goal_input(step, 'voice', text)
                if result is not None:
                    return result, None
        if command in STOP:
            return self.stop(), 'main menu'
        if command in REPEAT:
            return self.say(self.previous), None
        if command in HELP:
            return self.help(), None
        if self.state == 'picker':
            result = self.picker_words(command)
            if result is not None:
                return result
            return self.say('That is not a lesson name. ' + self.say_choices()), None
        if self.state == 'between':
            if command in NEXT_LESSON:
                return (self.begin(self.position + 1) if self.position + 1 < len(self.order) else self.start()), None
            if command in AGAIN:
                return self.begin(self.position), None
            if command in LESSON_LIST:
                return self.start(), None
            return self.say('Say next lesson, lesson list, or stop tutorial.'), None
        if command in LESSON_LIST:
            self.remember()
            self.close_sims()
            return self.start(), None
        if command in SKIP:
            return self.skip(), None
        if command in SHOW:
            return self.show(), None
        polite = POLITE.sub('', command).strip()
        if polite != command and polite and step.accepts_words(polite):
            # The app itself does not understand "please" here, so this does not pass, but it is no miss.
            return self.say('Almost. The app listens for the command alone, without words like please. Say just: '
                            + polite + '.'), None
        return self.miss(self.heard('voice', text, typed)), None

    def say_choices(self):
        return 'Use Up and Down Arrow and Enter, or say a name, such as ' + self.courses[0].name + '.'

    def help(self):
        step = self.step()
        return self.say(HELP_TEXT + ('Now: ' + step.say if step else ''))

    def skip(self):
        return self.advance('Skipped.', praise=False)

    def reply(self, step, kind, value):
        if callable(step.reply):
            if step.sim and step.text:
                feed(self.sims[step.sim], 'voice', value)
            return step.reply(self.sims, value)
        if step.feed and step.sim:
            sim = self.sims[step.sim]
            spoken = feed(sim, kind, value)      # your own words, as the app would get them
            return (spoken or '') + (' ' + step.reply if step.reply else '')
        if step.text and step.sim:
            return (feed(self.sims[step.sim], 'voice', value) or '') + (' ' + step.reply if step.reply else '')
        return step.reply

    def goal_input(self, step, kind, value):
        """An input on a simulated screen. Returns the words to say, or None when the screen ignores it."""
        sim = self.sims[step.sim]
        sim.chosen = None
        spoken = feed(sim, kind, value)
        if spoken is None and sim.chosen is None:
            return None
        if step.goal(self.sims):
            sim.chosen = None
            if callable(step.reply):
                # The step knows the app's own words for what the choice opens.
                return self.advance(step.reply(self.sims, value))
            return self.advance(((spoken or '') + ' ' + (step.reply or '')).strip())
        if sim.chosen is not None:
            # A wrong choice: the real app would have opened something else. Stay here.
            sim.chosen = None
            return self.miss((spoken + ' ' if spoken else '') + 'In this lesson, the app stays here.')
        return self.say(spoken)


def position_in_course(order, position):
    course = order[position][0]
    lessons = [i for i, (c, _) in enumerate(order) if c is course]
    return lessons.index(position) + 1, len(lessons)


# The app side ---------------------------------------------------------------------------------
def start(app):
    """Open the tutorial on its lesson list. Returns the mode."""
    app.tutorial_session = TutorialSession(app, getattr(app, 'APP', None))
    app.speak(app.tutorial_session.start())
    return MODE


def intercepts_key(app, key):
    """True when this key goes to the tutorial instead of the app's own key handling."""
    session = app.tutorial_session
    if not isinstance(session, TutorialSession):
        return False
    # A voice list opened from the tutorial ("Voice list") keeps its own keys.
    if app.VOICE_PICK_INDEX is not None or app.SYNTH_PICK_INDEX is not None or app.NAMED_LIST:
        return False
    return not session.passes_through(key)


def route(app, text, typed=False):
    """Words or a key for the tutorial. The app's own global requests still work when the
    step does not ask for them: stop talking, speech speed and volume, voices, the time,
    what is playing, the display, sleep and exit. Returns the mode."""
    session = app.tutorial_session
    if not isinstance(session, TutorialSession):
        # The tutorial screen with no lesson list open (after an error): global requests
        # still work; anything else opens the lesson list.
        if text.startswith(KEY_PREFIX):
            return start(app)
        command = app.normalized_command(text)
        handled = global_request(app, text, command, typed, None)
        return handled if handled is not None else start(app)
    if text.startswith(KEY_PREFIX):
        app.interrupt_speech()
        spoken, leave = session.key(text[len(KEY_PREFIX):])
        return finish(app, spoken, leave)
    command = app.normalized_command(text)
    picking = app.VOICE_PICK_INDEX is not None or app.SYNTH_PICK_INDEX is not None
    if picking or not session.expects_words(text):
        handled = global_request(app, text, command, typed, session)
        if handled is not None:
            return handled
    app.interrupt_speech()
    spoken, leave = session.words(text, typed)
    return finish(app, spoken, leave)


def global_request(app, text, command, typed, session):
    """The app's own requests that work on every screen, done for real. Returns the mode, or None."""
    if app.change_speech_setting(text) or app.use_synthesizer(text) or app.voice_menu(command):
        return MODE
    control = app.speech_control(text)
    if control:
        app.control_speech(control)
        return MODE
    import time_date
    clock = time_date.clock_request(text, False)
    if clock:
        app.speak_clock(clock)
        return MODE
    if app.now_playing_asked(text, MODE, typed):
        app.speak(app.now_playing(MODE))
        return MODE
    display = __import__('display_options').voice_request(text)
    if display:
        app.change_display(display, MODE)
        return MODE
    if app.spoken_control(command) == 'sleep':
        if session is not None:
            session.remember()
        app.SLEEP_RETURN_MODE = MODE
        app.speak(app.sleep_message())
        return 'sleep'
    if app.spoken_control(command) == 'exit':
        if session is not None:
            session.stop()
        app.tutorial_session = None
        return app.handle(text, 'awake', typed)
    return None


def finish(app, spoken, leave):
    if leave is None:
        if spoken:
            app.speak(spoken)
        return MODE
    app.tutorial_session = None
    if leave == 'exit':
        app.MAIN_MENU_LEAD = ''
        return app.handle('exit companion', 'awake', typed=True)
    # Said with the main menu in one message (handle() says it).
    app.MAIN_MENU_LEAD = spoken
    return 'awake'


def self_check(app):
    """Build every lesson's practice screens once and close them (the packaged app's
    --check-runtime). Returns the lessons that could not start; empty means all can.
    The installed app packs its modules, so this proves the practice copies load there."""
    import tutorial_lessons
    failed = []
    for course in tutorial_lessons.build(app):
        for lesson in course.lessons:
            sims = {}
            try:
                sims = lesson.make_sims()
            except Exception as error:
                failed.append(course.name + ': ' + lesson.title + ' (' + type(error).__name__ + ')')
            finally:
                for sim in sims.values():
                    try:
                        sim.close()
                    except Exception:
                        pass
    return failed
