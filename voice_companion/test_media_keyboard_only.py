"""Radio and Podcasts with the keyboard only (nightly sweep, November 6, 2026).

A blind user who never speaks a command uses only keys. Every key must say something, and
the lists must offer only what can be done. These drive the real app through
companion.navigation_key and companion.handle_keyboard with a real MediaHub."""
import unittest

import companion
from test_media_expert_user import ExpertMediaTestCase

FORM_OPEN = 'Finish or cancel this form first. Enter continues. Escape cancels.'


class FormKeysAreNeverSilentTests(ExpertMediaTestCase):
    """In a radio or podcast form (Station database, Schedule, Search), Space on OK,
    Control+S, Control+D, F5 and Delete said nothing at all."""

    def open_station_database(self):
        self.say('Media')
        self.key('Enter')                     # Radio
        for _ in range(5):
            self.key('Down')                  # Station database
        self.assertTrue(self.key('Enter').startswith('Station database. '))

    def test_space_on_ok_and_cancel_presses_them(self):
        self.open_station_database()
        self.key('Down')                      # iprd
        self.assertEqual(self.key('Tab'), 'OK.')
        said = self.key('Space')
        self.assertIsNone(companion.MEDIA_NAV.form)
        self.assertIn('iprd', said.casefold())
        self.assertEqual(self.hub.source(), 'iprd')

    def test_space_on_cancel_cancels(self):
        self.open_station_database()
        self.key('Tab')
        self.assertEqual(self.key('Tab'), 'Cancel.')
        self.assertTrue(self.key('Space').startswith('Canceled. '))
        self.assertIsNone(companion.MEDIA_NAV.form)

    def test_list_keys_in_a_form_say_the_form_is_open(self):
        self.open_station_database()
        for name in ('Ctrl+D', 'Ctrl+F', 'Ctrl+Shift+P', 'F5', 'Delete', 'Space'):
            with self.subTest(key=name):
                self.assertEqual(self.key(name), FORM_OPEN)
                self.assertIsNotNone(companion.MEDIA_NAV.form)

    def test_player_keys_still_control_the_audio_in_a_form(self):
        self.say('Media', 'Radio', 'Play WGN')
        nav = companion.media_navigation()
        nav.keyboard('Escape')
        nav.keyboard('Escape')               # the full radio menu
        for _ in range(5):
            self.key('Down')
        self.key('Enter')                     # Station database form
        self.assertEqual(self.key('Ctrl+S'), 'Audio stopped.')
        self.assertEqual(self.key('Ctrl+R'), 'Playing audio.')
        self.assertIsNotNone(companion.MEDIA_NAV.form)


class EmptyPresetsKeepTheRadioMenuTests(ExpertMediaTestCase):
    """Control+Shift+P with no presets, Delete, then Tab, offered "Station actions": Add to
    favorites and Record current station, with no station chosen or playing."""

    def test_tab_from_an_empty_preset_list_goes_to_the_radio_menu(self):
        self.say('Media')
        self.key('Enter')
        self.assertEqual(self.key('Ctrl+Shift+P'), 'No radio presets yet. Select a station and say save preset.')
        self.assertEqual(self.key('Delete'), 'No radio presets yet. Select a station and say save preset.')
        self.assertEqual(self.key('Tab'), 'Actions. Search stations (S), 1 of 22.')

    def test_escape_from_an_empty_preset_list_says_the_radio_menu(self):
        self.say('Media')
        self.key('Enter')
        self.key('Ctrl+Shift+P')
        self.key('Delete')
        self.assertEqual(self.key('Escape'), 'Search stations (S), 1 of 22.')
        self.assertEqual(self.key('Escape'), 'Media menu. Radio (R), 1 of 4.')

    def test_saved_presets_still_get_the_station_actions(self):
        self.say('Media', 'Radio', 'Play WGN', 'Save preset as News', 'Stop')
        self.hub.player.close()
        self.hub.current_station = None
        self.key('Ctrl+Shift+P')
        self.assertEqual(self.key('Tab'), 'Actions. Add to favorites (A), 1 of 7.')


class StationListRefreshWordsTests(ExpertMediaTestCase):
    """F5 in Radio said "IPRD refresh failed. The last saved catalog remains available;
    Radio Browser still searches live." and, after a good refresh, "1 stations"."""

    def test_a_failed_refresh_says_what_to_do(self):
        def offline(url):
            raise OSError('offline')
        self.hub.fetch_json = offline
        self.say('Media')
        self.key('Enter')
        self.assertEqual(self.key('F5'), 'The IPRD station list could not be refreshed. Check the internet connection, '
                                         'then press F5 to try again. Your saved stations and Radio Browser searches still work.')

    def test_one_station_is_one_station(self):
        self.hub.fetch_json = lambda url: {'stations': [{'name': 'IPRD One', 'streams': [{'url': 'https://radio.test/i'}]}]}
        self.say('Media')
        self.key('Enter')
        self.assertEqual(self.key('F5'), 'The IPRD station list is refreshed. It has 1 station. Radio Browser is always searched live.')


if __name__ == '__main__':
    unittest.main()


import test_media_player_menu  # noqa: E402  (its names are not imported, so its tests do not run twice)


class LevelPlayer(test_media_player_menu.PlayerLikeMediaPlayer):
    """Keeps its volume from 0 to 1, as media_player.MediaPlayer does."""
    volume = .5

    def adjust(self, setting, value):
        if setting == 'volume':
            self.volume = max(0.0, min(1.0, round(self.volume + value, 2)))
            return self.volume
        return value


class MediaPlayerVolumeEdgeTests(unittest.TestCase):
    """Up Arrow at the loudest said "Volume 100 percent." again, and Down Arrow at silence
    "Volume 0 percent.", as if they had changed. Radio and Podcasts say that it is the
    loudest, or that the audio is silent."""
    # The media player tests' setup, without running their tests again here.
    setUp = test_media_player_menu.MediaPlayerMenuTests.setUp
    key = test_media_player_menu.MediaPlayerMenuTests.key

    def test_up_and_down_at_the_ends_say_so(self):
        self.player = LevelPlayer()
        companion.MEDIA_HUB.player = self.player
        mode = companion.handle('media player', 'awake')
        mode = companion.task_navigation().selected_file(self.song)
        for _ in range(5):
            mode = self.key('Up', mode)
        self.said.clear()
        self.key('Up', mode)
        self.assertEqual(self.said, ['Loudest. Volume 100 percent.'])
        for _ in range(10):
            mode = self.key('Down', mode)
        self.said.clear()
        self.key('Down', mode)
        self.assertEqual(self.said, ['Volume 0 percent. The audio is silent.'])
        self.said.clear()
        self.key('Up', mode)
        self.assertEqual(self.said, ['Volume 10 percent.'])


import test_youtube  # noqa: E402  (its names are not imported, so its tests do not run twice)


class YouTubePlayerKeysAreNeverSilentTests(unittest.TestCase):
    """In the YouTube player, End, Page Down and Page Up said nothing at all. The arrows,
    Space and Home control the video there, so say that, and how to get back to the list."""
    setUp = test_youtube.NoBrowser.setUp
    press = test_youtube.NoBrowser.press

    def test_list_keys_in_the_player_say_what_the_keys_do(self):
        import youtube_screen
        youtube_screen.screen(self.app).push_player()
        for name in ('End', 'Next', 'Prior'):
            with self.subTest(key=name):
                self.said.clear()
                self.assertEqual(self.press(name), 'youtube')
                self.assertEqual(self.said, ['In the player, the arrows change the volume and skip. '
                                             'Space plays or pauses. Escape goes back to the list.'])
