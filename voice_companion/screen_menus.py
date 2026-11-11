"""Alt menus for the main screens: Email, email drafts, Notepad, the web page,
Help, lessons and Document reader.

Each menu works like a Windows menu (Will, November 10, 2026): Alt opens it, a
group's letter opens the group, and an item's letter runs the item. Arrows move,
Enter chooses, Escape goes back one level, and Alt closes it. Numbers do nothing.
Every item runs the same spoken command as its voice command or shortcut key, so
the result is the same whichever way it is given.

The Word processor, File manager and Media player keep their own Alt menus
(task_navigation.py and file_manager.py). Radio and Podcasts use their actions
list as the menu, the main menu is already a menu, and on the Web browser menu
Alt says where you are.
"""
from hints import hint
from menu_navigation import announce_item, spoken_key

# (label, key, command). The key is the shortcut that does the same thing, or ''
# when there is none. Each item's letter is in LETTERS, below.
# A command with {value} asks for the value first. @options:<category> opens
# that page of Options.
MENUS = {
    # Grouped as people expect from Outlook and Thunderbird (Will, November 10, 2026): what you do
    # with a message, its header, its attachments, its read and flag marks, then places and views.
    'mailbox': ('Email menu', [
        ('Message', [
            ('New email', 'N', 'new email'),
            ('Open message', 'Enter', 'open current message'),
            ('Reply', 'R', 'reply'),
            ('Reply all', 'A', 'reply all'),
            ('Forward', 'F', 'forward'),
            ('Email the sender', 'E', 'new email to sender'),
            ('Move to folder', 'M', 'move'),
            ('Delete', 'Delete', 'delete'),
            ('Message details', 'I', 'message details')]),
        ('Header', [
            ('From', 'Alt+1', 'who is it from'),
            ('To', 'Alt+2', 'who is it to'),
            ('CC', 'Alt+3', 'read the cc'),
            ('Subject', 'Alt+4', 'what is the subject'),
            ('Date sent', 'Alt+5', 'when was it sent'),
            ('Copy sender address', 'C', 'copy sender address')]),
        ('Attachments', [
            ('List attachments', 'L', 'list attachments'),
            ('Open attachment', '', 'open attachment'),
            ('Save all attachments', '', 'save all attachments'),
            ('Attachment sizes', '', 'how big are the attachments')]),
        ('Unread and flags', [
            ('Mark as read or unread', 'Q', 'mark as read or unread'),
            ('Flag or unflag', 'X', 'flag or unflag'),
            ('Important or not important (Gmail)', 'H', 'mark important or not important'),
            ('Message status', '', 'message status')]),
        ('Select', [
            ('Select or unselect message', 'Space', 'toggle message selection'),
            ('Select all messages', 'Ctrl+A', 'select all messages'),
            ('Clear selection', 'U', 'clear selection'),
            ('What is selected', 'S', 'what is selected')]),
        ('Go to', [
            ('Inbox', '', 'go to inbox'),
            ('Sent', '', 'go to sent'),
            ('Drafts', '', 'go to drafts'),
            ('Trash', '', 'go to trash'),
            ('Spam', '', 'go to spam'),
            ('Choose a folder', 'G', 'go to folder'),
            ('Which folder', 'W', 'which folder'),
            ('Email drafts', 'D', 'open email draft'),
            ('Main menu', '', 'main menu')]),
        ('Edit folders', [
            ('Create folder', '', 'create folder'),
            ('Rename folder', 'F2', 'rename folder'),
            ('Move folder', '', 'move folder'),
            ('Delete empty folder', '', 'delete folder'),
            ('List folders', '', 'list folders')]),
        ('View', [
            ('Check for new mail', 'F5', 'list messages'),
            ('Next page of messages', 'Page Down', 'next messages'),
            ('Previous page of messages', 'Page Up', 'previous messages'),
            ('Newest message in folder', 'Ctrl+Home', 'newest message'),
            ('Oldest message in folder', 'Ctrl+End', 'oldest message'),
            ('Messages per page', '', 'email list size'),
            ('Show Thunderbird', '', 'show thunderbird'),
            ('Hide Thunderbird', '', 'hide thunderbird')]),
        ('Tools', [
            ('Add account', '', 'add account'),
            ('Switch account', '', 'switch account'),
            ('Which account', '', 'which email account'),
            ('Remove account', '', 'remove email account'),
            ('Add Thunderbird account', '', 'add thunderbird account'),
            ('List contacts', 'P', 'list contacts'),
            ('Add contact', '', 'add contact {value}'),
            ('Email options', '', '@options:Email'),
            ('Email help', 'Double:F1', 'help with email')]),
    ]),
    'email_draft': ('Email draft menu', [
        ('Message', [
            ('Send', 'Alt+S', 'send email'),
            ('Save draft', 'Ctrl+S', 'save draft'),
            ('Read draft', 'Ctrl+R', 'read email draft'),
            ('Save and close', '', 'leave email'),
            ('Discard draft', '', 'discard draft')]),
        ('Edit', [
            ('Undo', 'Ctrl+Z', 'undo'),
            ('Redo', 'Ctrl+Y', 'redo')]),
        ('Go to', [
            ('To', '', 'go to to'),
            ('Cc', '', 'go to cc'),
            ('Bcc', '', 'go to bcc'),
            ('Subject', '', 'go to subject'),
            ('Message body', '', 'go to body')]),
        ('Text style', [
            ('Bold', 'Ctrl+B', 'toggle bold'),
            ('Italic', 'Ctrl+I', 'toggle italic'),
            ('Underline', 'Ctrl+U', 'toggle underline')]),
        ('Attachments', [
            ('Attach a file', 'Ctrl+O', 'attach a file'),
            ('Attach the last download', '', 'attach the last download'),
            ('List attachments', 'Ctrl+L', 'list attachments'),
            ('Remove an attachment', '', 'remove attachment')]),
        ('Contacts', [
            ('List contacts', 'Ctrl+K', 'list contacts'),
            ('Add contact', '', 'add contact {value}')]),
        ('Importance and read receipt', [
            ('Change importance', 'Ctrl+Shift+I', 'change importance'),
            ('High importance', '', 'high importance'),
            ('Normal importance', '', 'normal importance'),
            ('Low importance', '', 'low importance'),
            ('Read receipt on or off', 'Ctrl+Shift+T', 'read receipt on or off'),
            ('Importance and receipt now', '', 'importance')]),
        ('Options and help', [
            ('Email options', '', '@options:Email'),
            ('Writing email help', 'Double:F1', 'help with writing email')]),
    ]),
    # Named after what is open, so it is not confused with the Notepad menu you start from.
    'note': ('Note menu', [
        ('Note', [
            ('Read note', 'Ctrl+R', 'read from top'),
            ('Save and close note', 'Ctrl+S', 'save note'),
            ('Saved notes', 'Ctrl+O', 'list notes')]),
        ('Edit', [
            ('New line', '', 'new line'),
            ('Undo', 'Ctrl+Z', 'undo'),
            ('Redo', 'Ctrl+Y', 'redo'),
            ('Scratch last words', '', 'scratch that')]),
        ('Options and help', [
            ('Notepad options', '', '@options:Notepad'),
            ('Notepad help', 'Double:F1', 'help with notepad'),
            ('Main menu', '', 'main menu')]),
    ]),
    'web': ('Web page menu', [
        ('Go to', [
            ('Back', 'Alt+Left', 'web key Back'),
            ('Forward', 'Alt+Right', 'web key Forward'),
            ('Refresh', 'F5', 'web key Refresh'),
            ('Search or enter address', 'Ctrl+L', 'web key Search'),
            ('Web history', '', 'web history'),
            ('Web browser menu', 'Escape', 'web browser menu')]),
        ('Page', [
            ('Find on page', 'Ctrl+F', 'find {value}'),
            ('Top of page', 'Ctrl+Home', 'top of page'),
            ('Bottom of page', 'Ctrl+End', 'bottom of page'),
            ('Headings', 'F6', 'list headings'),
            ('Links', 'F7', 'list links'),
            ('Form fields', 'F8', 'list fields')]),
        ('Favorites', [
            ('Add favorite', '', 'add favorite'),
            ('Go to favorite', '', 'go to favorite')]),
        ('Tools', [
            ('Downloads', 'Ctrl+D', 'download manager'),
            ('Set up Chrome', '', 'set up chrome'),
            ('Show browser window', '', 'show browser window'),
            ('Hide browser window', '', 'hide browser window')]),
        ('Options and help', [
            ('Web browser options', '', '@options:Web browser'),
            ('Web help', 'Double:F1', 'help with web')]),
    ]),
    'downloads': ('Downloads menu', [
        ('Download', [
            ('Open', 'Enter', 'open download'),
            ('Pause or resume', 'Space', 'pause or resume download'),
            ('Cancel or remove from list', 'Delete', 'delete download'),
            ('Details', '', 'download details')]),
        ('Move in list', [
            ('Start this one next', '', 'move to next'),
            ('Move earlier', 'Ctrl+Up', 'move download earlier'),
            ('Move later', 'Ctrl+Down', 'move download later')]),
        ('Folder', [
            ('Open downloads folder', '', 'open downloads folder'),
            ('Choose download folder', '', '@options:Web browser')]),
        ('Leave and help', [
            ('Close downloads', 'Escape', 'close downloads'),
            ('Downloads help', 'Double:F1', 'help with downloads')]),
    ]),
    'contacts': ('Address manager menu', [
        ('Contact', [
            ('Email this person', 'Ctrl+E', 'email contact'),
            ('Open details', 'Enter', 'open contact'),
            ('Read all details', '', 'read contact'),
            ('Phone number', '', 'call details'),
            ('Edit contact', 'F2', 'edit contact'),
            ('Delete contact', 'Delete', 'delete contact')]),
        ('Address book', [
            ('Add contact', 'Ctrl+N', 'add contact'),
            ('Find contact', 'Ctrl+F', 'find contact {value}'),
            ('Refresh contacts', '', 'refresh contacts'),
            # Last, so hiding it (one email account) moves no other item.
            ('Choose address book', 'Ctrl+L', 'choose address book')]),
        ('Leave and help', [
            ('Main menu', '', 'main menu'),
            ('Address manager help', 'Double:F1', 'help with contacts')]),
    ]),
    'calendar': ('Schedule manager menu', [
        ('Event', [
            ('Read event', 'Enter', 'read event'),
            ('Next event', 'Down', 'next event'),
            ('Previous event', 'Up', 'previous event'),
            ('Add event', 'Ctrl+N', 'add event'),
            ('Edit event', 'F2', 'edit event'),
            ('Delete event', 'Delete', 'delete event')]),
        ('Go to', [
            ('Today', 'Home', 'today'),
            ('Next day', 'Right', 'next day'),
            ('Previous day', 'Left', 'previous day'),
            ('Next week', 'Page Down', 'next week'),
            ('Previous week', 'Page Up', 'previous week'),
            ('Go to a date', 'Ctrl+G', 'go to date')]),
        ('Calendar', [
            ('Refresh calendar', '', 'refresh calendar'),
            # Last, so hiding it (one email account) moves no other item.
            ('Choose calendar', 'Ctrl+L', 'choose calendar')]),
        ('Leave and help', [
            ('Main menu', '', 'main menu'),
            ('Schedule manager help', 'Double:F1', 'help with calendar')]),
    ]),
    'help': ('Help menu', [
        ('Help', [
            ('Help topics', '', 'help topics'),
            ('Subsections', '', 'list subsections'),
            ('Release notes', '', 'release notes'),
            ('Lessons', '', 'start tutorial'),
            ('Open the guide folder', '', 'open user guides'),
            ('Close help', '', 'close help'),
            ('Main menu', '', 'main menu')]),
    ]),
    'tutorial': ('Lessons menu', [
        ('Lessons', [
            ('Lesson list', 'Ctrl+L', 'lesson list'),
            ('Repeat', 'Ctrl+R', 'repeat'),
            ('Continue reading', 'Ctrl+Down', 'continue reading'),
            ('Next lesson', '', 'next lesson'),
            ('Previous lesson', '', 'previous lesson'),
            ('Find lesson', 'Ctrl+F', 'find lesson {value}'),
            ('Explain a command', 'Ctrl+E', 'explain command {value}'),
            ('List commands', 'Double:F1', 'list commands'),
            ('Main menu', '', 'main menu')]),
    ]),
    'attachments': ('Attachments menu', [
        ('Attachment', [
            ('Open', 'Enter', 'open attachment'),
            ('Save in Downloads', 'Ctrl+S', 'save attachment'),
            ('Save to a folder', 'Ctrl+D', 'save attachment to folder'),
            ('Save all', 'Ctrl+Shift+S', 'save all attachments'),
            ('Details', 'Ctrl+I', 'read attachment details'),
            ('Remove from this email', 'Delete', 'remove attachment'),
            ('Attach another file', 'Ctrl+O', 'attach a file')]),
        # Tags, as in File manager (Will, November 4, 2026); the guide says this menu has every choice.
        ('Tags', [
            ('Tag or untag', 'Space', 'tag attachment'),
            ('Tag all', 'Ctrl+A', 'tag all attachments'),
            ('What is tagged', 'Ctrl+Shift+T', 'what attachments are tagged'),
            ('Clear tags', 'Ctrl+Shift+A', 'clear attachment tags')]),
        ('Leave and help', [
            ('Close the list', 'Escape', 'close attachments'),
            ('Attachments help', 'Double:F1', 'help with attachments')]),
    ]),
    # Named after what is open, so it is not confused with the Document reader menu you start from.
    'file_reader': ('Document menu', [
        ('Read', [
            ('Read document', 'Ctrl+R', 'read document'),
            ('Find text', 'Ctrl+F', 'find {value}'),
            ('Beginning of document', '', 'go to beginning of document'),
            ('End of document', '', 'go to end of document'),
            ('Formatting details', 'Insert+F', 'what formatting'),
            ('Selected text', 'Insert+Shift+Down', 'what is selected'),
            ('Say all from here', 'Insert+Down', 'say all')]),
        ('Go to', [
            ('Next heading', 'H', 'next heading'),
            ('Previous heading', 'Shift+H', 'previous heading'),
            ('Next table', 'T', 'next table'),
            ('Next list', 'L', 'next list'),
            ('Next link', 'K', 'next link'),
            ('Follow link', 'Enter', 'follow link'),
            ('Next bookmark', 'B', 'next bookmark'),
            ('Next footnote', 'N', 'next footnote')]),
        ('Leave and help', [
            ('Back to files', 'Escape', 'back to files'),
            ('Main menu', '', 'main menu'),
            ('Document reader help', 'Double:F1', 'help with document reader')]),
    ]),
    # YouTube (youtube_screen.py). Each key is the same on the screen without the menu.
    'youtube': ('YouTube actions menu', [
        ('Play', [
            ('Play or pause', 'Space', 'play or pause video'),
            ('Skip back', 'Left', 'skip back'),
            ('Skip forward', 'Right', 'skip forward'),
            ('Restart the video', '0', 'restart video'),
            ('Next video', 'N', 'next video'),
            ('Previous video', 'P', 'previous video'),
            ('Skip ad', 'S', 'skip ad'),
            ('Stop video', '', 'stop video'),
            ('Skip amount', '', 'skip amount {value}')]),
        ('Volume and speed', [
            ('Volume up', 'Ctrl+Up', 'video volume up'),
            ('Volume down', 'Ctrl+Down', 'video volume down'),
            ('Sound on or off', 'M', 'mute or unmute'),
            ('Slower', 'comma', 'slower video'),
            ('Faster', 'period', 'faster video'),
            ('Normal speed', '', 'normal speed')]),
        ('Captions and picture', [
            ('Captions on or off', 'C', 'captions on or off'),
            ('Read the caption', 'R', 'read caption'),
            ('Video quality', 'Q', 'video quality'),
            ('Video full screen', 'F', 'video full screen'),
            ('Autoplay on or off', 'A', 'autoplay on or off')]),
        ('This video', [
            ('Video details', 'I', 'video details'),
            ('Description', 'D', 'read description'),
            ('Comments', 'O', 'read comments'),
            ('Up next', 'X', 'up next'),
            ('Go to channel', 'G', 'go to channel'),
            ('Open in browser', '', 'open in browser'),
            ('List chapters', 'H', 'list chapters'),
            ('Next chapter', 'Ctrl+Right', 'next chapter'),
            ('Previous chapter', 'Ctrl+Left', 'previous chapter')]),
        ('Your account', [
            ('Like', 'T', 'like video'),
            ('Subscribe or unsubscribe', 'U', 'subscribe or unsubscribe'),
            ('Save to Watch later', '', 'save to watch later'),
            ('Save to a playlist', 'W', 'save video'),
            ('Add a comment', '', 'post comment {value}'),
            ('Sign in', '', 'sign in'),
            ('Sign out', '', 'sign out')]),
        ('Search', [
            ('Search', 'Ctrl+F', 'search youtube'),
            ('Search filters', 'Ctrl+Shift+F', 'search filters'),
            ('Clear filters', '', 'clear filters')]),
        ('Go to', [
            ('YouTube menu', '', 'youtube menu'),
            ('Home', '', 'youtube home'),
            ('New from subscriptions', '', 'subscriptions'),
            ('Subscribed channels', '', 'my subscriptions'),
            ('History', '', 'history'),
            ('Watch later', '', 'watch later'),
            ('Liked videos', '', 'liked videos'),
            ('Your playlists', '', 'my playlists'),
            ('Load the list again', 'F5', 'refresh youtube')]),
        ('Leave and help', [
            ('Go back', 'Escape', 'go back'),
            ('YouTube help', 'Double:F1', 'help with youtube'),
            ('Media menu', '', 'media menu'),
            ('Main menu', '', 'main menu')]),
    ]),
}

