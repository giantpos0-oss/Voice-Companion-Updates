"""Will, November 4, 2026: choosing the voice belongs in Voice options, not Synthesizer options,
and Up Arrow raises speech rate, pitch and volume, as in a screen reader's settings."""
import unittest

from settings_model import DEFAULTS, SettingsSession, fields

CONTEXT = {'engines': ('SAPI', 'espeak', 'ai'), 'windows_voices': ('Microsoft David', 'Microsoft Zira'),
           'espeak_voices': ('English (America)',), 'ai_voices': ('coral', 'alloy')}


def keys(category, context):
    return [f.key for f in fields(category, context)]


class VoiceOptionsLayoutTests(unittest.TestCase):
    def test_the_voice_for_your_synthesizer_comes_first_in_voice_options(self):
        for engine, key in (('SAPI', 'windows_voice'), ('windows', 'windows_voice'), ('espeak', 'espeak_voice'), ('ai', 'ai_voice')):
            with self.subTest(engine=engine):
                context = CONTEXT | {'engine': engine}
                self.assertEqual(keys('Voice options', context)[:4], [key, 'rate', 'pitch', 'volume'])
                for other in {'windows_voice', 'espeak_voice', 'ai_voice'} - {key}:
                    self.assertNotIn(other, keys('Voice options', context))
                synthesizer = keys('Synthesizer options', context)
                self.assertEqual(synthesizer[0], 'engine')
                self.assertFalse({'windows_voice', 'espeak_voice', 'ai_voice'} & set(synthesizer))

    def test_changing_the_synthesizer_changes_the_voice_list(self):
        session = SettingsSession(DEFAULTS | {'engine': 'SAPI', 'windows_voice': 'Microsoft David'}, dict(CONTEXT))
        self.assertEqual(session.current_fields()[0].key if session.category_name() == 'Voice options' else
                         fields('Voice options', session.context)[0].key, 'windows_voice')
        session.set('engine', 'espeak')
        self.assertEqual(fields('Voice options', session.context)[0].key, 'espeak_voice')

    def test_spoken_voice_commands_still_work_for_any_synthesizer(self):
        session = SettingsSession(DEFAULTS | {'engine': 'SAPI', 'windows_voice': 'Microsoft David'}, dict(CONTEXT))
        self.assertEqual(session.voice_setting('set AI voice to alloy'), ('ai_voice', 'alloy'))
        session.set('ai_voice', 'alloy')
        self.assertEqual(session.values['ai_voice'], 'alloy')
        self.assertEqual(session.voice_setting('SAPI voice Microsoft Zira'), ('windows_voice', 'Microsoft Zira'))

    def test_up_arrow_raises_rate_pitch_and_volume(self):
        # The combo boxes move to the item above on Up Arrow: the highest value is listed first.
        voice = {f.key: f.choices for f in fields('Voice options', CONTEXT)}
        for key, top, bottom in (('rate', '10', '-10'), ('pitch', '10', '-10'), ('volume', '100', '0')):
            with self.subTest(key=key):
                self.assertEqual((voice[key][0], voice[key][-1]), (top, bottom))
                values = [int(v) for v in voice[key]]
                self.assertEqual(values, sorted(values, reverse=True))


if __name__ == '__main__':
    unittest.main()
