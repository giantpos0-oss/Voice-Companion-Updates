"""Options, Favorite apps: one list of every app (Will, November 10, 2026).

Space selects or unselects the app under the cursor. Control+Up and Control+Down move it,
and Control+Home and Control+End move it to the top or the bottom. Favorite apps
(Control+F1) lists the selected apps in this order.

What is chosen is saved as it was before 0.2.211: one on or off setting per app
(favorite_word_processor). The order is saved as favorite_order, a list of every app
name. Saved options from older versions have no order yet, so their apps keep the old
order, which is the order of FAVORITE_APPS.
"""
from menu_navigation import next_match
from task_navigation import FAVORITE_APPS, FAVORITE_ORDER, favorite_key, favorite_order

# Voice commands in the list. Plain words act on the app under the cursor.
# "Select" only selects and "Unselect" only unselects, so saying one twice never undoes it.
SELECT_WORDS = ('select', 'select app', 'select it', 'select this app', 'choose', 'choose app', 'add', 'add app')
UNSELECT_WORDS = ('unselect', 'unselect app', 'unselect it', 'unselect this app', 'deselect', 'deselect app',
                  'remove', 'remove app')
TOGGLE_WORDS = ('toggle', 'toggle app', 'select or unselect')
MOVE_WORDS = {'move up': 'up', 'move app up': 'up', 'move it up': 'up', 'move down': 'down', 'move app down': 'down',
              'move it down': 'down', 'move to top': 'top', 'move to the top': 'top', 'move app to top': 'top',
              'move app to the top': 'top', 'move to first': 'top', 'move to bottom': 'bottom',
              'move to the bottom': 'bottom', 'move app to bottom': 'bottom', 'move app to the bottom': 'bottom',
              'move to last': 'bottom'}
CURSOR_WORDS = {'next': 1, 'next app': 1, 'previous': -1, 'previous app': -1, 'first item': 'first',
                'start of list': 'first', 'top of list': 'first', 'first app': 'first', 'last item': 'last',
                'end of list': 'last', 'bottom of list': 'last', 'last app': 'last'}
HINT = 'Space selects or unselects. Control+Up or Control+Down moves.'


def plain(command):
    """A spoken command without capitals, commas or a full stop: "Move up." is "move up"."""
    return ' '.join(str(command).casefold().replace(',', ' ').strip().rstrip('.!?').split())


class FavoriteList:
    """The staged list in Options. It changes session.values only; OK saves, Cancel undoes."""

    def __init__(self, session):
        self.session = session
        self.order = favorite_order(session.values)
        self.index = 0

    def __len__(self):
        return len(self.order)

    def chosen(self, index=None):
        name = self.order[self.index if index is None else index]
        return bool(self.session.values.get(favorite_key(name)))

    def state(self, index=None):
        return 'selected' if self.chosen(index) else 'not selected'

    def label(self, index=None):
        """What is said on an app: "Email, selected, 4 of 12."."""
        index = self.index if index is None else index
        return self.order[index] + ', ' + self.state(index) + ', ' + str(index + 1) + ' of ' + str(len(self.order)) + '.'

    def line(self, index):
        """What is shown in the list on the screen: "Email, selected"."""
        return self.order[index] + ', ' + self.state(index)

    def _save_order(self):
        self.session.set(FAVORITE_ORDER, list(self.order))

    def toggle(self):
        name = self.order[self.index]
        self.session.values[favorite_key(name)] = not self.chosen()
        return name + ', ' + self.state() + '.'

    def choose(self, selected):
        """Select or unselect the app under the cursor; says so when it already is."""
        if self.chosen() == selected:
            return self.order[self.index] + ' is already ' + self.state() + '.'
        return self.toggle()

    def move(self, where):
        """Move the app under the cursor: 'up', 'down', 'top' or 'bottom'."""
        name = self.order[self.index]
        last = len(self.order) - 1
        target = {'up': self.index - 1, 'down': self.index + 1, 'top': 0, 'bottom': last}[where]
        if target < 0 or self.index == 0 and where == 'top':
            return name + ' is already at the top.'
        if target > last or self.index == last and where == 'bottom':
            return name + ' is already at the bottom.'
        self.order.insert(target, self.order.pop(self.index))
        self.index = target
        self._save_order()
        return name + ', moved to ' + str(target + 1) + ' of ' + str(len(self.order)) + '.'

    def go(self, where):
        """Move the cursor: 1, -1, 'first' or 'last'. Stops at the ends, as every list does."""
        if where in ('first', 'last'):
            target = 0 if where == 'first' else len(self.order) - 1
        else:
            target = self.index + where
        if target < 0 or where == 'first' and self.index == 0:
            return 'Start of list.'
        if target >= len(self.order) or where == 'last' and self.index == len(self.order) - 1:
            return 'End of list.'
        self.index = target
        return self.label()

    def letter(self, character):
        """A first letter moves to the next app that starts with it."""
        index = next_match(self.order, self.index, character)
        if index is None:
            return 'No app starts with ' + character.upper() + '.'
        if index == self.index:
            return 'End of matching items.'
        self.index = index
        return self.label()

    def keyboard(self, key, control=False):
        """A key in the list: Up, Down, Home, End, Space or a letter. None for any other key."""
        if control and key in ('Up', 'Down', 'Home', 'End'):
            return self.move({'Up': 'up', 'Down': 'down', 'Home': 'top', 'End': 'bottom'}[key])
        if control:
            return None
        if key in ('Up', 'Down'):
            return self.go(-1 if key == 'Up' else 1)
        if key in ('Home', 'End'):
            return self.go('first' if key == 'Home' else 'last')
        if key == 'Space':
            return self.toggle()
        if len(key) == 1 and key.isalpha():
            return self.letter(key)
        return None

    def voice(self, command):
        """A spoken command for the list, or None when it is not one."""
        words = plain(command)
        if words in SELECT_WORDS or words in UNSELECT_WORDS:
            return self.choose(words in SELECT_WORDS)
        if words in TOGGLE_WORDS:
            return self.toggle()
        if words in MOVE_WORDS:
            return self.move(MOVE_WORDS[words])
        if words in CURSOR_WORDS:
            return self.go(CURSOR_WORDS[words])
        return None


__all__ = ['FavoriteList', 'FAVORITE_APPS', 'HINT', 'SELECT_WORDS', 'UNSELECT_WORDS', 'TOGGLE_WORDS', 'MOVE_WORDS', 'CURSOR_WORDS']