# Screens where Alt does something here. Word processor, document, File manager
# and Media player handle Alt themselves when it is pressed.
ALT_SCREENS = frozenset(MENUS) | {'awake', 'browser_menu', 'media', 'podcast'}
# Spoken ways to open a menu, besides its name ("email menu").
OPEN_PHRASES = {'mailbox': ('menu', 'open menu', 'mail menu'), 'file_reader': ('menu', 'open menu', 'reader menu', 'document reader menu'),
                'email_draft': ('draft menu',), 'web': ('page menu',), 'help': (), 'note': ('notepad menu',),
                'tutorial': ('tutorial menu', 'lesson menu'), 'downloads': ('menu', 'open menu', 'download menu'),
                'contacts': ('menu', 'open menu', 'contact menu', 'contacts menu'), 'calendar': ('menu', 'open menu', 'calendar menu'),
                'attachments': ('menu', 'open menu', 'attachment menu'), 'youtube': ('menu', 'open menu', 'actions menu')}
# Each item's letter, by its command, so the same action has the same letter in every
# menu (Will, November 10, 2026). Mostly the first letter of the action's main word; where
# two items in a group would share one, a well-known letter from the word (Windows style).
# Help is always H and Options always O.
LETTERS = {
    # Email: Message
    'new email': 'N', 'open current message': 'O', 'reply': 'R', 'reply all': 'A', 'forward': 'F',
    'new email to sender': 'E', 'move': 'M', 'delete': 'D', 'message details': 'I',
    # Email: Header
    'who is it from': 'F', 'who is it to': 'T', 'read the cc': 'C', 'what is the subject': 'S',
    'when was it sent': 'D', 'copy sender address': 'A',
    # Attachments, in email and on the Attachments screen
    'list attachments': 'L', 'open attachment': 'O', 'save all attachments': 'S', 'how big are the attachments': 'Z',
    'save attachment': 'D', 'save attachment to folder': 'F', 'read attachment details': 'I', 'remove attachment': 'R',
    'attach a file': 'A', 'attach the last download': 'D', 'close attachments': 'C',
    'tag attachment': 'T', 'tag all attachments': 'A', 'what attachments are tagged': 'W', 'clear attachment tags': 'C',
    # Email: Unread and flags, Select
    'mark as read or unread': 'U', 'flag or unflag': 'F', 'mark important or not important': 'I', 'message status': 'S',
    'toggle message selection': 'S', 'select all messages': 'A', 'clear selection': 'C', 'what is selected': 'W',
    # Email: Go to
    'go to inbox': 'I', 'go to sent': 'S', 'go to drafts': 'D', 'go to trash': 'T', 'go to spam': 'P',
    'go to folder': 'C', 'which folder': 'W', 'open email draft': 'E', 'main menu': 'M',
    # Email: Edit folders
    'create folder': 'C', 'rename folder': 'R', 'move folder': 'M', 'delete folder': 'D', 'list folders': 'L',
    # Email: View
    'list messages': 'C', 'next messages': 'N', 'previous messages': 'P', 'newest message': 'W', 'oldest message': 'O',
    'email list size': 'M', 'show thunderbird': 'S', 'hide thunderbird': 'H',
    # Email: Tools; contacts in email and drafts
    'add account': 'A', 'switch account': 'S', 'which email account': 'W', 'remove email account': 'R',
    'add thunderbird account': 'T', 'list contacts': 'L', 'add contact {value}': 'C',
    # Email draft
    'send email': 'S', 'save draft': 'V', 'read email draft': 'R', 'leave email': 'C', 'discard draft': 'D',
    'undo': 'U', 'redo': 'R', 'go to to': 'T', 'go to cc': 'C', 'go to bcc': 'B', 'go to subject': 'S', 'go to body': 'M',
    'toggle bold': 'B', 'toggle italic': 'I', 'toggle underline': 'U',
    'change importance': 'C', 'high importance': 'H', 'normal importance': 'N', 'low importance': 'L',
    'read receipt on or off': 'R', 'importance': 'I',
    # Note
    'read from top': 'R', 'save note': 'C', 'list notes': 'N', 'new line': 'N', 'scratch that': 'S',
    # Web page
    'web key Back': 'B', 'web key Forward': 'F', 'web key Refresh': 'R', 'web key Search': 'S', 'web history': 'H',
    'web browser menu': 'W', 'find {value}': 'F', 'top of page': 'T', 'bottom of page': 'B', 'list headings': 'H',
    'list links': 'L', 'list fields': 'I', 'add favorite': 'A', 'go to favorite': 'G', 'download manager': 'D',
    'set up chrome': 'C', 'show browser window': 'S', 'hide browser window': 'H',
    # Downloads
    'open download': 'O', 'pause or resume download': 'P', 'delete download': 'C', 'download details': 'I',
    'move to next': 'S', 'move download earlier': 'E', 'move download later': 'L', 'open downloads folder': 'F',
    'close downloads': 'C',
    # Address manager
    'email contact': 'M', 'open contact': 'O', 'read contact': 'R', 'call details': 'P', 'edit contact': 'E',
    'delete contact': 'D', 'add contact': 'A', 'find contact {value}': 'F', 'refresh contacts': 'R',
    'choose address book': 'C',
    # Schedule manager
    'read event': 'R', 'next event': 'N', 'previous event': 'P', 'add event': 'A', 'edit event': 'E', 'delete event': 'D',
    'today': 'T', 'next day': 'N', 'previous day': 'P', 'next week': 'W', 'previous week': 'K', 'go to date': 'G',
    'refresh calendar': 'R', 'choose calendar': 'C',
    # Help and Lessons
    'help topics': 'T', 'list subsections': 'S', 'release notes': 'R', 'start tutorial': 'L', 'open user guides': 'G',
    'close help': 'C', 'lesson list': 'L', 'repeat': 'R', 'continue reading': 'C', 'next lesson': 'N',
    'previous lesson': 'P', 'find lesson {value}': 'F', 'explain command {value}': 'E', 'list commands': 'H',
    # Document reader
    'read document': 'R', 'go to beginning of document': 'B', 'go to end of document': 'E', 'what formatting': 'D',
    'say all': 'S', 'next heading': 'H', 'previous heading': 'P', 'next table': 'T', 'next list': 'L', 'next link': 'K',
    'follow link': 'F', 'next bookmark': 'B', 'next footnote': 'N', 'back to files': 'B',
    # YouTube
    'play or pause video': 'P', 'skip back': 'B', 'skip forward': 'F', 'restart video': 'R', 'next video': 'N',
    'previous video': 'V', 'skip ad': 'A', 'stop video': 'S', 'skip amount {value}': 'M',
    'video volume up': 'U', 'video volume down': 'D', 'mute or unmute': 'M', 'slower video': 'S', 'faster video': 'F',
    'normal speed': 'N', 'captions on or off': 'C', 'read caption': 'R', 'video quality': 'Q', 'video full screen': 'F',
    'autoplay on or off': 'A', 'video details': 'I', 'read description': 'D', 'read comments': 'C', 'up next': 'U',
    'go to channel': 'G', 'open in browser': 'B', 'list chapters': 'L', 'next chapter': 'N', 'previous chapter': 'P',
    'like video': 'L', 'subscribe or unsubscribe': 'S', 'save to watch later': 'W', 'save video': 'P',
    'post comment {value}': 'C', 'sign in': 'I', 'sign out': 'O', 'search youtube': 'S', 'search filters': 'F',
    'clear filters': 'C', 'youtube menu': 'Y', 'youtube home': 'H', 'subscriptions': 'N', 'my subscriptions': 'C',
    'history': 'I', 'watch later': 'W', 'liked videos': 'L', 'my playlists': 'P', 'refresh youtube': 'R',
    'go back': 'B', 'media menu': 'E',
}


