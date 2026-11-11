"""Practice copies of the app's screens for the tutorial, run by the app's own code.

Each screen here is the real one, cut off from your data and the outside world:
- Address manager and Schedule manager run contacts_screen and calendar_screen. They are
  loaded as private copies, so the real screens' state is never touched. Contacts are kept
  in a temporary folder; Thunderbird is replaced by a practice calendar in memory.
- Radio and Podcasts run the real MediaHub and MediaNavigation, with sample stations and
  shows instead of the internet, a pretend audio player, and no recording to disk.
- YouTube runs the real YouTubeScreen with a pretend page: no browser opens.
- File manager runs the real FileManager on files that exist only in memory.
- Document reader opens a sample document from a temporary folder with the real reader.
- Notepad keeps the note in memory and saves into a temporary folder with the real notepad.

Every temporary folder is deleted when the lesson ends (Sim.close).
"""
import importlib.util
import itertools
import shutil
import tempfile
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

from tutorial_engine import Sandbox, Sim, canonical_key

def private(name, **replace):
    """A private copy of one of the app's modules, with some of its names replaced.

    The code comes from the module's own loader, so this also works in the installed app,
    where modules are packed and there is no .py file to read."""
    import types
    spec = importlib.util.find_spec(name)
    code = spec.loader.get_code(name)
    module = types.ModuleType('tutorial_' + name)
    module.__file__ = spec.origin
    module.__dict__.update(replace)
    exec(code, module.__dict__)
    module.__dict__.update(replace)     # the module's own imports would put the real ones back
    return module


class NoAccounts:
    """No email account: the practice screens use only what is on this computer (here, nothing)."""

    def __init__(self, *args, **kwargs):
        pass

    def selected(self):
        return None

    def accounts(self):
        return []


def practice_box(app):
    """A stand-in app for the module screens, with a temporary data folder."""
    box = Sandbox(app)
    box.APP = Path(tempfile.mkdtemp(prefix='vc-tutorial-'))
    box.ProtectedStore = NoAccounts
    box.writing_dictation = lambda *a, **k: False
    box.sync_app_context = lambda *a, **k: None
    box.clock_text_entry = lambda *a, **k: False
    box.speak_status = box.speak
    box.choose_menu_letter = lambda *a, **k: None
    for name in ('VOICE_LIST_COMMANDS', 'PICK_CONFIRM', 'CLOCK'):
        setattr(box, name, getattr(app, name))
    box.EMAIL_LINK_RECIPIENT = None
    return box


class ScreenSim(Sim):
    """A screen written as a module of functions (contacts_screen, calendar_screen), run as the
    app runs it: keys through navigation_key, words through handle, and its typed questions
    through the real TaskNavigation prompt."""

    def __init__(self, app, module, mode, title):
        from task_navigation import TaskNavigation
        self.app = app
        self.box = practice_box(app)
        self.module = module
        self.screen = self.mode = mode
        self.title = title
        self.nav = TaskNavigation(self.box)
        self.box.task_navigation = lambda: self.nav
        self.box.open_named_list = self.named_list
        self.box.handle = self.dispatch
        self.listing = None

    def named_list(self, title, items):
        self.listing = (title, items)
        return title

    def dispatch(self, command, mode, typed=False):
        if mode != self.screen:
            # The screen hands this to another part of the app (an email, the main menu): here it stops.
            self.chosen = command
            return self.screen
        result = self.module.handle(self.box, command, mode, typed)
        if result is None:
            self.chosen = command
            return self.screen
        if result not in (self.screen, 'task_input'):
            self.chosen = result        # the screen was left (Escape): here it stays open
        return result

    def open(self):
        opener = getattr(self.module, 'open_screen', None) or self.module.open_manager
        opener(self.box, 'awake')
        self.opening = self.box.take()
        return self.opening

    def menu(self):
        if self.mode == 'task_input':
            return None
        return self.module.menu_state(self.box) if hasattr(self.module, 'menu_state') else None

    def set_mode(self, result):
        if result in (self.screen, 'task_input'):
            self.mode = result

    def feed(self, kind, value):
        from input_parity import screen_command
        if kind == 'key':
            key = canonical_key(value)
            if self.mode == 'task_input':
                request = {'Escape': 'cancel', 'Enter': '@task:skip'}.get(key)
                if request is None:
                    return None
                self.set_mode(self.nav.handle(request, 'task_input') or self.screen)
                return self.box.take() or None
            request = None
            if self.module.PENDING is None:
                request = screen_command(key, self.screen)   # the screen's own keys (input_parity.SCREEN_KEYS)
            if request and request.startswith('@prompt:'):
                self.set_mode(self.nav.action(request[len('@prompt:'):], self.screen))
                return self.box.take() or None
            if not request:
                if len(key) == 1 and key.isalpha():
                    # In a question the window sends the letter itself (Y, N); in a list, a letter to jump.
                    key = key.lower() if self.module.PENDING is not None else 'Letter:' + key.lower()
                request = self.module.navigation_key(self.box, key)
            if not request:
                return self.box.take() or None
            value = request
        if self.mode == 'task_input':
            self.set_mode(self.nav.handle(value, 'task_input') or self.screen)
            return self.box.take() or None
        self.set_mode(self.dispatch(value, self.screen, kind == 'key'))
        return self.box.take() or None

    def close(self):
        shutil.rmtree(self.box.APP, ignore_errors=True)


