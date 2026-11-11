"""The tutorial's courses and lessons (tutorial_engine.py runs them).

Most lessons are built from the app's own lists, so a new command or a renamed menu
item reaches the tutorial by itself:
- the main menu and its groups (MAIN_MENU_CHOICES, task_navigation),
- every Alt menu (screen_menus.MENUS),
- the direct keys of each screen (input_parity.SCREEN_KEYS),
- the document menu (task_navigation.DOCUMENT_ACTIONS),
- File manager's menu (file_manager.GROUPS),
- the Radio and Podcasts actions (media_navigation),
- the YouTube keys (youtube_screen.KEYS).
Guided lessons for the first tasks (the main menu, the keys that work everywhere,
writing, email and the web) are written out step by step, with simulated screens.

Every course says which main menu apps it teaches (Course.apps). A test fails if an
app on the main menu has no course.
"""
import re
import tempfile
from pathlib import Path

from menu_navigation import announce_item, bounded_index, next_match, spoken_key
from tutorial_engine import (AltMenuSim, Course, EditorSim, Lesson, MainMenuSim, MemoSim, Sim, Step, TaskMenuSim,
                             canonical_key, plain)

# Keys that are a real key press (not a menu path such as "Alt, 1, 3").
REAL_KEY = re.compile(r'^(?:Double:)?(?:(?:Ctrl|Alt|Shift|Insert|CapsLock)\+)*(?:F\d{1,2}|[A-Z0-9]|Enter|Escape|Space|Tab|'
                      r'Delete|Home|End|Up|Down|Left|Right|Next|Prior|Page Up|Page Down|comma|period|BackSpace)$')
PAGE_KEYS = {'Page Up': 'Prior', 'Page Down': 'Next'}
# How the guide writes a key the window sends under another name.
WINDOW_NAMES = {'Shift+Tab': 'ShiftTab'}


def key_id(key):
    """The key as the window sends it, or None when it is a menu path or several keys."""
    key = PAGE_KEYS.get(key, WINDOW_NAMES.get(key, key))
    return canonical_key(key) if REAL_KEY.match(key) else None


def phrase_of(command):
    """The spoken command, when it can be said as it is (no value to fill in)."""
    if not command or command.startswith('@') or '{value}' in command or command.startswith('web key '):
        return None
    return command


# Simulated screens for single apps -----------------------------------------------------------
class ListSim(Sim):
    """A plain list: arrows, Home, End, first letters and Enter, with the app's own words."""

    def __init__(self, title, items, hotkey=True, opening=''):
        self.title = title
        self.items = list(items)        # (name, command when chosen)
        self.index = 0
        self.hotkey = hotkey
        self.opening = opening

    def names(self):
        return [name for name, _ in self.items]

    def menu(self):
        return self.names(), self.index, lambda i: setattr(self, 'index', i)

    def say_item(self, index):
        return announce_item(self.items[index][0], index, len(self.items), hotkey=self.hotkey)

    def feed(self, kind, value):
        count = len(self.items)
        if kind == 'key':
            key = canonical_key(value)
            if key in ('Down', 'Up', 'Right', 'Left'):
                step = 1 if key in ('Down', 'Right') else -1
                new = bounded_index(self.index, step, count)
                if new == self.index:
                    return 'Start of list.' if step < 0 else 'End of list.'
                self.index = new
                return self.say_item(new)
            if key in ('Home', 'End'):
                new = 0 if key == 'Home' else count - 1
                if new == self.index:
                    return 'Start of list.' if key == 'Home' else 'End of list.'
                self.index = new
                return self.say_item(new)
            if len(key) == 1 and key.isalpha():
                new = next_match(self.names(), self.index, key)
                if new is None:
                    return 'No menu item starts with ' + key + '.'
                self.index = new
                return self.say_item(new)
            if key == 'Enter':
                self.chosen = self.items[self.index][1]
                return None
            return None
        command = plain(value)
        if command in ('next', 'previous'):
            return self.feed('key', 'Down' if command == 'next' else 'Up')
        if command in ('that one', 'okay', 'ok', 'confirm', 'confirm that'):
            self.chosen = self.items[self.index][1]
            return None
        for name, chosen in self.items:
            if command == plain(name):
                self.chosen = chosen
                return None
        return None


class BrowserMenuSim(Sim):
    """The Web browser menu, run by the real BrowserMenu with a stand-in page and no history."""
    title = 'Web browser menu'

    def __init__(self):
        from browser_menu import BrowserMenu
        from types import SimpleNamespace
        self.folder = Path(tempfile.mkdtemp(prefix='vc-tutorial-web-'))
        self.menu_object = BrowserMenu(self.folder)
        self.session = SimpleNamespace(snapshot=None, backend=None, favorites=None)
        self.opening = self.menu_object.start()

    def menu(self):
        return self.menu_object.menu(self.session, False)

    def feed(self, kind, value):
        if kind == 'key':
            key = canonical_key(value)
            command = {'Up': 'previous', 'Left': 'previous', 'Down': 'next', 'Right': 'next', 'Home': 'home', 'End': 'end',
                       'Enter': 'enter', 'Escape': 'escape'}.get(key)
            if command is None and len(key) == 1 and key.isalpha():
                command = 'letter:' + key.lower()
            if command is None:
                return None
        else:
            command = value
        text, action = self.menu_object.process(command, self.session, False)
        if action:
            self.chosen = action
        return text or None

    def close(self):
        import shutil
        shutil.rmtree(self.folder, ignore_errors=True)


SAMPLE_PAGE = [
    {'role': 'heading', 'level': 1, 'label': 'Weather for your area'},
    {'role': 'paragraph', 'label': 'Today will be sunny with a high of 70.'},
    {'role': 'link', 'label': 'Hourly forecast'},
    {'role': 'heading', 'level': 2, 'label': 'Search for a city'},
    {'role': 'textbox', 'tag': 'input', 'type': 'search', 'label': 'City name'},
    {'role': 'button', 'label': 'Search'},
    {'role': 'link', 'label': 'Weather alerts'},
]