def item_letter(command):
    """The letter that runs an item in its group: H for any help, O for any options."""
    if command.startswith('help with '):
        return 'H'
    if command.startswith('@options:'):
        return 'O'
    return LETTERS[command]


def group_letter(name):
    """A group's letter is its first letter: M for Message, O for Options and help."""
    return name[0].upper()


def item_label(label, letter, index, count):
    """An item as the menus say it: Reply (R), 3 of 9."""
    return label + ' (' + letter + '), ' + str(index + 1) + ' of ' + str(count) + '.'
# Context flags that mean a text box, list or question owns the keyboard.
BUSY_CONTEXT = ('named_list', 'task_input', 'account_entry', 'browser_name_input', 'file_name_input', 'media_input',
                'media_form', 'web_private', 'web_field', 'web_name_list')


def menu_path(mode, group, index):
    """The keys that reach an item from the screen: Alt, then letters ("Alt, M, R")."""
    groups = MENUS[mode][1]
    name, entries = groups[group]
    return 'Alt, ' + ((group_letter(name) + ', ') if len(groups) > 1 else '') + item_letter(entries[index][2])


def items(mode):
    """Every item of a screen's menu as (group, label, key or menu path, command)."""
    rows = []
    for group, (name, entries) in enumerate(MENUS[mode][1]):
        for index, (label, key, command) in enumerate(entries):
            rows.append((name, label, key or menu_path(mode, group, index), command))
    return rows