def contacts_sim(app):
    """Address manager with no Thunderbird and an empty address book in a temporary folder."""
    pim = private('thunderbird_pim')
    pim.usable = lambda folder: False
    pim.connected = lambda: False
    book = private('contacts_book', thunderbird_pim=pim)
    screen = private('contacts_screen', contacts_book=book, thunderbird_pim=pim)
    sim = ScreenSim(app, screen, 'contacts', 'Address manager')
    sim.open()
    return sim


def downloads_sim(app):
    """Downloads with three practice downloads, in a temporary folder. No browser is asked."""
    import json
    model = private('downloads')
    folder = Path(tempfile.mkdtemp(prefix='vc-tutorial-downloads-'))
    files = folder / 'Downloads'
    files.mkdir()
    records = []
    for n, (name, state) in enumerate((('Bus schedule.pdf', 'finished'), ('Recipes.docx', 'finished'),
                                       ('Family photos.zip', 'finished'))):
        path = files / name
        if state == 'finished':
            path.write_bytes(b'practice')
        records.append({'id': 'practice-' + str(n), 'source': 'chrome', 'ref': str(n), 'name': name, 'path': str(path),
                        'url': 'https://www.example.com/' + name.replace(' ', '-'), 'state': state, 'received': 2048,
                        'total': 2048 if state == 'finished' else 8192, 'created': 1000.0 - n})
    (folder / 'download-history.json').write_text(json.dumps(records), encoding='utf-8')
    manager = model.DownloadManager(folder, folder_setting=lambda: str(files), background=False)
    model.manager = lambda data_folder=None: manager
    screen = private('download_screen', downloads=model)
    sim = ScreenSim(app, screen, 'downloads', 'Downloads')
    sim.box.APP = folder
    sim.box.FILE_MANAGER = None
    sim.box.SLEEP_RETURN_MODE = 'awake'
    sim.box.PREFERENCES = {'download_folder': str(files)}
    sim.open()
    return sim


