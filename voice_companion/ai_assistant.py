"""AI assistant: Reading Assistant, Writing Assistant, Describe Image and Ask a Question.

Will, November 16, 2026: give Voice Companion the AI help GuideConnect has, built into
every screen it fits, with the same keys, menu items and voice commands everywhere.
Control+Shift+Q (or "AI assistant") opens it from what you are reading or writing.

- Reading Assistant: Summarise and Simplify, for an email, a document, a web page or a file.
- Writing Assistant: Check for errors, then keep or skip each correction; and Rewrite
  friendlier, more professional, clearer or shorter, then keep it or keep your own.
- Describe Image: a picture, with any writing in it, and questions about it.
- Ask a Question: about Voice Companion, answered from its own guide.

The work is done by Voice Companion's AI service (tools/ai-service), which holds the
OpenAI key, so people need no account of their own. Every request runs on its own
thread: the app never waits for the internet (the November 14 freeze lesson).
"""
import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVICE = 'https://ai.voicecompanionapp.com/v1/assist'
TIMEOUT_SECONDS = 60
STILL_WORKING_SECONDS = 8
IMAGE_LIMIT = 6 * 1024 * 1024
IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}

# What each kind of place offers, in order. Names are said, shown and spoken as commands.
CHECK = 'Check for errors'
FRIENDLIER = 'Friendlier'
PROFESSIONAL = 'More professional'
CLEARER = 'Clearer'
SHORTER = 'Shorter'
SUMMARISE = 'Summarise'
SIMPLIFY = 'Simplify'
DESCRIBE = 'Describe the image'
ASK_IMAGE = 'Ask about the image'
ASK_HELP = 'Ask a question'
CHOICES = {
    'write': (CHECK, FRIENDLIER, PROFESSIONAL, CLEARER, SHORTER, SUMMARISE, SIMPLIFY),
    'read': (SUMMARISE, SIMPLIFY),
    'image': (DESCRIBE, ASK_IMAGE),
    'help': (ASK_HELP,),
}
KEEP_FIRST = 'Done. Press Enter to use it in place of your text, or Escape to keep your own. Here it is. '
TONES = {FRIENDLIER: 'friendlier', PROFESSIONAL: 'professional', CLEARER: 'clearer', SHORTER: 'shorter'}

# Spoken words for each choice. Recognizers add capitals and periods; normalized() removes them.
SPOKEN = {
    CHECK: ('check for errors', 'check for mistakes', 'check spelling', 'check spelling and grammar', 'check my writing',
            'proofread', 'proofread this', 'check this'),
    FRIENDLIER: ('make it friendlier', 'make this friendlier', 'make it friendly', 'make it warmer', 'friendlier'),
    PROFESSIONAL: ('make it more professional', 'make this more professional', 'make it professional', 'more professional'),
    CLEARER: ('make it clearer', 'make this clearer', 'make it clear', 'clearer'),
    SHORTER: ('make it shorter', 'make this shorter', 'make it more concise', 'shorten it', 'shorter'),
    SUMMARISE: ('summarise', 'summarize', 'summarise this', 'summarize this', 'summarise it', 'summarize it',
                'summary', 'give me a summary', 'summarise this email', 'summarize this email',
                'summarise this page', 'summarize this page', 'summarise this document', 'summarize this document'),
    SIMPLIFY: ('simplify', 'simplify this', 'simplify it', 'make it simpler', 'make it easier to read', 'simplify this email',
               'simplify this page', 'simplify this document', 'in plain language', 'plain language'),
    DESCRIBE: ('describe the image', 'describe image', 'describe this image', 'describe the picture', 'describe this picture',
               'describe picture', 'what is in this picture', 'what is in the picture', 'what is in this image', 'describe it'),
    ASK_IMAGE: ('ask about the image', 'ask about this image', 'ask about the picture', 'ask about this picture'),
    ASK_HELP: ('ask a question', 'ask help a question', 'ask the guide'),
}
OPEN_WORDS = ('ai assistant', 'open ai assistant', 'open the ai assistant', 'reading assistant', 'writing assistant',
              'open reading assistant', 'open writing assistant', 'ai help')