def alt_menu_key(context, command_entry_active=False, typed_text=''):
    """What a lone Alt press (pressed and let go) sends, or None to leave it alone."""
    mode = context.get('mode')
    if command_entry_active:
        return None
    if context.get('screen_menu'):
        return 'Alt'
    if mode not in ALT_SCREENS or context.get('confirmation') is not None:
        return None
    if any(context.get(name) for name in BUSY_CONTEXT):
        return None
    # A typed command is kept. Notes and email boxes keep their text: the window
    # adds it first, as Enter or Tab would.
    if typed_text.strip() and mode not in ('note', 'email_draft'):
        return None
    return 'Alt'


def alt_unavailable(context, command_entry_active=False, typed_text=''):
    """What to say when a lone Alt opens no menu, so the key is never silent."""
    if command_entry_active or typed_text.strip() and context.get('mode') not in ('note', 'email_draft'):
        return 'No Alt menu while a command is typed. Press Enter to run it, or Escape to clear it.'
    if context.get('confirmation') is not None:
        return 'Answer the question first. Press Y for yes or N for no.'
    if any(context.get(name) for name in BUSY_CONTEXT):
        return 'No Alt menu here. Finish this first, or press Escape to go back.'
    return 'This screen has no Alt menu.'


def overlay_key(keysym, char, state):
    """The menu key for a key pressed while a menu is open.

    None lets the key do its usual job (shortcuts, F keys, Alt combinations);
    '' swallows it so that it does not type into the page or message."""
    from key_state import modifiers
    control, shift, alt = modifiers(state)
    if control or alt:
        return None
    named = {'Up': 'Up', 'Down': 'Down', 'Left': 'Left', 'Right': 'Right', 'Home': 'Home', 'End': 'End',
             'Return': 'Enter', 'KP_Enter': 'Enter', 'Escape': 'Escape', 'ISO_Left_Tab': 'ShiftTab',
             'Tab': 'ShiftTab' if shift else 'Tab'}
    if keysym in named:
        return named[keysym]
    if char and len(char) == 1 and char.isalnum():
        return 'Letter:' + char
    if keysym in ('space', 'BackSpace', 'Delete', 'Prior', 'Next') or char and char.isprintable():
        return ''
    return None