class PracticeCalendar:
    """Thunderbird's calendar, as the add-on answers (thunderbird_pim.call), kept in memory."""

    def __init__(self, today):
        import calendar_events
        self.events = []
        self.ids = itertools.count(1)
        start = datetime.combine(today, clock_time(10, 30))
        self.add(calendarId='practice', title='Doctor appointment', allDay=False, start=calendar_events.utc_ms(start),
                 end=calendar_events.utc_ms(start + timedelta(minutes=30)), location='VA clinic', notes='')

    def add(self, **event):
        event = dict(event, id='practice-' + str(next(self.ids)), calendar='Practice', recurring=False)
        self.events.append(event)
        return {'id': event['id']}

    def call(self, method, **params):
        if method == 'calendars':
            return [{'id': 'practice', 'name': 'Practice', 'account': ''}]
        if method == 'events':
            return {'events': [dict(e) for e in self.events if e['allDay'] or e['end'] >= params['start'] and e['start'] <= params['end']]}
        if method == 'addEvent':
            return self.add(**{k: params.get(k) for k in ('calendarId', 'title', 'allDay', 'start', 'end', 'location', 'notes')})
        if method == 'modifyEvent':
            event = next(e for e in self.events if e['id'] == params['id'])
            event.update(params['changes'])
            return {'id': event['id']}
        if method == 'deleteEvent':
            self.events = [e for e in self.events if e['id'] != params['id']]
            return {}
        return {}


def calendar_sim(app):
    """Schedule manager with one practice calendar holding a doctor appointment today."""
    pim = private('thunderbird_pim')
    calendar = PracticeCalendar(app.CLOCK().date())
    pim.usable = lambda folder: True
    pim.connected = lambda: True
    pim.call = calendar.call
    screen = private('calendar_screen', thunderbird_pim=pim)
    sim = ScreenSim(app, screen, 'calendar', 'Schedule manager')
    sim.calendar = calendar
    sim.open()
    return sim


# Radio and Podcasts -------------------------------------------------------------------------
class PracticeAudio:
    """The audio player, as the real one behaves (media_player.MediaPlayer.control), playing nothing."""

    def __init__(self):
        self.kind = None
        self.title = ''
        self.paused = True
        self.position = 0.0
        self.duration = None
        self.volume = 0.5
        self.rate = 1.0
        self.failed = False
        self.loading = False

    def open(self, url, title, kind):
        self.kind, self.title, self.paused, self.position = kind, title, False, 0.0
        self.duration = None if kind == 'radio' else 1800.0

    def close(self):
        self.kind = None

    def streaming(self):
        return self.kind is not None and not self.paused

    def health(self):
        return {'state': 'playing' if self.streaming() else 'paused'}

    def status(self):
        if not self.kind:
            raise ValueError('Open a media file first.')
        return {'paused': self.paused, 'position': self.position, 'duration': self.duration, 'failed': False}

    def control(self, action, seconds=15, position=None):
        if not self.kind:
            return None
        if action == 'toggle':
            self.paused = not self.paused
            return self.paused
        if action == 'stop':
            self.paused, self.position = True, 0.0
            return 0
        if action in ('pause', 'play'):
            self.paused = action == 'pause'
            return self.position
        if action == 'position':
            return self.position
        if action == 'seek':
            if self.duration is None:
                return None
            target = self.position + seconds if position is None else position
            self.position = max(0.0, min(self.duration, target))
            return self.position
        return None

    def adjust(self, setting, value):
        if not self.kind:
            raise ValueError('Open a media file first.')
        if setting == 'volume':
            self.volume = max(0.0, min(1.0, round(self.volume + value, 2)))
            return self.volume
        self.rate = value
        return value

    def set_ducked(self, *args, **kwargs):
        pass


STATIONS = [
    {'name': 'Jazz 24', 'url': 'https://stream.example.com/jazz24', 'country': 'United States', 'state': 'Washington',
     'tags': 'jazz', 'codec': 'MP3', 'stationuuid': 'practice-1', 'lastcheckok': 1},
    {'name': 'Smooth Jazz Florida', 'url': 'https://stream.example.com/smooth', 'country': 'United States',
     'state': 'Florida', 'tags': 'jazz,smooth jazz', 'codec': 'MP3', 'stationuuid': 'practice-2', 'lastcheckok': 1},
    {'name': 'Classic Country Radio', 'url': 'https://stream.example.com/country', 'country': 'United States',
     'state': 'Texas', 'tags': 'country', 'codec': 'MP3', 'stationuuid': 'practice-3', 'lastcheckok': 1},
]
SHOWS = [{'collectionName': 'History Hour', 'feedUrl': 'https://feeds.example.com/history', 'primaryGenreName': 'History'},
         {'collectionName': 'Veterans Voices', 'feedUrl': 'https://feeds.example.com/veterans', 'primaryGenreName': 'Society'}]