# While you dictate, writing comes first: only these whole commands (the menu items) count.
# "Check this." or "Describe it." in a letter stays text.
WRITING_COMMANDS = OPEN_WORDS + ('check for errors', 'check for mistakes', 'check spelling and grammar',
                                 'make it friendlier', 'make it more professional', 'make it clearer', 'make it shorter',
                                 'summarise this document', 'summarize this document', 'simplify this document',
                                 'summarise this email', 'summarize this email', 'simplify this email',
                                 'summarise this note', 'summarize this note', 'simplify this note')

NOT_ON = 'AI features are turned off. To turn them on, open Options and choose AI assistant.'
# Honest about where the text goes (OpenAI's API keeps requests for a short time for abuse checks).
CONSENT = ('The AI assistant sends this text to Voice Companion\'s AI service, which uses OpenAI to do the work. '
           'Voice Companion does not keep it, and OpenAI does not use it to train its AI. '
           'Use the AI assistant? Say yes or no, or press Y or N.')
NO_TEXT = 'There is no text here for the AI assistant. Write or open something first.'
WORKING = 'Working on it. Press Escape to stop.'
STILL = 'Still working.'
STOPPED = 'Stopped. Nothing was changed.'


def normalized(text):
    text = re.sub(r"[^a-z0-9' ]+", ' ', str(text or '').lower().replace('&', ' and '))
    return re.sub(r'\s+', ' ', text).strip()


def spoken_choice(text, kind=None):
    """The choice these words name, or None. kind limits it to what that place offers."""
    said = normalized(text)
    for choice, words in SPOKEN.items():
        if kind and choice not in CHOICES[kind]:
            continue
        if said in words or said == normalized(choice):
            return choice
    return None


def writing_command(text):
    """True when dictated words are a whole AI command, not text to write."""
    return normalized(text) in WRITING_COMMANDS


def opens_assistant(text):
    return normalized(text) in OPEN_WORDS


class AssistantError(Exception):
    """A problem said to the person as it is: what happened and what to do."""


def install_id(folder):
    """A random id for this installed copy, so the service can keep its monthly limit."""
    path = Path(folder) / 'ai-install.txt'
    try:
        value = path.read_text(encoding='ascii').strip()
        if re.fullmatch(r'[0-9a-f]{32}', value):
            return value
    except (OSError, UnicodeError):
        pass
    value = os.urandom(16).hex()
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(value, encoding='ascii')
        os.replace(temporary, path)
    except OSError:
        pass
    return value


LOG_FOLDER = [None]   # where ai-error.txt goes: the settings folder of the last request


def service_request(folder, version, task, payload, timeout=TIMEOUT_SECONDS, opener=urllib.request.urlopen):
    """Ask the AI service. Returns its answer, or raises AssistantError with words to say."""
    LOG_FOLDER[0] = folder
    body = json.dumps(dict(payload, task=task)).encode('utf-8')
    # The request names itself. Python's own name ("Python-urllib") is turned away by Cloudflare
    # with "error code: 1010" before the service sees it (Will, November 18, 2026: writing help
    # always failed). The updater has always named itself.
    request = urllib.request.Request(os.getenv('VOICE_COMPANION_AI_URL', SERVICE), data=body, method='POST', headers={
        'content-type': 'application/json', 'User-Agent': 'VoiceCompanion/%s' % version,
        'X-Companion-Install': install_id(folder), 'X-Companion-Version': str(version)})
    try:
        with opener(request, timeout=timeout) as reply:
            answer = json.loads(reply.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        try:
            raw = error.read()
        except Exception:
            raw = b''
        try:
            answer = json.loads(raw.decode('utf-8'))
        except Exception:
            answer = {'ok': False, 'error': 'status %s' % error.code, 'detail': raw[:200].decode('utf-8', 'replace').strip()}
    except (urllib.error.URLError, OSError, TimeoutError):
        raise AssistantError('Voice Companion could not reach the AI assistant. Check your internet connection, then try again.')
    except ValueError:
        raise AssistantError('The AI assistant sent an answer Voice Companion could not read. Please try again.')
    if answer.get('ok'):
        return answer
    error = str(answer.get('error', ''))
    if error == 'monthly limit':
        raise AssistantError('You have used all %s AI requests for this month. They start again on the first of next month.'
                             % answer.get('limit', 200))
    if error == 'image limit':
        raise AssistantError('You have used all %s picture descriptions for this month. They start again on the first of next month. '
                             'Reading and writing help still works.' % answer.get('limit', 200))
    if error == 'unavailable':
        raise AssistantError('The AI assistant is not available right now. Please try again later.')
    if error == 'busy':
        raise AssistantError('The AI assistant is very busy today. Please try again tomorrow.')
    if error == 'text too long':
        raise AssistantError('This is too long for the AI assistant. Select a smaller part, then try again.')
    if error == 'image too large':
        raise AssistantError('This picture is too large for the AI assistant.')
    record_problem(folder, task, error, answer.get('detail'))
    raise AssistantError('The AI assistant could not do that just now. Please try again in a moment.')


def record_problem(folder, task, error, detail=None):
    """Every failure names itself: what went wrong goes in ai-error.txt in the settings folder,
    never the person's text, so a helper (or Claude) can see why without asking."""
    try:
        from datetime import datetime
        line = '%s %s: %s%s\n' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), task, error or 'no reason given',
                                    ' (%s)' % str(detail)[:300].replace('\n', ' ').strip() if detail else '')
        path = Path(folder) / 'ai-error.txt'
        old = path.read_text(encoding='utf-8').splitlines(True)[-49:] if path.exists() else []
        path.write_text(''.join(old) + line, encoding='utf-8')
    except Exception:
        pass