class ScreenMenu:
    def __init__(self, app):
        self.app = app
        self.mode = None
        self.group = None
        self.index = 0

    def is_open(self, mode):
        return self.mode is not None and self.mode == mode

    def entries(self):
        groups = MENUS[self.mode][1]
        if len(groups) == 1:
            return self.shown(groups[0][1])
        if self.group is None:
            return [(name, '', None) for name, _ in groups]
        return self.shown(groups[self.group][1])

    def shown(self, entries):
        """The items that apply now. Choosing a calendar or address book is left out with one email account."""
        hidden = ()
        if self.mode in ('calendar', 'contacts'):
            try:
                hidden = __import__(self.mode + '_screen').hidden_commands()
            except Exception:
                hidden = ()
        return [entry for entry in entries if entry[2] not in hidden]

    def letter_of(self, entry):
        label, _, command = entry
        return group_letter(label) if command is None else item_letter(command)

    def describe(self, index):
        entries = self.entries()
        label, key, command = entries[index]
        text = item_label(label, self.letter_of(entries[index]), index, len(entries))
        if command is None:
            return text
        if key:
            text += ' ' + spoken_key(key) + '.'
        if not command.startswith(('@', 'web key ')) and '{value}' not in command:
            text += hint(' Say ' + command + '.')
        return text

    def keyboard(self, key, mode):
        """Keys for the menu. Called first in companion.navigation_key."""
        if self.mode is not None and self.mode != mode:
            self.close()
        if self.mode is None:
            if key != 'Alt':
                return None
            if mode in MENUS:
                return '@sm:open'
            if mode in ALT_SCREENS:
                return '@sm:alt'
            return None
        nav = {'Up': 'previous', 'Left': 'previous', 'ShiftTab': 'previous', 'Down': 'next', 'Right': 'next',
               'Tab': 'next', 'Home': 'home', 'End': 'end', 'Enter': 'enter', 'Escape': 'escape', 'Alt': 'close'}
        if key in nav:
            return '@sm:' + nav[key]
        if key.startswith('Letter:'):
            return '@sm:letter:' + key[7:]
        if key == 'Control':
            return None
        # Any other key closes the menu and does its usual job.
        self.close()
        return None

    def close(self):
        self.mode = None
        self.group = None
        self.index = 0

    def available(self, mode):
        """None when the menu can open, or what to say when a step must finish first."""
        m = self.app
        busy = 'Finish or cancel this step first. Then press Alt for the menu.'
        if m.NAMED_LIST or getattr(m, 'ACCOUNT_PICKER', None):
            return 'Close this list first. Then press Alt for the menu.'
        if mode == 'mailbox':
            mail = m.mail_session
            if mail is None:
                return 'Email is not open.'
            if getattr(mail, 'pending', None) or getattr(mail, 'folder_picker', None) or getattr(mail, 'folder_choice', None):
                return busy
        if mode == 'email_draft' and (m.email_draft is None or m.pending_send is not None):
            return 'Answer the send question first. Then press Alt for the menu.' if m.email_draft else busy
        if mode == 'web':
            web = m.web_session
            if web is None or getattr(web, 'pending', None) or getattr(web, 'submit_pending', None) or getattr(web, 'list_focus', None) or getattr(web, 'keyboard_field', None):
                return busy
        if mode == 'help' and m.help_session is None:
            return busy
        if mode == 'tutorial' and m.tutorial_session is None:
            return busy
        if mode == 'file_reader' and m.FILE_READER is None:
            return busy
        return None

    def open(self, mode):
        m = self.app
        problem = self.available(mode)
        if problem:
            m.speak(problem)
            return mode
        self.mode = mode
        self.group = None
        self.index = 0
        title = MENUS[mode][0]
        m.speak(title + '. ' + self.describe(0))
        return mode

    def other_alt(self, mode):
        """Alt on screens that already are, or already have, a menu."""
        m = self.app
        if mode == 'awake' and m.account_setup:
            # The account type question is open: Alt must not say a main menu item.
            m.speak('Answer the question first. ' + m.ACCOUNT_TYPE_PROMPT)
            return mode
        if mode == 'awake':
            if m.MAIN_MENU_INDEX is None:
                m.MAIN_MENU_INDEX = 0
            names = [name for name, _ in m.MAIN_MENU_CHOICES]
            m.speak('Main menu. ' + announce_item(names[m.MAIN_MENU_INDEX], m.MAIN_MENU_INDEX, len(names)))
            return mode
        if mode == 'browser_menu':
            menu = getattr(m.web_session, 'menu', None)
            if menu is not None and menu.level == 'menu':
                # Where you are, on the item you are on, as Alt on the main menu says it.
                state = menu.menu(m.web_session, m.PREFERENCES.get('web_keep_open', False))
                if state:
                    menu.index = state[1] or 0
                    m.speak('Web browser menu. ' + menu.notice(state[0]))
                    return mode
            return m.handle('web browser menu', mode, typed=True)
        if mode in ('media', 'podcast') and m.MEDIA_HUB:
            nav = m.media_navigation()
            if nav.form or nav.pending:
                m.speak('Finish or cancel this form first. Then press Alt for the menu.')
                return mode
            result = nav.keyboard('Tab')
            name = 'Podcasts menu. ' if nav.section == 'podcast' else 'Radio menu. '
            if nav.focus == 'actions':
                m.speak(name + result.split('. ', 1)[-1] if result.startswith('Actions. ') else name + result)
            else:
                m.speak('Menu closed. ' + result)
            return mode
        return None

    def run(self, command, mode):
        m = self.app
        if command.startswith('@options:'):
            m.SETTINGS_RETURN_MODE = mode
            result = m.open_settings(mode)
            if result == 'settings' and m.SETTINGS_PANEL:
                m.SETTINGS_PANEL.command(command.split(':', 1)[1])
            return result
        if '{value}' in command:
            return m.task_navigation().action(command, mode)
        return m.handle(command, mode, typed=True)

    def choose(self, index, mode):
        entries = self.entries()
        if not 0 <= index < len(entries):
            self.app.speak('Nothing to choose here.')
            return mode
        label, _, command = entries[index]
        if command is None:
            self.group = index
            self.index = 0
            self.app.speak(label + ' menu. ' + self.describe(0))
            return mode
        self.close()
        return self.run(command, mode)

    def back(self, mode):
        m = self.app
        if len(MENUS[self.mode][1]) > 1 and self.group is not None:
            self.index = self.group
            self.group = None
            m.speak(MENUS[self.mode][0] + '. ' + self.describe(self.index))
            return mode
        self.close()
        m.speak('Menu closed. ' + m.options_return_notice(mode))
        return mode

    def move(self, command, mode):
        entries = self.entries()
        old = self.index
        if command == 'home':
            self.index = 0
        elif command == 'end':
            self.index = len(entries) - 1
        else:
            self.index = max(0, min(len(entries) - 1, old + (1 if command == 'next' else -1)))
        edge = ''
        if self.index == old:
            edge = 'Start of list. ' if command in ('previous', 'home') else 'End of list. '
        self.app.speak(edge + self.describe(self.index))
        return mode

    def letter(self, value, mode):
        """A letter opens the group, or runs the item, that has it. A number, or a letter no
        item has, does nothing and says so (Will, November 10, 2026: no numbered paths)."""
        entries = self.entries()
        index = next((i for i, entry in enumerate(entries) if self.letter_of(entry) == value.upper()), None)
        if index is None:
            self.app.speak('No item uses ' + value.upper() + '.')
            return mode
        self.index = index
        return self.choose(index, mode)

    def handle(self, text, mode):
        """Menu keys and voice commands. None means the screen handles the text."""
        m = self.app
        if self.mode is not None and self.mode != mode:
            self.close()
        if text.startswith('@sm:'):
            action = text[4:]
            if action == 'open':
                return self.open(mode) if self.mode is None else self.back(mode)
            if action == 'alt':
                return self.other_alt(mode) or mode
            if self.mode is None:
                return mode
            if action == 'close':
                self.close()
                m.speak('Menu closed. ' + m.options_return_notice(mode))
                return mode
            if action in ('next', 'previous', 'home', 'end'):
                return self.move(action, mode)
            if action == 'enter':
                return self.choose(self.index, mode)
            if action == 'escape':
                return self.back(mode)
            if action.startswith('letter:'):
                return self.letter(action[7:], mode)
            return mode
        command = m.normalized_command(text)
        if self.mode is None:
            if mode in MENUS and command in (MENUS[mode][0].lower(),) + OPEN_PHRASES.get(mode, ()):
                return self.open(mode)
            return None
        if command in ('next', 'previous', 'next item', 'previous item'):
            return self.move(command.split()[0], mode)
        if command in ('first item', 'start of list', 'top of list'):
            return self.move('home', mode)
        if command in ('last item', 'end of list', 'bottom of list'):
            return self.move('end', mode)
        if command in ('enter', 'okay', 'ok', 'that one', 'confirm', 'confirm that', 'open', 'open it'):
            return self.choose(self.index, mode)
        if command in ('escape', 'go back', 'back', 'cancel'):
            return self.back(mode)
        if command in ('close menu', 'exit menu', 'leave menu', 'alt'):
            return self.handle('@sm:close', mode)
        for index, entry in enumerate(self.entries()):
            if command == entry[0].lower():
                return self.choose(index, mode)
        # Any other command closes the menu and works as usual on this screen.
        self.close()
        return None