EPISODES = ['The Battle of Midway', 'Building the Golden Gate Bridge', 'The First Moon Landing']


def practice_directory(url):
    """The station directory and podcast search, answered from the samples above."""
    from urllib.parse import parse_qs, urlsplit
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    if '/json/stations/search' in url:
        words = (query.get('name') or query.get('tag') or '').casefold()
        return [dict(s) for s in STATIONS if words in s['name'].casefold() or words in s['tags']]
    if 'term' in query:
        words = query['term'].casefold()
        return {'results': [dict(s) for s in SHOWS if any(w in s['collectionName'].casefold() for w in words.split())]}
    if url.endswith('.json'):
        return {'chapters': [{'startTime': 0, 'title': 'Opening'}, {'startTime': 300, 'title': 'The battle'},
                             {'startTime': 900, 'title': 'What came after'}]}
    raise OSError('Not in the practice directory.')


def practice_hub(app):
    """The real MediaHub, offline: sample directory, pretend player, nothing saved outside a temporary folder."""
    # A private copy of media_hub with no way to the internet: every address answers "no internet".
    class NoInternet:
        Request = staticmethod(lambda url, *a, **k: url)

        @staticmethod
        def urlopen(*args, **kwargs):
            raise OSError('Practice: no internet.')
    MediaHub = private('media_hub', request=NoInternet).MediaHub
    folder = Path(tempfile.mkdtemp(prefix='vc-tutorial-media-'))
    hub = MediaHub(folder, opener=lambda *a, **k: None, fetch_json=practice_directory, notify=lambda text: None,
                   clock=app.CLOCK, player=PracticeAudio())
    hub._radio_query = lambda query: practice_directory('https://practice/json/stations/search?' +
                                                        __import__('urllib.parse').parse.urlencode(query))
    hub._stations_file = lambda name: []
    hub._feed_episodes = lambda show: [{'title': title, 'url': show['feed'] + '/' + str(n) + '.mp3', 'show': show['name'],
                                        'feed': show['feed'], 'published': 0,
                                        'chapters_url': show['feed'] + '/chapters.json' if n == 0 else ''}
                                       for n, title in enumerate(EPISODES)]
    hub.start_podcast_refresh = lambda *a, **k: False
    hub.start_scheduler = lambda *a, **k: None

    def recorder(station, minutes, stop):
        stop.wait(0)     # nothing is recorded in practice
    hub._record_worker = recorder
    hub._download_worker = lambda *args, **kwargs: None     # nothing is downloaded in practice
    return hub


class MediaSim(Sim):
    """Radio or Podcasts, with the real menus and words (MediaNavigation and MediaHub)."""

    def __init__(self, app, section):
        from media_navigation import MediaNavigation
        self.hub = practice_hub(app)
        self.nav = MediaNavigation(self.hub, section)
        self.section = section
        self.title = 'Radio' if section == 'radio' else 'Podcasts'
        self.opening = self.nav.enter(section, keyboard=True)

    def menu(self):
        return self.nav.state()

    def feed(self, kind, value):
        try:
            if kind == 'key':
                key = canonical_key(value)
                if len(key) == 1 and key.isalpha():
                    key = 'Letter:' + key.lower()
                result = self.nav.keyboard(key)
            elif self.nav.form and self.nav.field_index < len(self.nav.form['fields']) and \
                    not self.nav.form['fields'][self.nav.field_index]['choices']:
                # Words for a box in a form, as the window sends a typed value (field_value).
                result = self.nav.command(value)
            else:
                result = self.nav.command(value)
        except (OSError, ValueError, IndexError) as error:
            from media_navigation import spoken_error
            result = 'I could not complete that media request. ' + spoken_error(error)
        if result == '__main__':
            self.chosen = 'media menu'
            return None
        return result or None

    def close(self):
        self.hub.record_stop.set()
        shutil.rmtree(self.hub.folder, ignore_errors=True)