def pictures_left_words(answer):
    """Pictures have a monthly limit (reading and writing do not): say how many are left once it is 10 or fewer."""
    left = answer.get('pictures_left')
    if not isinstance(left, int) or left > 10:
        return ''
    if left == 0:
        return ' That was your last picture description this month. They start again on the first of next month.'
    return ' You have %d picture %s left this month.' % (left, 'description' if left == 1 else 'descriptions')


def image_payload(path):
    """A picture file as the service takes it, or raises AssistantError."""
    path = Path(path)
    kind = IMAGE_TYPES.get(path.suffix.lower())
    if kind is None:
        raise AssistantError('That is not a picture the AI assistant can describe. It can describe PNG, JPEG, GIF and WebP pictures.')
    try:
        data = path.read_bytes()
    except OSError:
        raise AssistantError('Voice Companion could not open that picture.')
    if len(data) > IMAGE_LIMIT:
        raise AssistantError('This picture is too large for the AI assistant.')
    return 'data:%s;base64,%s' % (kind, base64.b64encode(data).decode('ascii'))


def image_data(name, data):
    """Picture bytes already read (an email attachment) as the service takes them."""
    kind = IMAGE_TYPES.get(Path(str(name or '')).suffix.lower())
    if kind is None:
        raise AssistantError('That is not a picture the AI assistant can describe. It can describe PNG, JPEG, GIF and WebP pictures.')
    if len(data) > IMAGE_LIMIT:
        raise AssistantError('This picture is too large for the AI assistant.')
    return 'data:%s;base64,%s' % (kind, base64.b64encode(data).decode('ascii'))


def is_image(name):
    return Path(str(name or '')).suffix.lower() in IMAGE_TYPES


class Job:
    """One request on its own thread. The main loop collects the answer with poll()."""

    def __init__(self, work, clock=time.monotonic):
        self.clock = clock
        self.started = self.told = clock()
        self.result = self.error = None
        self.cancelled = False
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(work,), name='AI assistant', daemon=True)
        self.thread.start()

    def _run(self, work):
        try:
            self.result = work()
        except AssistantError as problem:
            self.error = str(problem)
        except Exception as problem:
            self.error = 'The AI assistant could not do that just now. Please try again in a moment.'
            if LOG_FOLDER[0]:
                record_problem(LOG_FOLDER[0], 'request', type(problem).__name__, str(problem)[:200])
        finally:
            self.done.set()


