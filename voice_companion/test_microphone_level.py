"""Microphone level (Will, November 12, 2026): Windows set his Jabra Evolve microphone to
19 percent, and Companion missed words until he raised it to about 70 in Sound settings.

Companion now raises the default microphone to the level chosen in Options while it
listens. It is not automatic gain: the level is set once to exactly the chosen value, a
higher level is never lowered, and a muted microphone is never unmuted.
The Windows microphone is faked at its boundary: a level from 0.0 to 1.0 and a mute flag.
"""
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import microphone_level
from microphone_level import MicrophoneKeeper, OFF, LEVEL_CHOICES, DEFAULT_LEVEL, short_name, spoken_level, target


class FakeMicrophone:
    def __init__(self, name='Headset Microphone (Jabra Evolve 65)', level=0.19, muted=False):
        self.name, self.level, self.muted = name, level, muted
        self.sets = []
        self.broken = False

    def default(self):
        if self.broken:
            raise OSError('No microphone is plugged in.')
        return self.name, self.level, self.muted

    def set_level(self, value):
        self.sets.append(value); self.level = value


class KeeperTests(unittest.TestCase):
    def setUp(self):
        self.mic = FakeMicrophone()
        self.choice = DEFAULT_LEVEL
        self.said, self.logged = [], []
        self.keeper = MicrophoneKeeper(lambda: self.mic, choice=lambda: self.choice,
                                       notify=self.said.append, log=self.logged.append)

    def test_a_low_headset_microphone_is_raised_to_the_chosen_level_and_said_once(self):
        self.keeper.check()
        self.assertEqual(self.mic.level, 0.7)
        self.assertEqual(self.said, ['Jabra Evolve 65 microphone was at 19 percent, so Voice Companion raised it to 70 percent.'])
        # Windows lowers it again (the headset reconnects): raised again, quietly.
        self.mic.level = 0.19
        self.keeper.check()
        self.assertEqual(self.mic.level, 0.7)
        self.assertEqual(len(self.said), 1)

    def test_a_higher_level_is_never_lowered(self):
        self.mic.level = 0.9
        self.keeper.check()
        self.assertEqual(self.mic.sets, [])
        self.assertEqual(self.said, [])

    def test_it_is_set_once_to_exactly_the_choice_not_adjusted_to_the_voice(self):
        for _ in range(5):
            self.keeper.check()
        self.assertEqual(self.mic.sets, [0.7])

    def test_leave_as_windows_has_it_changes_nothing(self):
        self.choice = OFF
        self.keeper.check()
        self.assertEqual((self.mic.sets, self.said), ([], []))

    def test_a_muted_microphone_is_never_unmuted_but_the_person_is_told(self):
        self.mic.level, self.mic.muted = 0.8, True
        self.keeper.check(); self.keeper.check()
        self.assertEqual(self.said, ['Jabra Evolve 65 microphone is muted in Windows or on the headset. '
                                     'Unmute it so Voice Companion can hear you.'])
        self.assertTrue(self.mic.muted)
        self.mic.muted = False; self.keeper.check()
        self.mic.muted = True; self.keeper.check()
        self.assertEqual(len(self.said), 2, 'Muted again later: said again.')

    def test_low_and_muted_are_said_in_one_message(self):
        self.mic.muted = True
        self.keeper.check()
        self.assertEqual(len(self.said), 1)
        self.assertIn('raised it to 70 percent', self.said[0])
        self.assertIn('is muted', self.said[0])

    def test_no_microphone_never_raises_and_is_logged_once(self):
        self.mic.broken = True
        self.assertIsNone(self.keeper.check()); self.keeper.check()
        self.assertEqual(len(self.logged), 1)
        self.assertIn('could not read', self.keeper.report())

    def test_the_report_names_the_device_and_its_level(self):
        self.mic.level = 0.55
        self.assertEqual(self.keeper.report(), 'Jabra Evolve 65 microphone is at 55 percent. '
                                               'Voice Companion raises it to at least 70 percent while it listens.')

    def test_it_checks_at_once_when_listening_starts_and_not_while_off(self):
        self.keeper.start()
        self.addCleanup(self.keeper.close)
        time.sleep(0.1)
        self.assertEqual(self.mic.sets, [], 'Nothing is changed while the microphone is off.')
        self.keeper.listening_changed(True)
        for _ in range(100):
            if self.mic.sets: break
            time.sleep(0.02)
        self.assertEqual(self.mic.sets, [0.7])