# YouTube ------------------------------------------------------------------------------------
VIDEOS = [
    {'kind': 'video', 'id': 'practice1', 'title': 'How to make a cup of coffee', 'channel': 'Kitchen Basics',
     'duration': 245, 'views': '120K views', 'age': '2 years ago'},
    {'kind': 'video', 'id': 'practice2', 'title': 'Coffee brewing for beginners', 'channel': 'Brew Lab',
     'duration': 612, 'views': '45K views', 'age': '8 months ago'},
    {'kind': 'video', 'id': 'practice3', 'title': 'The history of coffee', 'channel': 'Story Time',
     'duration': 1320, 'views': '980K views', 'age': '5 years ago'},
]


class PracticeVideo:
    """The YouTube player page, as youtube_page.YouTubePage answers, playing nothing."""

    def __init__(self):
        self.paused, self.time, self.duration, self.volume, self.muted = True, 0, 245, 100, False
        self.captions = {'available': True, 'on': False}
        self.title = ''

    def state(self):
        return {'paused': self.paused, 'time': self.time, 'duration': self.duration, 'volume': self.volume,
                'muted': self.muted, 'captions': dict(self.captions), 'ad': {}, 'title': self.title}

    def play(self):
        self.paused = False
        return True

    def pause(self):
        self.paused = True

    def seek(self, seconds):
        self.time = max(0, min(self.duration, int(seconds)))
        return self.state()

    def set_volume(self, value):
        self.volume = max(0, min(100, int(value)))
        return self.volume

    def set_muted(self, wanted):
        self.muted = bool(wanted)
        return self.muted

    def toggle_captions(self):
        self.captions['on'] = not self.captions['on']
        return dict(self.captions)

    def read_list(self):
        return [dict(v) for v in VIDEOS], {}

    def read_filters(self):
        return []

    def signed_in(self):
        return False


class PracticePage:
    def is_closed(self):
        return False


class YouTubeSim(Sim):
    """YouTube with the real YouTubeScreen: its menu, search, lists, player and words. No browser opens."""
    title = 'YouTube'

    def __init__(self, app):
        self.box = practice_box(app)
        self.module = private('youtube_screen')
        box = self.box
        box.MEDIA_HUB = None
        box.PREFERENCES = {}
        box.menu_state = lambda mode: self.module.menu_state(box)
        screen = self.module.YouTubeScreen(box)
        self.module.SCREEN = screen
        box.YOUTUBE = screen
        video = PracticeVideo()
        screen.lists = screen.player = video
        screen.go = lambda url: ''

        def open_video_page(url):
            screen.video_page = PracticePage()
            item = next((v for v in VIDEOS if v['id'] in url), VIDEOS[0])
            video.title, video.duration, video.time, video.paused = item['title'], item['duration'], 0, True
        screen.open_video_page = open_video_page
        screen.check_signed_in = lambda: None
        self.screen, self.video = screen, video
        box.handle = self.dispatch
        self.opening = screen.show_menu('YouTube. ')

    def dispatch(self, command, mode, typed=False):
        self.chosen = command
        return 'youtube'

    def menu(self):
        try:
            return self.module.menu_state(self.box)
        except Exception:
            return None

    def feed(self, kind, value):
        module, box = self.module, self.box
        if kind == 'key':
            key = canonical_key(value)
            if len(key) == 1 and key.isalpha():
                view = self.screen.view()
                # In a list, a letter moves to a name; elsewhere, a letter is a video key.
                if view and view['kind'] in module.MENU_KINDS and not self.screen.pending:
                    key = 'Letter:' + key.lower()
            if key.startswith('Letter:'):
                box.choose_menu_letter = lambda letter, mode: box.speak(self.letter(letter))
            request = module.navigation_key(box, key)
            if request is None:
                return box.take() or None
            value, typed = request, True
        else:
            typed = False
        try:
            result = module.handle(box, value, 'youtube', typed)
        except module.YouTubeError as error:
            box.speak(str(error))
            result = 'youtube'
        if result not in (None, 'youtube'):
            self.chosen = result
        return box.take() or None

    def letter(self, letter):
        from menu_navigation import announce_item, next_match
        names, index, select = self.module.menu_state(self.box)
        found = next_match(names, index, letter)
        if found is None:
            return 'No menu item starts with ' + letter.upper() + '.'
        select(found)
        return announce_item(names[found], found, len(names))

    def close(self):
        shutil.rmtree(self.box.APP, ignore_errors=True)