class Session:
    """The AI assistant screen: a menu of what fits the place you came from, then the answer.

    source: {kind: write | read | image | help, label: 'the selected text', text, title,
             apply(new_text) -> words to say, image_path, guide(question) -> guide text}.
    request(task, payload) -> the service's answer (raises AssistantError).
    """

    def __init__(self, source, return_mode, request, clock=time.monotonic):
        self.source = source
        self.return_mode = return_mode
        self.request = request
        self.clock = clock
        self.kind = source['kind']
        self.choices = list(CHOICES[self.kind])
        self.index = 0
        self.level = 'menu'            # menu, question, working, result, corrections
        self.choice = None
        self.job = None
        self.result = ''
        self.corrections = []
        self.correction_index = 0
        self.kept = 0
        self.asking = None             # the choice waiting for a typed or spoken question

    # ----- what is said -----
    def opening(self):
        where = self.source.get('label') or 'this'
        return 'AI assistant, for %s. %s' % (where, self.item_words())

    def item_words(self):
        return '%s, %d of %d.' % (self.choices[self.index], self.index + 1, len(self.choices))

    def correction_words(self):
        if not self.corrections:
            return 'No more corrections.'
        c = self.corrections[self.correction_index]
        reason = (' ' + c['reason'].strip().rstrip('.') + '.') if c.get('reason') else ''
        return 'Change "%s" to "%s".%s %d of %d.' % (c['original'], c['replacement'], reason,
                                                    self.correction_index + 1, len(self.corrections))

    # ----- moving -----
    def move(self, step=None, to=None):
        if self.level == 'corrections':
            count = len(self.corrections)
            if not count:
                return 'No more corrections.'
            if to == 'first':
                self.correction_index = 0
            elif to == 'last':
                self.correction_index = count - 1
            else:
                self.correction_index = max(0, min(count - 1, self.correction_index + step))
            return self.correction_words()
        if self.level != 'menu':
            return None
        if to == 'first':
            self.index = 0
        elif to == 'last':
            self.index = len(self.choices) - 1
        else:
            self.index = max(0, min(len(self.choices) - 1, self.index + step))
        return self.item_words()

    def letter(self, letter):
        if self.level != 'menu':
            return None
        letter = letter.lower()
        order = list(range(self.index + 1, len(self.choices))) + list(range(0, self.index + 1))
        for i in order:
            if self.choices[i].lower().startswith(letter):
                self.index = i
                return self.item_words()
        return 'No choice starts with %s.' % letter.upper()

    # ----- doing -----
    def choose(self, choice=None):
        """Run a choice (the current one when None). Returns words to say."""
        choice = choice or self.choices[self.index]
        if choice not in self.choices:
            return 'That is not offered here. ' + self.item_words()
        self.index = self.choices.index(choice)
        self.choice = choice
        if choice in (ASK_IMAGE, ASK_HELP):
            self.level, self.asking = 'question', choice
            return ('Type or say your question about the image, then press Enter.' if choice == ASK_IMAGE
                    else 'Type or say your question about Voice Companion, then press Enter.')
        return self._start(choice)

    def ask(self, question):
        """The question for Ask about the image or Ask a question."""
        question = str(question or '').strip()
        if not question:
            return 'Type or say your question, then press Enter.'
        choice, self.asking = self.asking or self.choice, None
        return self._start(choice, question)

    def _start(self, choice, question=None):
        source = self.source
        text = source.get('text') or ''
        if choice in (DESCRIBE, ASK_IMAGE):
            path, ready = source.get('image_path'), source.get('image_data')
            def work():
                payload = {'image': ready or image_payload(path)}
                if question:
                    payload['question'] = question
                return self.request('describe_image', payload)
        elif choice == ASK_HELP:
            guide = source['guide'](question)
            def work():
                return self.request('help_question', {'question': question, 'guide': guide})
        else:
            if not text.strip():
                self.level = 'menu'
                return NO_TEXT
            if choice == CHECK:
                work = lambda: self.request('check_errors', {'text': text})
            elif choice in TONES:
                work = lambda: self.request('rewrite', {'text': text, 'tone': TONES[choice]})
            else:
                work = lambda: self.request('summarise' if choice == SUMMARISE else 'simplify', {'text': text})
        self.level = 'working'
        self.job = Job(work, self.clock)
        return WORKING

    def stop(self):
        if self.job is not None:
            self.job.cancelled = True
            self.job = None
        self.level = 'menu'
        return STOPPED

    def poll(self):
        """Words to say when the answer arrives (or that it is still coming); None otherwise."""
        job = self.job
        if job is None or self.level != 'working':
            return None
        if not job.done.is_set():
            if self.clock() - job.told >= STILL_WORKING_SECONDS:
                job.told = self.clock()
                return STILL
            return None
        self.job = None
        if job.cancelled:
            return None
        if job.error:
            self.level = 'menu'
            return job.error
        answer = job.result or {}
        if self.choice == CHECK:
            text = self.source.get('text') or ''
            self.corrections = [c for c in answer.get('corrections') or []
                                if isinstance(c, dict) and c.get('original') and c.get('original') in text
                                and c.get('replacement') is not None and c['original'] != c['replacement']]
            self.correction_index, self.kept = 0, 0
            if not self.corrections:
                self.level = 'menu'
                return 'No mistakes found. ' + self.item_words()
            self.level = 'corrections'
            count = len(self.corrections)
            return ('Found %d %s. Press Enter to keep a correction, Delete to skip it, or Control+Enter to keep them all. '
                    % (count, 'correction' if count == 1 else 'corrections')) + self.correction_words()
        self.result = (answer.get('text') or '').strip()
        if not self.result:
            self.level = 'menu'
            return 'The AI assistant sent back nothing. Please try again.'
        self.level = 'result'
        # What to do comes first, before the answer is read (Will, November 18, 2026: "a better
        # prompt ... that says done, press Enter to keep, before what it generated is read back").
        if self.keepable():
            return KEEP_FIRST + self.result
        return 'Done. Here it is. ' + self.result + pictures_left_words(answer)

    def keepable(self):
        """A rewrite, or simplified writing, can go in place of the text it came from."""
        return bool(self.source.get('apply')) and (self.choice in TONES or (self.choice == SIMPLIFY and self.source.get('kind') == 'write'))

    # ----- keeping changes -----
    def keep_result(self):
        """Enter on a rewrite: put it in place of your text."""
        if self.level != 'result' or not self.keepable():
            return None
        said = self.source['apply'](self.result)
        self.level = 'menu'
        return said or 'Done. Say undo to put your own text back.'

    def keep_correction(self):
        if self.level != 'corrections' or not self.corrections:
            return None
        c = self.corrections.pop(self.correction_index)
        said = self.source['fix'](c['original'], c['replacement'])
        if said is False:
            return 'That text has changed, so the correction was skipped. ' + self._after_correction()
        self.kept += 1
        return 'Kept. ' + self._after_correction()

    def skip_correction(self):
        if self.level != 'corrections' or not self.corrections:
            return None
        self.corrections.pop(self.correction_index)
        return 'Skipped. ' + self._after_correction()

    def keep_all(self):
        if self.level != 'corrections' or not self.corrections:
            return None
        changed = 0
        while self.corrections:
            c = self.corrections.pop(0)
            if self.source['fix'](c['original'], c['replacement']) is not False:
                changed += 1
        self.kept += changed
        self.level = 'menu'
        return 'Kept %d %s. Say undo to take them back one at a time.' % (changed, 'correction' if changed == 1 else 'corrections')

    def _after_correction(self):
        if not self.corrections:
            self.level = 'menu'
            kept = self.kept
            return ('Done. You kept %d. ' % kept if kept else 'Done. ') + self.item_words()
        self.correction_index = min(self.correction_index, len(self.corrections) - 1)
        return self.correction_words()

    def back(self):
        """Escape: from an answer to the menu; from the menu, None (leave the assistant)."""
        if self.level == 'working':
            return self.stop()
        if self.level in ('result', 'corrections', 'question'):
            kept_own = self.level == 'result' and self.choice in TONES
            self.level, self.asking = 'menu', None
            return ('Kept your own text. ' if kept_own else '') + self.item_words()
        return None


