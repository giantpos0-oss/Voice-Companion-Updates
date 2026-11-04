"""Empty and edge states in Radio, Podcasts and the player (nightly sweep, November 4, 2026).

No presets, no subscriptions, nothing playing, a number past the last result, odd files in
the recordings folder, a damaged subscriptions file, and a recording at midnight. These
drive the real app through companion.handle and the real media keys, with a real MediaHub."""
import json
import unittest
from datetime import datetime
from unittest.mock import patch

import companion
from test_media_new_veteran import NewVeteranMediaTestCase


class EdgeStateTestCase(NewVeteranMediaTestCase):
    def key(self, name):
        return companion.media_navigation().keyboard(name)


class NothingPlayingTests(EdgeStateTestCase):
    """With nothing loaded, a seek or chapter key said the audio "cannot seek" or the
    episode "does not provide chapter markers". Nothing is playing: say that."""

    def test_rewind_key_with_nothing_playing(self):
        self.say('Media', 'Podcasts')
        self.assertEqual(self.key('Ctrl+Left'), 'No audio is playing. Choose a station or episode first.')
        self.assertEqual(self.key('Ctrl+Right'), 'No audio is playing. Choose a station or episode first.')

    def test_spoken_rewind_with_nothing_playing(self):
        said = self.say('Media', 'Radio', 'Rewind 30 seconds')
        self.assertEqual(said, 'No audio is playing. Choose a station or episode first.')

    def test_next_chapter_with_nothing_playing(self):
        said = self.say('Media', 'Podcasts', 'Next chapter')
        self.assertEqual(said, 'No audio is playing. Choose an episode first.')
        self.assertEqual(self.hub.chapter('previous'), 'No audio is playing. Choose an episode first.')


class NoPresetsTests(EdgeStateTestCase):
    """Play preset and Delete preset with no presets said "I could not find that preset.
    Say list presets." and List presets then said there are none. Say it at once."""

    def test_play_preset_with_no_presets(self):
        said = self.say('Media', 'Radio', 'Play preset')
        self.assertEqual(said, 'No radio presets yet. Select a station and say save preset.')

    def test_delete_preset_key_with_no_presets(self):
        self.say('Media', 'Radio', 'List presets')
        self.assertEqual(self.key('Delete'), 'No radio presets yet. Select a station and say save preset.')

    def test_a_preset_name_that_is_not_saved_still_says_so(self):
        self.say('Media', 'Radio', 'Search radio', 'WGN', 'Save preset')
        said = self.say('Play preset Jazz')
        self.assertEqual(said, 'I could not find that preset. Say list presets.')


class StationNumberTests(EdgeStateTestCase):
    """A number past the last result said "I could not complete that media request. That
    station number is unavailable. Search radio again." The results are fine: say the range."""

    def test_play_a_number_past_the_last_station(self):
        self.say('Media', 'Radio', 'Search radio', 'WGN')
        count = len(self.hub.stations)
        said = self.say('Play station 9')
        self.assertEqual(said, 'There are only ' + str(count) + ' stations in these results. Say a number from 1 to ' + str(count) + '.')
        self.assertIsNone(self.hub.player.kind)

    def test_record_a_number_past_the_last_station(self):
        self.say('Media', 'Radio', 'Search radio', 'WGN')
        said = self.say('Record station 9')
        self.assertTrue(said.startswith('There are only '), said)
        self.assertIsNone(self.hub.recording)

    def test_record_a_station_number_before_any_search(self):
        said = self.say('Media', 'Radio', 'Record station 2')
        self.assertEqual(said, 'Search for stations first.')


class EmptyListTests(EdgeStateTestCase):
    """An empty list says what to do next, as every spoken message should."""

    def test_no_subscriptions(self):
        said = self.say('Media', 'Podcasts', 'List subscriptions')
        self.assertEqual(said, 'No podcast subscriptions yet. To add one, search or browse podcasts, '
                               'choose a show, and say subscribe.')

    def test_no_downloads(self):
        said = self.say('Media', 'Podcasts', 'List downloads')
        self.assertEqual(said, 'No downloaded episodes yet. Open a podcast, choose an episode, '
                               'and say download this episode.')

    def test_no_recordings(self):
        said = self.say('Media', 'Radio', 'List recordings')
        self.assertEqual(said, 'No radio recordings yet. Choose a station and say record radio.')

    def test_download_with_no_episode_open(self):
        said = self.say('Media', 'Podcasts', 'Download this episode')
        self.assertEqual(said, 'Open a podcast and choose an episode first. Then say download this episode.')


class RecordingsFolderTests(EdgeStateTestCase):
    """Windows can put desktop.ini or Thumbs.db in a folder. They were listed and
    "played" as radio recordings. Only sound files are recordings. The spoken list
    also said ".mp3" while the keys did not."""

    def setUp(self):
        super().setUp()
        folder = self.hub.folder / 'Radio Recordings'
        folder.mkdir(parents=True)
        (folder / 'desktop.ini').write_text('[.ShellClassInfo]', encoding='utf-8')
        (folder / 'Thumbs.db').write_bytes(b'x')
        (folder / 'WGN 2026-11-04 20-00-00.mp3').write_bytes(b'ID3')

    def test_only_sound_files_are_listed_and_played(self):
        said = self.say('Media', 'Radio', 'List recordings')
        self.assertEqual(said, 'Recordings: 1. WGN 2026-11-04 20-00-00')
        said = self.say('Play recording 1')
        self.assertEqual(said, 'Playing recording WGN 2026-11-04 20-00-00. Say pause audio or stop audio.')
        self.assertEqual(self.say('Play recording 2'), 'That recording number is unavailable.')

    def test_keys_list_the_same_recordings(self):
        self.say('Media', 'Radio', 'List saved recordings')
        names = [item['title'] for item in companion.media_navigation().items()]
        self.assertEqual(names, ['WGN 2026-11-04 20-00-00'])