# File manager -------------------------------------------------------------------------------
class PracticeFiles:
    """Files that exist only in memory, answering as file_manager.ShellFiles does."""
    ROOT = 'P:\\'

    def __init__(self):
        from file_manager import Item
        self.Item = Item
        self.tree = {self.ROOT: ['Documents', 'Music', 'Letter to Sam.docx', 'Shopping list.txt'],
                     self.ROOT + 'Documents': ['Budget.xlsx', 'Recipes'], self.ROOT + 'Documents\\Recipes': [],
                     self.ROOT + 'Music': ['Song.mp3']}
        self.clip = ([], False)
        self.actions = []

    def folder(self, path):
        return path in self.tree

    def item(self, path):
        name = PureWindowsPath(path).name
        return self.Item(name, path, self.folder(path), False, True, 0.0, 0.0, size=None if self.folder(path) else 2048)

    def roots(self):
        return [self.Item('Practice drive (P:)', self.ROOT, True, True)]

    def list(self, path):
        names = self.tree.get(path)
        if names is None:
            raise OSError(path + ' is no longer there.')
        items = [self.item(str(PureWindowsPath(path) / name)) for name in names]
        return sorted(items, key=lambda i: (not i.folder, i.name.casefold()))

    def parent(self, path):
        parent = str(PureWindowsPath(path).parent)
        return None if path == self.ROOT else parent

    def extended(self, path):
        return {}

    def clipboard(self, paths, cut):
        self.clip = (list(paths), cut)

    def get_clipboard(self):
        return self.clip

    def finish_cut(self, paths):
        self.clip = ([], False)

    def operate(self, action, paths, destination=None, name=None):
        self.actions.append(action)
        for path in paths:
            parent = str(PureWindowsPath(path).parent)
            base = PureWindowsPath(path).name
            if action in ('delete', 'move') and base in self.tree.get(parent, []):
                self.tree[parent].remove(base)
            if action == 'rename' and base in self.tree.get(parent, []):
                self.tree[parent][self.tree[parent].index(base)] = name
            if action in ('copy', 'move') and destination in self.tree:
                taken = self.tree[destination]
                new = base
                while new in taken:
                    new = PureWindowsPath(new).stem + ' - Copy' + PureWindowsPath(new).suffix
                taken.append(new)