class ChoiceTests(unittest.TestCase):
    def test_spoken_levels(self):
        for said, choice in (('Seventy.', '70 percent'), ('80 percent', '80 percent'), ('100%', '100 percent'),
                             ('full', '100 percent'), ('off', OFF), ('Leave it as Windows has it.', OFF),
                             ('45', None), ('loud', None), ('', None)):
            self.assertEqual(spoken_level(said), choice, said)

    def test_targets(self):
        self.assertEqual(target('70 percent'), 0.7)
        self.assertIsNone(target(OFF))
        self.assertEqual(target('damaged value'), 0.7)

    def test_device_names_are_short(self):
        self.assertEqual(short_name('Headset Microphone (Jabra Evolve 65)'), 'Jabra Evolve 65 microphone')
        self.assertEqual(short_name('Microphone (2- Jabra Link 400)'), 'Jabra Link 400 microphone')
        self.assertEqual(short_name('USB Mic'), 'USB Mic')
        self.assertEqual(short_name(''), 'Your microphone')

    def test_the_option_is_in_input_options_with_a_default_of_70(self):
        from settings_model import DEFAULTS, SettingsSession, fields
        field = next(f for f in fields('Input options', {}) if f.key == 'microphone_level')
        self.assertEqual(field.choices, LEVEL_CHOICES)
        self.assertEqual(DEFAULTS['microphone_level'], '70 percent')
        session = SettingsSession({}, {})
        session.set('microphone_level', 'Eighty.')
        self.assertEqual(session.values['microphone_level'], '80 percent')


class CommandTests(unittest.TestCase):
    def setUp(self):
        import companion
        self.c = companion

    def test_spoken_commands(self):
        r = self.c.microphone_level_request
        self.assertEqual(r('microphone level'), ('report', None))
        self.assertEqual(r('what is my microphone level'), ('report', None))
        self.assertEqual(r('set the microphone level to 80 percent'), ('set', '80 percent'))
        self.assertEqual(r('mic volume seventy'), ('set', '70 percent'))
        self.assertEqual(r('microphone level 45'), ('set', None))
        self.assertIsNone(r('microphone off'))
        self.assertIsNone(r('microphone'))
        # On a command screen an unclear level is answered with the choices; in writing fields it is text.
        self.assertEqual(r('the microphone level was low yesterday'), ('set', None))

    def test_a_command_sets_and_saves_the_level(self):
        said = []
        with patch.object(self.c, 'speak', said.append), patch.object(self.c, 'save_preferences', lambda: None), \
             patch.dict(self.c.PREFERENCES, {'microphone_level': '70 percent'}):
            self.assertEqual(self.c.handle('Set the microphone level to 90 percent.', 'awake'), 'awake')
            self.assertEqual(self.c.PREFERENCES['microphone_level'], '90 percent')
        self.assertIn('never lowers it', said[-1])

    def test_while_writing_it_is_text(self):
        with patch.object(self.c, 'INPUT_MODE', 'mixed'), patch.object(self.c, 'document', object()):
            self.assertTrue(self.c.writing_dictation('document'))
        # The guard in _handle uses writing_dictation, so "Mic volume was low" in a document is a sentence.
        self.assertIn("mic_request=None if writing_dictation(mode,typed) else microphone_level_request(command)",
                      open(self.c.__file__, encoding='utf-8').read())


if __name__ == '__main__':
    unittest.main()