def guide_sections(guide_text, question, limit=12000):
    """The parts of the user guide that best match a question, for Ask a Question.
    Sections start at a numbered heading line such as "25.4 Audio ducking"."""
    sections, current = [], []
    for line in str(guide_text or '').splitlines():
        if re.match(r'^\d+(\.\d+)*\s+\S', line) and current:
            sections.append('\n'.join(current)); current = []
        current.append(line)
    if current:
        sections.append('\n'.join(current))
    stop = {'the', 'a', 'an', 'to', 'how', 'do', 'i', 'is', 'in', 'of', 'and', 'or', 'can', 'what', 'my', 'on', 'for',
            'it', 'with', 'you', 'does', 'where', 'when', 'why', 'which', 'me', 'be', 'from', 'at', 'this', 'that'}
    words = [w for w in normalized(question).split() if w not in stop and len(w) > 1]
    if not words:
        return sections[0][:limit] if sections else ''
    def score(section):
        low = section.lower()
        head = low.split('\n', 1)[0]
        return sum(low.count(w) + 5 * head.count(w) for w in words)
    ranked = sorted((s for s in sections if score(s)), key=score, reverse=True)
    chosen, size = [], 0
    for section in ranked:
        if size + len(section) > limit:
            continue
        chosen.append(section); size += len(section)
    return '\n\n'.join(chosen)