class FileSim(Sim):
    """File manager, run by the real FileManager on practice files in memory."""
    title = 'File manager'

    def __init__(self, app):
        from file_manager import FileManager
        self.files = PracticeFiles()
        self.manager = FileManager(self.files)
        self.manager.refresh(PracticeFiles.ROOT)
        self.opening = 'File manager. ' + self.settle('')

    def settle(self, said):
        import time
        notices = [said] if said and not self.manager.busy else []
        until = time.monotonic() + 5
        while self.manager.busy and time.monotonic() < until:
            result = self.manager.poll()
            if result:
                notices.append(result)
            time.sleep(.002)
        return ' '.join(n for n in notices if n)

    def menu(self):
        labels = self.manager.labels()
        index = self.manager.menu_index if self.manager.menu else self.manager.index
        return (labels, index, lambda i: None) if labels else None

    def feed(self, kind, value):
        manager = self.manager
        if kind == 'key':
            key = canonical_key(value)
            command = FILE_KEYS.get(key)
            if command is None and len(key) == 1 and key.isalnum():
                command = 'file letter ' + key.lower()
            if command is None:
                return None
            if manager.pending and manager.pending[0] == 'delete':
                # The delete question: Y, N and Escape, as companion.navigation_key answers it.
                command = {'Y': 'yes', 'N': 'no', 'Escape': 'no'}.get(key)
                if command is None:
                    return None
        else:
            command = value
        if command.startswith('file letter '):
            command = 'file letters ' + command[len('file letter '):]     # as companion._handle passes them
        try:
            result = manager.command(command, typed=kind == 'key')
        except (ValueError, OSError) as error:
            result = str(error)
        if result == '__main__':
            self.chosen = 'main menu'
            return None
        if result in ('email this file', 'attach to draft'):
            self.chosen = result
            return None
        if manager.location is not None and not manager.location.startswith(PracticeFiles.ROOT):
            manager.refresh(PracticeFiles.ROOT)      # never outside the practice drive
        return self.settle(result) or result or None


def file_keys():
    """File manager's keys, as companion.navigation_key maps them for File manager."""
    from file_manager import GROUPS
    keys = {key: command for _, items in GROUPS.values() for _, key, command in items}
    keys.update({'Up': 'previous', 'Down': 'next', 'Left': 'previous', 'Right': 'next', 'Home': 'home', 'End': 'end',
                 'Enter': 'enter', 'Space': 'toggle tag', 'Escape': 'escape', 'Alt': 'file manager menu'})
    keys.pop('Double:F1', None)
    return keys


FILE_KEYS = file_keys()


# Document reader ----------------------------------------------------------------------------
SAMPLE_DOCUMENT = '''<html><body>
<h1>Welcome to the practice document</h1>
<p>This short document has a heading, a table, a link, a list, a bookmark and a footnote.</p>
<h2>Bus times</h2>
<table><tr><th>Stop</th><th>Time</th></tr><tr><td>Main Street</td><td>8 AM</td></tr></table>
<p>See the <a href="#notes">notes at the end</a>.</p>
<h2>Things to bring</h2>
<ul><li>ID card</li><li>Water</li></ul>
<p id="notes">Notes. The bus is free for veterans.<sup><a href="#fn1" class="footnote-ref">1</a></sup></p>
<p class="footnote" id="fn1">1. Show your VA card.</p>
</body></html>'''


class ReaderSim(Sim):
    """Document reader with a sample document, read by the real reader (document_reader)."""
    title = 'Document reader'

    def __init__(self, app):
        import document_reader
        self.app = app
        self.folder = Path(tempfile.mkdtemp(prefix='vc-tutorial-reader-'))
        path = self.folder / 'Practice document.html'
        path.write_text(SAMPLE_DOCUMENT, encoding='utf-8')
        self.reader = document_reader.open_document(path)
        from file_manager import FileManager
        self.opening = FileManager(PracticeFiles()).finish_open(self.reader)   # as File manager opens it

    def feed(self, kind, value):
        import document_reader
        if kind == 'key':
            command = document_reader.READER_KEYS.get(canonical_key(value)) or READING_KEYS.get(canonical_key(value))
            if command is None:
                return None
            value = command
        return document_reader.reader_command(self.reader, value, self.app.normalized_command(value))

    def close(self):
        shutil.rmtree(self.folder, ignore_errors=True)


# The arrows in a document read as in every text (the window reads them; these are the same moves).
READING_KEYS = {'Down': 'next line', 'Up': 'previous line', 'Ctrl+Right': 'next word', 'Ctrl+Left': 'previous word',
                'Ctrl+Down': 'next paragraph', 'Ctrl+Up': 'previous paragraph'}