class PageSim(Sim):
    """A small web page. Each part is said with the real page reader's words (web_browse.describe)."""
    title = 'Web page'

    def __init__(self):
        self.elements = SAMPLE_PAGE
        self.position = 0
        self.field = None

    def say(self, index):
        from web_browse import describe
        return describe(self.elements[index], self.elements)

    def find(self, kinds, step):
        from web_browse import kind
        index = self.position + step
        while 0 <= index < len(self.elements):
            if kind(self.elements[index]) in kinds:
                self.position = index
                return self.say(index)
            index += step
        return None

    def feed(self, kind, value):
        from web_browse import QUICK_KEYS, SPOKEN_NAMES
        if kind != 'key':
            return None
        key = canonical_key(value)
        if self.field is not None:
            return None
        if key in ('Down', 'Up'):
            new = self.position + (1 if key == 'Down' else -1)
            if not 0 <= new < len(self.elements):
                return 'Bottom of page.' if key == 'Down' else 'Top of page.'
            self.position = new
            return self.say(new)
        shift = key.startswith('Shift+')
        letter = key[6:] if shift else key
        if len(letter) == 1 and letter.lower() in QUICK_KEYS:
            name = QUICK_KEYS[letter.lower()]
            found = self.find({name}, -1 if shift else 1)
            if found is None:
                return 'No more ' + SPOKEN_NAMES.get(name, name) + 's.' if not shift else 'No earlier ' + SPOKEN_NAMES.get(name, name) + 's.'
            return found
        if key == 'Tab':
            return self.find({'link', 'button', 'edit'}, 1)
        if key == 'Enter':
            from web_browse import kind as kind_of
            element = self.elements[self.position]
            self.chosen = kind_of(element) + ':' + element['label']
            return None
        return None


class MailboxSim(Sim):
    """An inbox with three sample messages. A message is said with the real list words
    (mail_voice.status_words and sender_name), in the default order: from, subject, date."""
    title = 'Email: Inbox'
    ROWS = [
        {'id': '1', 'from': 'Sam Rivera <sam@example.com>', 'subject': 'Lunch on Friday', 'date': 'Monday', 'unread': True,
         'body': 'Hi. Are you free for lunch on Friday at noon?', 'to': 'you@example.com'},
        {'id': '2', 'from': 'VA Clinic <clinic@example.com>', 'subject': 'Appointment reminder', 'date': 'Sunday',
         'unread': False, 'body': 'Your appointment is on Tuesday at 9 AM.', 'to': 'you@example.com'},
        {'id': '3', 'from': 'Pat Lee <pat@example.com>', 'subject': 'Photos from the trip', 'date': 'Saturday',
         'unread': False, 'body': 'Here are the photos I promised.', 'to': 'you@example.com'},
    ]

    def __init__(self):
        self.current = 1
        self.view = 'folder'

    def summary(self, number):
        from mail_voice import sender_name, status_words
        row = self.ROWS[number - 1]
        parts = [p for p in (status_words(row), sender_name(row), row['subject'], row['date']) if p]
        return '. '.join(parts) + '. ' + str(number) + ' of ' + str(len(self.ROWS)) + '.'

    def menu(self):
        if self.view != 'folder':
            return None
        return [self.summary(i + 1) for i in range(len(self.ROWS))], self.current - 1, lambda i: setattr(self, 'current', i + 1)

    def feed(self, kind, value):
        from input_parity import MAIL_HEADER_KEYS
        key = canonical_key(value) if kind == 'key' else None
        command = plain(value) if kind != 'key' else {'Down': 'next message', 'Up': 'previous message', 'Enter': 'that one',
                                                     'Escape': 'go back'}.get(key, '')
        row = self.ROWS[self.current - 1]
        if key in MAIL_HEADER_KEYS:
            question = MAIL_HEADER_KEYS[key]
            from mail_voice import sender_name
            return {'who is it from': 'From ' + sender_name(row) + '.', 'who is it to': 'To ' + row['to'] + '.',
                    'read the cc': 'No CC.', 'what is the subject': 'Subject ' + row['subject'] + '.',
                    'when was it sent': 'Sent ' + row['date'] + '.', 'how many attachments': 'No attachments.'}[question]
        if command in ('next message', 'previous message', 'next', 'previous') and self.view == 'folder':
            step = 1 if command.startswith('next') else -1
            if not 1 <= self.current + step <= len(self.ROWS):
                return 'End of list.' if step > 0 else 'Start of list.'
            self.current += step
            return self.summary(self.current)
        if command in ('that one', 'open current message', 'open message') and self.view == 'folder':
            self.view = 'message'
            row['unread'] = False
            return 'Message opened. ' + row['body']
        if command in ('go back', 'back') and self.view == 'message':
            self.view = 'folder'
            return self.summary(self.current)
        return None


class MediaSim(Sim):
    """The Radio or Podcasts screen, run by the real MediaNavigation with a stand-in player that plays nothing."""

    class Hub:
        def __init__(self):
            self.stations = []
            self.shows = []
            self.episodes = []
            self.station_index = self.show_index = self.episode_index = self.category_index = 0
            self.preset_index = 0
            self.current_station = None
            self.preset_browsing = self.browsing_episodes = self.browsing_categories = False
            self.awaiting_radio_search = self.awaiting_podcast_search = False
            self.calls = []

        def presets(self):
            return []

        def downloads(self):
            return []

        def recordings(self):
            return []

        def podcast_categories(self):
            return []

        def __getattr__(self, name):
            def record(*args, **kwargs):
                self.calls.append(name)
                return ''
            return record

    def __init__(self, section):
        from media_navigation import MediaNavigation
        self.hub = MediaSim.Hub()
        self.nav = MediaNavigation(self.hub, section)
        self.title = 'Radio' if section == 'radio' else 'Podcasts'
        self.opening = self.nav.enter(section, keyboard=True)

    def menu(self):
        return self.nav.state()

    def current(self):
        state = self.nav.state()
        return state[0][state[1] or 0] if state else None

    def feed(self, kind, value):
        if kind == 'key':
            key = canonical_key(value)
            if key not in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Enter', 'Tab', 'ShiftTab', 'Space') and \
                    not (len(key) == 1 and key.isalpha()):
                return None
            if key == 'Enter':
                self.chosen = self.current()
                return None
            if len(key) == 1:
                state = self.nav.state()
                new = next_match(state[0], state[1], key)
                if new is None:
                    return 'No menu item starts with ' + key + '.'
                state[2](new)
                return announce_item(state[0][new], new, len(state[0]))
            return self.nav.keyboard(key) or None
        command = plain(value)
        for action in self.nav.actions:
            if command == plain(action.label) or action.command and command == action.command:
                self.chosen = action.label
                return None
        if command in ('next', 'previous'):
            return self.nav.keyboard('Down' if command == 'next' else 'Up')
        return None


class HelpSim(Sim):
    """Help, with the real user guide (read only)."""
    title = 'Help'

    def __init__(self, app):
        from onboard_help import HelpSession
        self.session = HelpSession(app.GUIDE)
        self.opening = self.session.start()

    def menu(self):
        if self.session.level == 'topics':
            return [t['name'] for t in self.session.topics], self.session.topic_index, lambda i: setattr(self.session, 'topic_index', i)
        if self.session.level == 'subtopics':
            subs = self.session._subtopics()
            return [s[0] for s in subs], self.session.subtopic_index, lambda i: setattr(self.session, 'subtopic_index', i)
        return None

    def feed(self, kind, value):
        if kind == 'key':
            value = {'Down': 'next', 'Up': 'previous', 'Enter': 'that one', 'Escape': 'go back'}.get(canonical_key(value))
            if value is None:
                return None
        return self.session.process(value)