class DamagedDownloadLimitTests(EdgeStateTestCase):
    """A damaged automatic download setting was read out as "[1]", and stopped the
    background check of every feed ("Podcast feeds could not be checked")."""

    def setUp(self):
        super().setUp()
        self.hub.folder.mkdir(parents=True, exist_ok=True)
        (self.hub.folder / 'podcast-subscriptions.json').write_text(json.dumps(
            [{'name': 'History Hour', 'feed': 'https://pod.test/h', 'episodes': [], 'download_limit': [1]},
             {'name': 'Science Now', 'feed': 'https://pod.test/s', 'episodes': [], 'download_limit': 'ten'}]),
            encoding='utf-8')

    def test_a_damaged_limit_is_said_as_manual(self):
        said = self.say('Media', 'Podcasts', 'List subscriptions')
        self.assertIn('Subscription 1: History Hour, automatic downloads manual.', said)

    def test_feeds_still_refresh(self):
        notices = []
        self.hub.notify = notices.append
        self.hub._auto_download = lambda *args: self.fail('a damaged limit must not download')
        self.assertEqual(self.hub.refresh_subscriptions(), 'Checked 2 of 2 subscribed podcast feeds.')
        self.assertFalse([n for n in notices if 'could not' in n], notices)


class SubscribeTwiceTests(EdgeStateTestCase):
    """Subscribe on a show you already have said "Subscribed to" again, as if it were new."""

    def test_subscribing_again_says_you_already_are(self):
        self.say('Media', 'Podcasts', 'Search podcasts for history')
        self.assertTrue(self.say('Subscribe').startswith('Subscribed to History Hour.'))
        said = self.say('Subscribe')
        self.assertEqual(said, 'You are already subscribed to History Hour. Say list subscriptions to hear them.')
        saved = json.loads((self.hub.folder / 'podcast-subscriptions.json').read_text(encoding='utf-8'))
        self.assertEqual([s['name'] for s in saved], ['History Hour'])


class PlayerControlsReturnTests(EdgeStateTestCase):
    """Player controls named the wrong place for Escape after a saved recording."""

    def test_escape_names_the_recordings(self):
        folder = self.hub.folder / 'Radio Recordings'
        folder.mkdir(parents=True)
        (folder / 'WGN.mp3').write_bytes(b'ID3')
        self.say('Media', 'Radio', 'List saved recordings')
        self.key('Enter')
        said = self.say('Player controls')
        self.assertTrue(said.endswith('Escape goes back to the recordings.'), said)
        self.assertEqual(self.key('Escape'), 'WGN (W), 1 of 1.')


class MidnightTests(EdgeStateTestCase):
    """At night, "today at 12 AM" has passed. Midnight tonight is 12 AM tomorrow: say so."""

    def setUp(self):
        super().setUp()
        self.hub.clock = lambda: datetime(2026, 11, 4, 22, 15)

    def test_spoken_today_at_midnight(self):
        self.say('Media', 'Radio', 'Search radio', 'WGN')
        said = self.say('Schedule station 1 today at 12 AM for 30 minutes')
        self.assertEqual(said, '12 AM today has passed. For midnight tonight, say tomorrow at 12 AM.')
        said = self.say('Schedule station 1 tomorrow at 12 AM for 30 minutes')
        self.assertEqual(said, 'Scheduled WGN Radio 720 for Thursday, November 5 at twelve AM for 30 minutes. '
                               'Keep Voice Companion running and the computer awake.')

    def test_schedule_form_today_at_midnight(self):
        self.say('Media', 'Radio', 'Search radio', 'WGN')
        nav = companion.media_navigation()
        nav.open_form('schedule')
        nav.form['fields'][0]['value'] = 'today'
        nav.form['fields'][1]['value'] = '12 AM'
        self.assertEqual(nav.submit_form(), '12 AM today has passed. For midnight tonight, choose tomorrow and 12 AM.')
        self.assertIsNotNone(nav.form)



class QuestionKeyTests(EdgeStateTestCase):
    """In a Yes or No question on Radio or Podcasts, Space said nothing, while on every
    other screen it answers like Enter. Other keys said nothing either."""

    def setUp(self):
        super().setUp()
        self.say('Media', 'Radio', 'Search radio', 'WGN', 'Save preset', 'List presets')
        self.assertTrue(self.key('Delete').startswith('Delete preset '))

    def test_space_answers_like_enter(self):
        self.assertEqual(self.key('Up'), 'Yes.')
        self.assertTrue(self.key('Space').startswith('Deleted preset '))
        self.assertEqual(self.hub.presets(), [])

    def test_other_keys_ask_again(self):
        self.assertEqual(self.key('F5'), 'Yes or no?')
        self.assertEqual(self.key('Delete'), 'Yes or no?')
        self.assertEqual(len(self.hub.presets()), 1)


if __name__ == '__main__':
    unittest.main()