# Notepad ------------------------------------------------------------------------------------
class NoteSim(Sim):
    """A note in Notepad. Words are added as the app adds them; Save note uses the real notepad in a
    temporary folder."""
    title = 'Note'

    def __init__(self, app):
        from reading_navigation import ReadingCursor
        self.app = app
        self.words = []
        self.reading = ReadingCursor()
        self.folder = Path(tempfile.mkdtemp(prefix='vc-tutorial-note-'))
        self.saved = False

    def feed(self, kind, value):
        from input_parity import screen_command
        from reading_navigation import edge_notice, reading_request
        import notepad
        app = self.app
        if kind == 'key':
            value = screen_command(canonical_key(value), 'note')
            if not value:
                return None
        command = app.normalized_command(value)
        request = reading_request(command)
        if request:
            self.reading.set_text(' '.join(self.words))
            unit, direction = request
            result = self.reading.read(direction) if unit == 'read' else self.reading.move(unit, direction)
            return result if unit == 'read' else edge_notice(self.reading, 'note') + result
        if command in ('save note', 'finish note', 'done dictating'):
            if not self.words:
                return 'The note was empty.'
            notepad.add(self.folder, ' '.join(self.words))
            self.words = []
            self.saved = True
            self.chosen = 'save note'
            return app.NOTE_SAVED
        if command in ('list notes', 'open a note', 'open notes'):
            notes = notepad.newest_first(notepad.read_notes(self.folder))
            if not notes:
                return 'You have no saved notes yet. Say Write a note to start one.'
            self.chosen = 'list notes'
            return 'Notes. ' + notepad.label(notes[0])
        self.words.append(' '.join(str(value).split()))
        return self.words[-1]

    def close(self):
        shutil.rmtree(self.folder, ignore_errors=True)


# Set up Chrome -----------------------------------------------------------------------------
class PracticeChrome:
    """Windows and Chrome, as chrome_setup.WindowsChrome answers: Chrome is installed and the
    extension is not added yet. Nothing is installed, added or opened."""

    def __init__(self):
        self.extension = 'missing'
        self.opened = []

    def supported(self):
        return True

    def find_chrome(self):
        return 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

    def extension_state(self):
        return self.extension

    def add_extension(self):
        self.extension = 'added'

    def remove_extension(self):
        self.extension = 'missing'

    def install_chrome(self):
        return True

    def open_chrome(self, address):
        self.opened.append(address)
        return True


class ChromeSim(Sim):
    """Set up Chrome, run by the real ChromeSetup conversation on a practice computer."""
    title = 'Chrome setup'

    def __init__(self, app):
        self.app = app
        self.setup = None

    def feed(self, kind, value):
        import chrome_setup
        if kind == 'key':
            value = {'Y': 'yes', 'N': 'no', 'Escape': 'cancel'}.get(canonical_key(value))
            if value is None:
                return None
        command = self.app.normalized_command(value)
        if self.setup is None or self.setup.finished:
            if command not in ('set up chrome', 'setup chrome', 'chrome setup'):
                return None
            self.setup = chrome_setup.ChromeSetup(PracticeChrome(), lambda: False)
            return self.setup.start()
        return self.setup.respond(command)

    def close(self):
        if self.setup is not None:
            self.setup.close()


# Options, Favorite apps --------------------------------------------------------------------
class FavoritesSim(Sim):
    """The Favorite apps list in Options, run by the real FavoriteList. Nothing is saved."""
    title = 'Favorite apps'

    def __init__(self):
        from favorite_list import FavoriteList
        from settings_model import SettingsSession
        # A staged Options session, as the dialog has: OK would save it, and here nothing ever does.
        self.list = FavoriteList(SettingsSession({}, {}))

    def menu(self):
        return [self.list.line(i) for i in range(len(self.list))], self.list.index, lambda i: None

    def feed(self, kind, value):
        if kind == 'key':
            key = canonical_key(value)
            control = key.startswith('Ctrl+')
            return self.list.keyboard(key[len('Ctrl+'):] if control else key, control=control)
        return self.list.voice(value)