class FileListSim(ListSim):
    """File manager with three sample items. Each is said as File manager says it: name, kind, place."""

    def __init__(self):
        super().__init__('File manager', [('Documents, folder', 'open folder'), ('Music, folder', 'open folder'),
                                          ('Letter to Sam.docx, file', 'open file')])

    def say_item(self, index):
        # As FileManager.say_current says it: "Documents, folder. 1 of 3."
        return self.items[index][0] + '. ' + str(index + 1) + ' of ' + str(len(self.items)) + '.'


class DocumentMenuSim(TaskMenuSim):
    """A document with its Alt menu (task_navigation's document menu), closed at first."""
    TITLE = 'Document menu. Use arrows and Enter to choose a group'

    def __init__(self, app):
        super().__init__(app, 'document_menu', self.TITLE)
        self.open_now = False

    def menu(self):
        return super().menu() if self.open_now else None

    def feed(self, kind, value):
        if not self.open_now:
            if kind == 'key' and canonical_key(value) == 'Alt':
                self.open_now = True
                self.nav.group = None
                return self.open()
            return None
        if kind == 'key' and canonical_key(value) in ('Alt', 'Escape') and self.nav.group is None:
            self.open_now = False
            return 'Back to document.'
        spoken = super().feed(kind, value)
        if self.chosen == 'escape':
            # Escape in a group goes back to the groups, as in the app.
            self.chosen = None
            self.nav.group = None
            return self.open()
        if self.chosen is not None:
            self.open_now = False
            self.nav.group = None
        return spoken


# Helpers for writing lessons ---------------------------------------------------------------
def menu_goal(name, command):
    """Passes when the simulated screen `name` chose `command`."""
    return lambda sims: sims[name].chosen == command


def index_goal(name, index):
    return lambda sims: getattr(sims[name], 'index', None) == index


def opening(sim):
    return getattr(sim, 'opening', '') or ''


def task_menu_text(app, mode, title):
    sim = TaskMenuSim(app, mode, title)
    return sim.open()


# Drills: one step for each action, from the app's own lists ---------------------------------------
def drill_step(label, key, command, screen, sim=None):
    """'<Label>. Press <key>, or say <command>.' The key and the command come from the app's own lists."""
    keys = (key_id(key),) if key and key_id(key) else ()
    phrase = phrase_of(command)
    phrases = (phrase,) if phrase else ()
    if not keys and not phrases:
        return None
    how = []
    if keys:
        how.append('press ' + spoken_key(keys[0]))
    if phrases:
        how.append('say ' + phrase)
    text = ', or '.join(how)
    return Step(label.rstrip('.') + '. ' + text[0].upper() + text[1:] + '.', keys=keys, phrases=phrases,
                reply='', screen=screen, command=command)


def alt_menu_lessons(app, mode, intro):
    """One lesson for each group of a screen's Alt menu: open the menu, choose items, then the keys."""
    from screen_menus import MENUS, items
    title, groups = MENUS[mode]
    lessons = []
    for group_index, (group, entries) in enumerate(groups):
        steps = [Step('Press Alt to open the ' + title + '.', keys=('Alt',), sim='menu', goal=lambda s: s['menu'].is_open(),
                      how='Press the Alt key once and let it go.', screen=mode, replay=(('key', 'Alt'),))]
        if len(groups) > 1:
            name = group
            steps.append(Step('Open the ' + group + ' group. Use Down Arrow until you hear ' + group + ', then press Enter. '
                              'Or press ' + str(group_index + 1) + '.', sim='menu', screen=mode,
                              goal=lambda s, g=group_index: s['menu'].menu_object.group == g,
                              how='Press Down Arrow until you hear ' + name + '. Then press Enter.',
                              replay=(('key', str(group_index + 1)),)))
        first = next(((label, command) for label, _, command in entries if not command.startswith('@')),
                     (entries[0][0], entries[0][2]))
        number = [command for _, _, command in entries].index(first[1]) + 1
        steps.append(Step('Choose ' + first[0] + '. Use the arrows until you hear it, then press Enter.', sim='menu',
                          screen=mode, goal=menu_goal('menu', first[1]), replay=(('key', str(number)),),
                          how='Press Down Arrow until you hear ' + first[0] + '. Then press Enter.'))
        for label, key, command in entries:
            path = [row for row in items(mode) if row[0] == group and row[1] == label][0][2]
            step = drill_step(label, key, command, mode)
            if step is None:
                # No direct key and no words to say: the menu path, as the menu says it.
                digits = path[len('Alt, '):].split(', ')
                step = Step(label + '. Press Alt, then ' + ', then '.join(digits) + '.', sim='menu', screen=mode,
                            goal=menu_goal('menu', command), how='Press Alt, then ' + ', then '.join(digits) +
                            '. Press each key once.', command=command,
                            replay=(('key', 'Alt'),) + tuple(('key', d) for d in digits))
            steps.append(step)
        lessons.append(Lesson(mode + '-' + plain(group).replace(' ', '-'), title + ': ' + group, intro, steps,
                              sims=lambda m=mode: {'menu': AltMenuSim(app, m)}))
    return lessons


def screen_key_lesson(app, mode, name, intro, skip=()):
    """The direct keys of one screen (input_parity.SCREEN_KEYS), each with its spoken command."""
    from input_parity import SCREEN_KEYS
    steps = []
    for key, command in SCREEN_KEYS.get(mode, {}).items():
        if key in skip or key == 'Ctrl+F12':
            continue
        label = command.replace(' {value}', '').capitalize()
        step = drill_step(label, key, command, mode)
        if step is not None:
            steps.append(step)
    return Lesson(mode + '-keys', name + ' keys', intro, steps) if steps else None


def task_menu_lesson(app, mode, title, key, name, intro):
    """A list menu from task_navigation: move, then choose each item by key or by name."""
    nav_items = TaskMenuSim(app, mode, title).nav.items(mode)
    steps = [Step('Listen: ' + task_menu_text(app, mode, title) + ' Press Down Arrow to hear the next item.',
                  keys=('Down',), sim='menu', feed=True, screen=mode, command='next')]
    for label, item_key, command in nav_items:
        keys = (key_id(item_key),) if item_key and key_id(item_key) else ()
        if command == 'main menu':
            # Main menu and F1 are the app's own, on every screen.
            steps.append(Step('Choose ' + label + '. Press F1, or say main menu.', keys=('F1',), phrases=('main menu',),
                              reply=app.MAIN_MENU_PROMPT, screen=mode, command='main menu'))
        elif keys:
            spoken = phrase_of(command)
            steps.append(Step('Choose ' + label + '. Press ' + spoken_key(keys[0]) + '.', keys=keys,
                              phrases=(spoken,) if spoken else (), reply='That opens ' + label + '. Here, nothing opens.',
                              screen=mode, command=command))
        else:
            how = 'Use the arrows until you hear ' + label + ', then press Enter. Or say ' + label.lower() + '.'
            steps.append(Step('Choose ' + label + '. ' + how, sim='menu', goal=menu_goal('menu', command), screen=mode,
                              how=how, replay=(('voice', label),)))
    return Lesson(key, name, intro, steps, sims=lambda: {'menu': TaskMenuSim(app, mode, title)})


