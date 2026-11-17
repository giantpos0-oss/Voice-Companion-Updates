"""N (next video) never freezes Voice Companion when YouTube answers slowly.

On November 14, 2026, Will pressed N while YouTube's page was answering each check in
about 3.5 seconds. Companion checked up to 20 times whether the next video had started,
so the app froze for 76 seconds. N now waits at most NEXT_SECONDS in all.
The player is faked at its boundary, with a clock that moves as a slow page would.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import youtube_screen
from youtube_screen import YouTubeScreen, NEXT_SECONDS


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class SlowPlayer:
    """A player whose page takes `delay` seconds to answer; the next video starts after `starts_after` checks."""

    def __init__(self, clock, delay, starts_after=None):
        self.clock, self.delay, self.starts_after = clock, delay, starts_after
        self.checks = 0

    def state(self):
        self.clock.now += self.delay
        self.checks += 1
        if self.starts_after is not None and self.checks > self.starts_after:
            return {'id': 'next', 'title': 'Next one', 'channel': 'Someone'}
        return {'id': 'first', 'title': 'First one'}

    def next_video(self):
        self.clock.now += self.delay

    def settle(self, ms):
        self.clock.now += ms / 1000.0


def press_n(player):
    screen = SimpleNamespace(player=player, need_video=lambda: None, video={'id': 'first'},
                             now_on=lambda state, lead='': lead + 'Playing ' + state['title'] + '.')
    return YouTubeScreen.next_video(screen)


class NextVideoTests(unittest.TestCase):
    def test_a_slow_youtube_never_holds_n_for_long(self):
        clock = Clock()
        player = SlowPlayer(clock, delay=3.5)
        with patch.object(youtube_screen.time, 'monotonic', clock):
            said = press_n(player)
        waited = clock.now - 1000.0
        self.assertLess(waited, NEXT_SECONDS + 3.5 + 1, 'N froze Voice Companion (76 seconds before the fix).')
        self.assertEqual(said, 'YouTube is slow to answer, so the next video may still be loading. Press F3 to hear what is playing.')

    def test_the_next_video_is_said_as_soon_as_it_starts(self):
        clock = Clock()
        player = SlowPlayer(clock, delay=0.01, starts_after=2)
        with patch.object(youtube_screen.time, 'monotonic', clock):
            self.assertEqual(press_n(player), 'Next video. Playing Next one.')
        self.assertLess(clock.now - 1000.0, 1.0)

    def test_a_quick_youtube_with_no_next_video_says_so(self):
        clock = Clock()
        player = SlowPlayer(clock, delay=0.01)
        with patch.object(youtube_screen.time, 'monotonic', clock):
            self.assertEqual(press_n(player), 'There is no next video.')
        self.assertLess(clock.now - 1000.0, NEXT_SECONDS + 1)


if __name__ == '__main__':
    unittest.main()