# The courses --------------------------------------------------------------------------------------
def main_menu_apps(app):
    """Every app on the main menu, with the groups opened: [(name, command)].

    A main menu item that opens a list menu (Office tools, Organizer, Media, Shut down
    or restart, or any group added later) is followed into that list."""
    from task_navigation import LIST_MENUS
    found = []
    for name, command in app.MAIN_MENU_CHOICES:
        sim = TaskMenuSim(app, 'awake', '')
        result = sim.nav.handle(command, 'awake')
        if result in LIST_MENUS:
            for item_name, _, item_command in sim.nav.items(result):
                found.append((item_name, item_command))
        else:
            found.append((name, command))
    return found


def build(app):
    from screen_menus import MENUS
    courses = []
    choices = app.MAIN_MENU_CHOICES
    names = [name for name, _ in choices]

    # Getting around -------------------------------------------------------------------------
    unique = next(i for i, n in enumerate(names) if i >= 2 and [x[0].lower() for x in names].count(n[0].lower()) == 1)
    office = next((i for i, (_, c) in enumerate(choices) if c == 'office tools'), 1)
    menu_steps = [
        Step('You are on the main menu. Press Down Arrow to hear the first item.', keys=(), sim='menu',
             goal=index_goal('menu', 0), how='Press the Down Arrow key once.', screen='awake', replay=(('key', 'Down'),)),
        Step('Press Down Arrow again to hear the next item.', sim='menu', goal=index_goal('menu', 1),
             how='Press the Down Arrow key once more.', screen='awake', replay=(('key', 'Down'),)),
        Step('Press Up Arrow to go back to ' + names[0] + '.', sim='menu', goal=index_goal('menu', 0),
             how='Press the Up Arrow key once.', screen='awake', replay=(('key', 'Up'),)),
        Step('Press End to hear the last item.', sim='menu', goal=index_goal('menu', len(names) - 1),
             how='Press the End key. It is near the arrow keys.', screen='awake', replay=(('key', 'End'),)),
        Step('Press Home to go back to the first item.', sim='menu', goal=index_goal('menu', 0),
             how='Press the Home key.', screen='awake', replay=(('key', 'Home'),)),
        Step('A first letter jumps to an item. Press ' + names[unique][0].upper() + ' to jump to ' + names[unique] + '.',
             sim='menu', goal=index_goal('menu', unique), how='Press the letter ' + names[unique][0].upper() + '.',
             screen='awake', replay=(('key', names[unique][0].upper()),)),
        Step('Now use your voice. Say next.', phrases=('next',), sim='menu', feed=True, screen='awake', command='next',
             how='Say the word next. Or press Alt+T, type next, and press Enter.'),
        Step('Say previous.', phrases=('previous',), sim='menu', feed=True, screen='awake', command='previous',
             how='Say the word previous. Or press Alt+T, type previous, and press Enter.'),
        Step('Open ' + names[office] + '. Move to it and press Enter, or say ' + names[office] + '.', sim='menu',
             goal=menu_goal('menu', choices[office][1]), screen='awake',
             how='Say ' + names[office] + '. Or press Home, then Down Arrow until you hear ' + names[office] +
             ', then press Enter.', replay=(('voice', names[office]),)),
    ]
    groups = []
    for name, command in choices:
        sim = TaskMenuSim(app, 'awake', '')
        result = sim.nav.handle(command, 'awake')
        from task_navigation import LIST_MENUS
        if result in LIST_MENUS:
            groups.append((name, command, result, sim.sandbox.take()))
    group_steps = []
    for name, command, mode, words in groups:
        items = TaskMenuSim(app, mode, name).nav.items(mode)
        group_steps.append(Step('Say ' + name + ' to open it. It holds ' + join(i[0] for i in items) + '.',
                                phrases=(command,), reply=words, screen='awake', command=command))
    first_group = groups[0] if groups else None
    if first_group:
        group_steps.append(Step('In a group, Escape goes back to the main menu. Press Escape.', keys=('Escape',),
                                reply=app.MAIN_MENU_PROMPT, screen=first_group[2], command='escape'))
    basics = [
        Lesson('main-menu', 'Move and choose on the main menu',
               'Every task starts on the main menu. You move with the arrows or your voice, and open the item you hear. '
               'If you have no microphone, press Alt+T, type the words, and press Enter.',
               menu_steps, sims=lambda: {'menu': MainMenuSim(app)}),
        Lesson('groups', 'Open the app groups',
               'Some main menu items are groups of apps. They work like the main menu.', group_steps),
    ]
    everywhere = [
        Step('Press F1. On every screen, F1 goes to the main menu.', keys=('F1',), reply=app.MAIN_MENU_PROMPT,
             screen='awake', command='@main_menu'),
        Step('Press F1 twice quickly. That opens help for the screen you are on.', keys=('Double:F1',),
             reply='On the main menu, that opens the user guide.', screen='awake', command='help'),
        Step('Press Control. It stops speech at once.', keys=('Control',), reply='Speech stops.', screen='awake'),
        Step('Press Alt+T. That is the command box, for typing a command.', keys=('Alt+T',),
             reply='Now type the words what time is it, and press Enter.', screen='awake'),
        Step('Type what time is it, and press Enter.', phrases=('what time is it', 'what time is it?'),
             reply=lambda sims, value: clock_words(app), screen='awake', command='what time is it',
             how='Type the words what time is it, then press Enter. You can also say them.'),
        Step('Press F12. It says the time on every screen. F12 twice quickly says the date.', keys=('F12',),
             reply=lambda sims, value: clock_words(app), screen='awake'),
        Step('Press F3. It says what is playing.', keys=('F3',), reply=lambda sims, value: app.now_playing('awake'),
             screen='awake'),
        Step('Press Alt+O. It opens Options.', keys=('Alt+O',), reply='That opens Options. Here, nothing opens.',
             screen='awake', command='open options'),
        Step('Press Control+F1. It opens Favorite apps, your own short list of apps.', keys=('Ctrl+F1',),
             reply='That opens Favorite apps. Here, nothing opens.', screen='awake', command='@favorites'),
        Step('Press Control+F12. It pauses voice commands. Press it again to wake up.', keys=('Ctrl+F12',),
             reply='The app says: ' + app.sleep_message().split('.')[0] + '. Here, it stays awake.', screen='awake',
             command='go to sleep'),
        Step('Press F9. It turns the microphone fully off or on.', keys=('F9',),
             reply='Here, the microphone stays as it is.', screen='awake'),
        Step('Say main menu. It works on every screen, like F1.', phrases=('main menu', 'back to main menu'),
             reply=app.MAIN_MENU_PROMPT, screen='awake'),
    ]
    basics.append(Lesson('everywhere', 'Keys that work everywhere',
                         'These keys work on every screen. Learn them first. Here, they only practice.', everywhere))
    courses.append(Course('basics', 'Getting around', ('getting around', 'getting started', 'basics', 'main menu',
                                                         'keys', 'start'), basics))

    # Alt menus ----------------------------------------------------------------------------------
    alt_title, alt_groups = MENUS['note']
    second = alt_groups[1] if len(alt_groups) > 1 else alt_groups[0]
    target = next(label for label, _, command in second[1] if not command.startswith('@'))
    target_command = next(command for label, _, command in second[1] if label == target)
    alt_steps = [
        Step('This is a note. Press Alt to open its menu.', sim='menu', goal=lambda s: s['menu'].is_open(),
             how='Press the Alt key once and let it go.', screen='note', replay=(('key', 'Alt'),)),
        Step('The menu has groups. Press Down Arrow to move to the ' + second[0] + ' group.', sim='menu', screen='note',
             goal=lambda s: s['menu'].menu_object.group is None and s['menu'].menu_object.index == 1,
             how='Press the Down Arrow key once.', replay=(('key', 'Down'),)),
        Step('Press Enter to open the ' + second[0] + ' group.', sim='menu', screen='note',
             goal=lambda s: s['menu'].menu_object.group == 1, how='Press Enter.', replay=(('key', 'Enter'),)),
        Step('Press Escape to go back to the groups. Escape goes back one level.', keys=('Escape',), sim='menu', feed=True,
             screen='note'),
        Step('Press 2 to open the ' + second[0] + ' group at once. A number opens a group or chooses an item.', sim='menu',
             screen='note', goal=lambda s: s['menu'].menu_object.group == 1, how='Press the number 2 key.',
             replay=(('key', '2'),)),
        Step('Choose ' + target + '. Press its first letter, ' + target[0].upper() + ', then press Enter.', sim='menu',
             screen='note', goal=menu_goal('menu', target_command),
             how='Press the letter ' + target[0].upper() + ' until you hear ' + target + '. Then press Enter.',
             replay=(('voice', target),)),
        Step('Each item says its key, so next time you can press the key itself. Press Alt to open the menu, then Alt '
             'again to close it.', sim='menu', screen='note', goal=lambda s: getattr(s['menu'], 'closed_once', False),
             how='Press Alt to open the menu. Then press Alt again.', replay=(('key', 'Alt'), ('key', 'Alt'))),
    ]

    def alt_sims():
        sim = AltMenuSim(app, 'note')
        original = sim.feed

        def feed(kind, value):
            was_open = sim.is_open()
            result = original(kind, value)
            if was_open and not sim.is_open() and sim.chosen is None:
                sim.closed_once = True
            return result
        sim.feed = feed
        return {'menu': sim}
    courses.append(Course('alt', 'Alt menus', ('alt menus', 'alt menu', 'alt', 'menus'), [
        Lesson('alt-menus', 'Use an Alt menu', 'On most screens, Alt opens a menu of that screen\'s actions. '
               'Each item says its key and its voice command.', alt_steps, sims=alt_sims)]))

    # Word processor ------------------------------------------------------------------------------
    doc_intro = 'This is a practice document. It is deleted when the lesson ends.'
    writing = [
        Step('Say a short sentence, such as: The red fox ran home. Or press Alt+T, type it, and press Enter.', text=True,
             sim='doc', example='The red fox ran home.', screen='document'),
        Step('Say read paragraph to hear it.', phrases=('read paragraph',), sim='doc', feed=True, screen='document',
             command='read paragraph'),
        Step('Say go to beginning of document.', phrases=('go to beginning of document',), sim='doc', feed=True,
             screen='document', command='go to beginning of document'),
        Step('Say next word.', phrases=('next word',), sim='doc', feed=True, screen='document', command='next word'),
        Step('Say select red fox. Choose words by saying them.', phrases=('select red fox',), sim='doc', feed=True,
             screen='document', command='select red fox',
             how='Say select red fox. If your sentence has other words, say select and two of its words.'),
        Step('Press Control+B to make the chosen words bold.', keys=('Ctrl+B',), phrases=('toggle bold', 'make this bold'),
             reply=lambda s, v: doc_feed(s, 'make this bold'), screen='document', command='toggle bold',
             replay=()),
        Step('Press Control+Z to undo that.', keys=('Ctrl+Z',), phrases=('undo',), reply=lambda s, v: doc_feed(s, 'undo'),
             screen='document', command='undo'),
        Step('Press Control+S to save. Here, the practice file is not kept.', keys=('Ctrl+S',), phrases=('save document',),
             reply='The app says: Saved the Word document, and its name.', screen='document', command='save document'),
        Step('Say leave document. Companion asks whether to save. Here, nothing is saved.',
             phrases=('leave document',), reply='Save this document? Yes or no. Use arrows to choose, then Enter. '
             'Escape keeps editing.', screen='document', command='leave document'),
        Step('Press N, for No. The answer keys are Y and N.', keys=('N',), phrases=('no',),
             reply='That leaves without saving the latest changes.', screen='document_save', command='no'),
    ]
    naming = [
        Step('Listen: ' + task_menu_text(app, 'word_processor', 'Word processor menu') +
             ' Press Control+N to create a document.', sim='menu', goal=menu_goal('menu', 'create a document'),
             keys=(), screen='word_processor', how='Hold Control and press N.', replay=(('key', 'Ctrl+N'),)),
        Step('Companion asks: Please say or type the name for your document, then press Enter or say confirm. '
             'Say a name, such as My letter.', text=True, sim='name', example='My letter', feed=True,
             screen='document_name'),
        Step('Say confirm, or press Enter.', keys=('Enter',), phrases=('confirm',),
             reply=lambda s, v: 'New document, ' + (s['name'].value or 'Untitled') + '. Speak or type to write. '
                                'For help, say help with documents, or press F1 twice.',
             screen='document_name', command='confirm'),
    ]
    from task_navigation import DOCUMENT_ACTIONS
    document = [
        Lesson('create', 'Create and name a document', 'The Word processor menu opens first. Here, no file is made.',
               naming, sims=lambda: {'menu': TaskMenuSim(app, 'word_processor', 'Word processor menu'),
                                     'name': MemoSim(lambda name: name + '. Press Enter or say confirm to use this name.')}),
        Lesson('write', 'Write, read and fix', doc_intro, writing, sims=lambda: {'doc': EditorSim('document')}),
    ]
    for group, entries in DOCUMENT_ACTIONS.items():
        steps = []
        for label, key, command in entries:
            step = drill_step(label, key, command, 'document')
            if step is None and key.startswith('Alt, '):
                digits = key[len('Alt, '):].split(', ')
                step = Step(label + '. Press Alt, then ' + ', then '.join(digits) + '.', sim='docmenu',
                            goal=menu_goal('docmenu', command), screen='document', command=command,
                            how='Press Alt, then ' + ', then '.join(digits) + '. Press each key once.',
                            replay=(('key', 'Alt'),) + tuple(('key', d) for d in digits))
            if step is not None:
                steps.append(step)
        document.append(Lesson('menu-' + plain(group).replace(' ', '-'), 'Document menu: ' + group,
                               'Each action has a key, or words to say, in a document. Here, nothing changes.', steps,
                               sims=lambda: {'docmenu': DocumentMenuSim(app)}))
    document.append(task_menu_lesson(app, 'word_processor', 'Word processor menu', 'wp-menu', 'Word processor menu',
                                     'The Word processor menu has four choices.'))
    courses.append(Course('document', 'Word processor', ('word processor', 'documents', 'document', 'writing'), document,
                          apps=('word processor',)))

    # Email --------------------------------------------------------------------------------------
    compose = [
        Step('Say write an email. Or press N in your inbox.', phrases=('write an email', 'new email', 'write email',
                                                                        'compose email', 'new message'),
             reply='New email. To field. Who do you want to send the email to? Type an address, or say a saved contact name.',
             screen='awake', command='write an email'),
        Step('Say or type an address, such as sam at example dot com. Here, type sam@example.com.', text=True,
             sim='mail', example='sam@example.com', screen='email_draft'),
        Step('Say a subject, such as Lunch on Friday.', text=True, sim='mail', example='Lunch on Friday',
             screen='email_draft'),
        Step('Say your message, such as: Are you free at noon?', text=True, sim='mail', example='Are you free at noon?',
             screen='email_draft'),
        Step('Say read subject to check it.', phrases=('read subject',), sim='mail', feed=True, screen='email_draft',
             command='read subject'),
        Step('Press Control+R to hear the message.', keys=('Ctrl+R',), phrases=('read email draft',), sim='mail',
             reply=lambda s, v: s['mail'].feed('voice', 'read email draft'), screen='email_draft', command='read email draft'),
        Step('Say send it. Companion reads it all back first. Nothing is sent before your Yes.',
             phrases=SEND_WORDS, keys=('Alt+S', 'Ctrl+Enter'), reply=send_review, screen='email_draft', command='send email'),
        Step('Say no, or press N, to keep it as a draft. Here, nothing is ever sent.', keys=('N',),
             phrases=('no', 'cancel send'), reply='Sending canceled. The email remains a local draft.',
             screen='email_draft', command='no'),
    ]

    def mail_sims():
        return {'mail': EditorSim('email', compose_step='recipient')}
    reading = [
        Step('This is your inbox. Press Down Arrow for the next message.', sim='box', keys=(),
             goal=lambda s: s['box'].current == 2, how='Press the Down Arrow key once.', screen='mailbox',
             replay=(('key', 'Down'),)),
        Step('Press Up Arrow to go back to the first message.', sim='box', goal=lambda s: s['box'].current == 1,
             how='Press the Up Arrow key once.', screen='mailbox', replay=(('key', 'Up'),)),
        Step('Press Alt+1 to hear who it is from. Alt+1 to Alt+6 read the header.', keys=('Alt+1',), sim='box', feed=True,
             phrases=('who is it from',), screen='mailbox', command='who is it from'),
        Step('Press Enter to open the message.', sim='box', goal=lambda s: s['box'].view == 'message', how='Press Enter.',
             screen='mailbox', replay=(('key', 'Enter'),)),
        Step('Press R to reply. Here, nothing is written.', keys=('R',), phrases=('reply',),
             reply='That starts a reply. The To and Subject are filled in for you.', screen='mailbox', command='reply'),
        Step('Press Escape to go back to the inbox.', sim='box', goal=lambda s: s['box'].view == 'folder',
             how='Press Escape.', screen='mailbox', replay=(('key', 'Escape'),)),
    ]
    email = [
        Lesson('read', 'Read your inbox', 'These are practice messages. Your real email is not touched.', reading,
               sims=lambda: {'box': MailboxSim()}),
        Lesson('write', 'Write and check an email', 'This is a practice email. It is never sent.', compose, sims=mail_sims),
    ]
    email += [l for l in (screen_key_lesson(app, 'mailbox', 'Inbox', 'One letter for each action in the inbox. '
                                                                        'Here, nothing changes.', skip=('F1',)),
                          screen_key_lesson(app, 'email_draft', 'Email draft', 'Keys while you write an email.',
                                            skip=('F1',))) if l]
    email += alt_menu_lessons(app, 'mailbox', 'Every inbox action is in this menu. Here, nothing changes.')
    email += alt_menu_lessons(app, 'email_draft', 'Every draft action is in this menu. Here, nothing is sent.')
    courses.append(Course('email', 'Email', ('email', 'mail', 'e mail'), email, apps=('email',)))

    # Web browser ----------------------------------------------------------------------------------
    browser = BrowserMenuSim()
    browser_opening = browser.opening
    browser.close()
    web_menu = [
        Step('Listen: ' + browser_opening + ' Press Down Arrow to hear the first choice.', sim='menu',
             goal=lambda s: s['menu'].menu_object.index == 0, how='Press the Down Arrow key once.', screen='browser_menu',
             replay=(('key', 'Down'),)),
        Step('Press Enter to choose Search or enter address.', sim='menu', goal=menu_goal('menu', 'search'),
             how='Press Enter while you hear Search or enter address.', screen='browser_menu',
             replay=(('key', 'Enter'),)),
        Step('Companion says: Web address or search. Say or type an address or a search, then press Enter. '
             'Addresses do not need www or https. Escape cancels. Type weather.gov and press Enter.', text=True,
             reply='In the real app, the page opens. Companion says Page loaded, the page title, and the site. '
                   'Here, no website opens.',
             screen='search'),
    ]
    page = [
        Step('This is a practice page. Press Down Arrow to read the next line.', sim='page',
             goal=lambda s: s['page'].position == 1, how='Press the Down Arrow key once.', screen='web',
             replay=(('key', 'Down'),)),
        Step('Press H to move to the next heading.', sim='page', goal=lambda s: s['page'].position == 3,
             how='Press the letter H.', screen='web', replay=(('key', 'H'),)),
        Step('Press Shift+H to go back to the heading before.', sim='page', goal=lambda s: s['page'].position == 0,
             how='Hold Shift and press H.', screen='web', replay=(('key', 'Shift+H'),)),
        Step('Press K to move to the next link.', sim='page', goal=lambda s: s['page'].position == 2,
             how='Press the letter K.', screen='web', replay=(('key', 'K'),)),
        Step('Press E to move to the next text box. You can type there at once.', sim='page',
             goal=lambda s: s['page'].position == 4, how='Press the letter E.', screen='web', replay=(('key', 'E'),)),
        Step('Press Tab to move to the next control.', sim='page', goal=lambda s: s['page'].position == 5,
             how='Press the Tab key.', screen='web', replay=(('key', 'Tab'),)),
        Step('Press Enter to use the Search button. Here, nothing is sent.', sim='page',
             goal=menu_goal('page', 'button:Search'), how='Press Enter.', screen='web', replay=(('key', 'Enter'),),
             reply='That presses the button. The site decides what happens next.'),
        Step('Press Control+L to type a new address while you read a page.', keys=('Ctrl+L',),
             reply='Web address or search. Say or type an address or a search, then press Enter. '
                   'Addresses do not need www or https. Escape cancels.', screen='web'),
        Step('Press Escape. On a page, Escape opens the Web browser menu.', keys=('Escape',),
             reply='Web browser menu.', screen='web'),
    ]
    web = [
        Lesson('menu', 'Open an address', 'The Web browser menu opens first. Here, no website opens.', web_menu,
               sims=lambda: {'menu': BrowserMenuSim()}),
        Lesson('page', 'Read a page', 'Page keys move by line, heading, link, and text box.', page,
               sims=lambda: {'page': PageSim()}),
    ]
    web += [l for l in (screen_key_lesson(app, 'web', 'Web page', 'Keys while you read a page.', skip=('F1',)),) if l]
    web += alt_menu_lessons(app, 'web', 'Every page action is in this menu. Here, no website opens.')
    courses.append(Course('web', 'Web browser', ('web browser', 'web', 'browser', 'internet'), web,
                          apps=('web browser',)))

    # File manager ---------------------------------------------------------------------------------
    from file_manager import GROUPS
    files = [Lesson('move', 'Move through files', 'These are practice files. Your own files are not touched.', [
        Step('This is File manager. Press Down Arrow for the next item.', sim='list', goal=index_goal('list', 1),
             how='Press the Down Arrow key once.', screen='files', replay=(('key', 'Down'),)),
        Step('Press End to reach the last item.', sim='list', goal=index_goal('list', 2), how='Press End.',
             screen='files', replay=(('key', 'End'),)),
        Step('Press Home to reach the first item.', sim='list', goal=index_goal('list', 0), how='Press Home.',
             screen='files', replay=(('key', 'Home'),)),
        Step('Press Enter to open the folder you hear.', sim='list', goal=menu_goal('list', 'open folder'),
             how='Press Enter.', screen='files', replay=(('key', 'Enter'),)),
        Step('Press Escape to go back to the folder above.', keys=('Escape',), reply='That goes up one folder.',
             screen='files', command='escape'),
        Step('Press Alt to open the File manager menu. Every action and its key is there.', keys=('Alt',),
             reply='File manager menu. Here, nothing changes.', screen='files', command='file manager menu'),
    ], sims=lambda: {'list': FileListSim()})]
    for group_key, (title, entries) in GROUPS.items():
        steps = [s for s in (drill_step(label, key, command, 'files') for label, key, command in entries) if s]
        files.append(Lesson('menu-' + group_key, 'File manager: ' + title, 'Here, no file changes.', steps))
    courses.append(Course('files', 'File manager', ('file manager', 'files', 'folders'), files, apps=('file manager',)))

    # Notepad ------------------------------------------------------------------------------------------
    notepad = [task_menu_lesson(app, 'notepad_menu', 'Notepad menu', 'menu', 'Notepad menu', 'Notepad opens on its menu.')]
    notepad += [l for l in (screen_key_lesson(app, 'note', 'Note', 'Keys while you write a note. Here, nothing is saved.',
                                              skip=('F1',)),) if l]
    notepad += alt_menu_lessons(app, 'note', 'Every note action is in this menu.')
    courses.append(Course('notepad', 'Notepad', ('notepad', 'notes', 'note'), notepad, apps=('notepad',)))

    # Document reader ------------------------------------------------------------------------------------
    reader = [task_menu_lesson(app, 'reader_menu', 'Document reader menu', 'menu', 'Document reader menu',
                               'Document reader opens on its menu. It reads files without changing them.')]
    reader += [l for l in (screen_key_lesson(app, 'file_reader', 'Document reader', 'Keys while you read a file.',
                                             skip=('F1',)),) if l]
    reader += alt_menu_lessons(app, 'file_reader', 'Every reading action is in this menu.')
    courses.append(Course('reader', 'Document reader', ('document reader', 'reader'), reader, apps=('document reader',)))

    # Address manager and Schedule manager -------------------------------------------------------------------
    contacts = [l for l in (screen_key_lesson(app, 'contacts', 'Address manager', 'Keys in your contact list. '
                                                                                 'Here, no contact changes.',
                                              skip=('F1',)),) if l]
    contacts += alt_menu_lessons(app, 'contacts', 'Every contact action is in this menu.')
    courses.append(Course('contacts', 'Address manager', ('address manager', 'contacts', 'address book'), contacts,
                          apps=('contacts',)))
    calendar = [l for l in (screen_key_lesson(app, 'calendar', 'Schedule manager', 'Keys in your calendar. '
                                                                                  'Here, no event changes.',
                                              skip=('F1',)),) if l]
    calendar += alt_menu_lessons(app, 'calendar', 'Every calendar action is in this menu.')
    courses.append(Course('calendar', 'Schedule manager', ('schedule manager', 'calendar', 'schedule'), calendar,
                          apps=('calendar',)))

    # Media ------------------------------------------------------------------------------------------------
    for section, name, aliases, app_command in (('radio', 'Radio', ('radio', 'stations'), 'radio'),
                                                ('podcast', 'Podcasts', ('podcasts', 'podcast'), 'podcasts')):
        sim = MediaSim(section)
        actions = list(sim.nav.actions)
        opening_words = sim.opening
        steps = [Step('Listen: ' + opening_words + ' Press Down Arrow to hear the next action.', sim='media', screen='media',
                      goal=lambda s: (s['media'].nav.index or 0) == 1, how='Press the Down Arrow key once.',
                      replay=(('key', 'Down'),))]
        for action in actions:
            steps.append(Step(action.label + '. Move to it and press Enter, or say ' + action.label.lower() + '.',
                              sim='media', screen='media', goal=menu_goal('media', action.label),
                              how='Say ' + action.label.lower() + '. Or use the arrows until you hear it, then press Enter.',
                              replay=(('voice', action.label),)))
        courses.append(Course(section, name, aliases, [
            Lesson('actions', name + ' actions', 'The actions list has every ' + name + ' task. Here, nothing plays.',
                   steps, sims=lambda sec=section: {'media': MediaSim(sec)})], apps=(app_command,)))
    player = [task_menu_lesson(app, 'local_media', 'Media player', 'menu', 'Media player',
                               'Media player plays files on your computer. Here, nothing plays.')]
    courses.append(Course('player', 'Media player', ('media player', 'player'), player, apps=('media player',)))
    youtube = [l for l in (screen_key_lesson(app, 'youtube', 'YouTube', 'One key for each video action, most as on '
                                                                        'YouTube itself. Here, nothing plays.',
                                             skip=('F1',)),) if l]
    youtube += alt_menu_lessons(app, 'youtube', 'Every YouTube action is in this menu.')
    courses.append(Course('youtube', 'YouTube', ('youtube', 'videos'), youtube, apps=('youtube',)))

    # Options -----------------------------------------------------------------------------------------------
    from settings_model import CATEGORIES
    options_steps = [
        Step('Press Alt+O to open Options.', keys=('Alt+O',), phrases=('options', 'open options'),
             reply=announce_item(CATEGORIES[0], 0, len(CATEGORIES)), screen='awake', command='open options'),
        Step('Press Down Arrow to hear the next category.', sim='cats', goal=index_goal('cats', 1),
             how='Press the Down Arrow key once.', screen='settings', replay=(('key', 'Down'),)),
        Step('Press Enter to open that category.', keys=('Enter',),
             reply=lambda s, v: s['cats'].items[s['cats'].index][0] + ' options dialog. Here, no setting changes.', screen='settings'),
        Step('Press Tab to reach a control. In a choice, the arrows change it. On a checkbox, Space changes it.',
             keys=('Tab',), reply='Each control says its name and its value.', screen='settings'),
        Step('Press Escape to close Options without saving. Choose OK to save.', keys=('Escape',),
             reply='Options closed. Main menu. Pressing Enter in a setting, or choosing OK, saves instead.', screen='settings', command='cancel settings'),
    ]
    courses.append(Course('options', 'Options', ('options', 'settings'), [
        Lesson('use', 'Change an option', 'Options has a category for each part of the app. Here, no setting changes.',
               options_steps, sims=lambda: {'cats': ListSim('Options', [(c, c) for c in CATEGORIES])})],
        apps=('options',)))

    # Help and updates -------------------------------------------------------------------------------------------
    try:
        help_opening = HelpSim(app).opening
    except (OSError, ValueError):
        help_opening = None      # the guide is missing or damaged: Help says so; practice the rest
    help_steps = [] if help_opening is None else [
        Step('Listen: ' + str(help_opening) + ' Press Down Arrow to hear the next topic.', sim='help', screen='help',
             goal=lambda s: s['help'].session.topic_index == 1, how='Press the Down Arrow key once.',
             replay=(('key', 'Down'),)),
        Step('Press Enter to open the topic.', sim='help', screen='help', goal=lambda s: s['help'].session.level != 'topics',
             how='Press Enter.', replay=(('key', 'Enter'),)),
        Step('Press Escape to go back to the topics.', sim='help', screen='help',
             goal=lambda s: s['help'].session.level == 'topics', how='Press Escape.', replay=(('key', 'Escape'),)),
        Step('Say help with email to go straight to a topic.', phrases=('help with email',), sim='help', feed=True,
             screen='help', command='help with email'),
        Step('Say close help to go back to your work.', phrases=('close help',), sim='help', feed=True, screen='help',
             command='close help'),
    ]
    help_steps += [
        Step('Say check for updates. Companion looks for a newer version.', phrases=('check for updates',),
             reply='If there is one, Yes starts the update and No keeps this version. Here, nothing changes.',
             screen='awake', command='check for updates'),
        Step('Say release notes to hear what changed.', phrases=('release notes', "what's new"),
             reply='That opens the release notes in Help.', screen='awake', command='release notes'),
    ]
    help_lessons = [Lesson('help', 'Use Help and updates', 'Help reads the user guide to you.', help_steps,
                           sims=lambda: {'help': HelpSim(app)} if help_opening is not None else {})]
    help_lessons += alt_menu_lessons(app, 'help', 'Every Help action is in this menu.')
    courses.append(Course('help', 'Help and updates', ('help and updates', 'help', 'updates'), help_lessons,
                          apps=('help', 'check for updates')))

    # Sleep, shut down and exit ----------------------------------------------------------------------------------
    power_steps = [
        Step('Say go to sleep. Companion stops listening until you wake it.', phrases=('go to sleep',),
             reply=app.sleep_message() + ' Here, it stays awake.', screen='awake', command='go to sleep'),
        Step('Say wake up.', phrases=('wake up',), reply='Companion wakes up on the screen you left.', screen='sleep',
             command='wake up'),
        Step('Say exit Companion. It asks first.', phrases=('exit companion', 'exit voice companion', 'close companion'),
             keys=('Alt+F4',), reply='Exit Voice Companion? Are you sure? Yes or no. Use arrows or Tab to choose, '
                                     'then Enter. Escape cancels.', screen='awake', command='exit companion'),
        Step('Press N, for No, to stay.', keys=('N',), phrases=('no',), reply='Canceled. Main menu. Companion stays open.',
             screen='exit_confirm', command='no'),
    ]
    power = [Lesson('sleep', 'Sleep and exit', 'Here, nothing closes or shuts down.', power_steps)]
    power.append(task_menu_lesson(app, 'power_menu', 'Shut down or restart', 'power', 'Shut down or restart',
                                  'Each choice asks first. Here, nothing shuts down.'))
    courses.append(Course('power', 'Sleep and exit', ('sleep and exit', 'sleep', 'exit', 'shut down'), power,
                          apps=('exit companion', 'shut down computer', 'restart computer')))
    return courses


SEND_WORDS = ('send it', 'send email', 'send the email', 'send this email', 'send that', 'send this', 'send',
              'send my email', 'send now', 'send it now', 'send the message', 'please send it', 'please send')


def join(names):
    names = list(names)
    if len(names) < 3:
        return ' and '.join(names)
    return ', '.join(names[:-1]) + ', and ' + names[-1]


def clock_words(app):
    """The time, as F12 says it."""
    import time_date
    return time_date.announcement('time', app.CLOCK())


def doc_feed(sims, command):
    return sims['doc'].feed('voice', command) if 'doc' in sims else ''


def send_review(sims, value=None):
    draft = sims['mail'].editor
    body = ' '.join(p.text for p in draft.paragraphs).strip()
    subject = draft.subject or 'no subject'
    sentence = lambda text: text if text.rstrip().endswith(('.', '?', '!')) else text.rstrip() + '.'
    return ('Review before sending. From your email account. To ' + (draft.recipient or 'no one yet') + '. ' +
            sentence('Subject ' + subject) + ' ' + sentence('Message: ' + (body or 'no message body')) +
            ' Is that right? Press Y or N, or use arrows or Tab and Enter. Escape keeps the draft. '
            'You can also say yes to send or no to keep it.')
