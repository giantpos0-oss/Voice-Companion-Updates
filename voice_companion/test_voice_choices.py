import unittest
from unittest.mock import Mock,patch
import companion

class VoiceChoicesTests(unittest.TestCase):
    def setUp(self):
        self.speech=Mock()
        self.token=Mock()
        self.token.GetDescription.return_value='Windows voice'
        self.speech.Voice=self.token
        self.speech.GetVoices.return_value=Mock(Count=1,Item=lambda i:self.token)
        self.ai=Mock(enabled=False)
        self.patches=[patch.object(companion,'voice',self.speech,create=True),
            patch.object(companion,'AI_SPEECH',self.ai),patch.object(companion,'TEXT_MODE',False),
            patch.object(companion,'AI_VOICE_NAME','coral'),patch.object(companion,'VOICE_PICK_INDEX',None),
            patch.object(companion,'VOICE_PICK_ORIGINAL',None),patch.object(companion,'SYNTH_PICK_INDEX',None),
            patch.object(companion,'VOICE_PICK_ENGINE',None),patch.object(companion,'ESPEAK_SPEECH',None),patch.object(companion,'VOICE_PICK_CONFIRM',False),
            patch.object(companion,'save_speech_settings')]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def test_ai_preview_select_and_save_through_existing_commands(self):
        companion.handle('list voices','awake')
        self.assertFalse(self.ai.enabled)
        companion.handle('next','awake')
        companion.handle('okay','awake')
        self.assertTrue(self.ai.enabled)
        self.assertEqual(companion.AI_VOICE_NAME,'alloy')
        self.assertIn('AI voice Alloy',self.ai.speak.call_args.args[0])
        companion.save_speech_settings.assert_not_called()
        companion.handle('okay','awake')
        companion.save_speech_settings.assert_called_once()
        self.assertIsNone(companion.VOICE_PICK_INDEX)

    def test_cancel_restores_previous_ai_voice(self):
        self.ai.enabled=True
        companion.handle('list voices','awake')
        self.assertTrue(self.ai.enabled)
        companion.handle('okay','awake')
        self.assertFalse(self.ai.enabled)
        companion.handle('next voice','awake')
        companion.handle('cancel voice','awake')
        self.assertTrue(self.ai.enabled)
        self.assertEqual(companion.AI_VOICE_NAME,'coral')
        companion.save_speech_settings.assert_not_called()

    def test_unconfigured_ai_is_not_in_list(self):
        with patch.object(companion,'AI_SPEECH',None):
            self.assertEqual(len(companion.voice_choices()),1)

    def test_picker_stays_available_in_radio_mode(self):
        companion.handle('list voices','media')
        companion.handle('next','media')
        companion.handle('that one','media')
        self.assertTrue(self.ai.enabled)
        companion.handle('okay','media')
        companion.save_speech_settings.assert_called_once()

    def test_switching_by_windows_name_disables_ai(self):
        self.ai.enabled=True
        companion.handle('use voice Windows voice','awake')
        self.assertFalse(self.ai.enabled)


class VoiceCheckTests(unittest.TestCase):
    """"Voice check" starts the 32-bit voice helper, which can take seconds. It must never
    hold Companion's window or keys: the report runs in the background."""
    def test_voice_check_answers_at_once_and_says_the_result_when_ready(self):
        import queue,threading,time,tempfile
        from pathlib import Path
        release=threading.Event();self.addCleanup(release.set)
        def slow_report(voice,path):
            release.wait(10);return ['Microsoft David','VW Paul'],path
        notices=queue.Queue()
        with tempfile.TemporaryDirectory() as folder,patch.object(companion,'TEXT_MODE',False),patch.object(companion,'voice',Mock(),create=True),\
                patch.object(companion,'APP',Path(folder)),patch.object(companion,'MEDIA_NOTICES',notices),\
                patch.object(companion,'VOICE_CHECK',None),patch.object(companion,'speak') as speech,patch('voice_inventory.report',slow_report):
            started=time.monotonic()
            companion.handle('voice check','awake')
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual(speech.call_args.args[0],'Checking voices. This can take a few seconds.')
            companion.handle('voice check','awake')
            self.assertEqual(speech.call_args.args[0],'The voice check is still running.')
            self.assertTrue(notices.empty())
            release.set()
            result=notices.get(timeout=5)
            self.assertEqual(result,'2 usable SAPI 5 voices found. A voice check was saved in your Voice Companion data folder. '
                             'Ask your helper to open voice-check.txt there for details.')
            companion.VOICE_CHECK.join(5)
            companion.handle('voice check','awake')
            self.assertEqual(speech.call_args.args[0],'Checking voices. This can take a few seconds.')
            release.set();notices.get(timeout=5);companion.VOICE_CHECK.join(5)

    def test_voice_check_that_cannot_save_says_why(self):
        import queue,tempfile
        from pathlib import Path
        notices=queue.Queue()
        with tempfile.TemporaryDirectory() as folder,patch.object(companion,'TEXT_MODE',False),patch.object(companion,'voice',Mock(),create=True),\
                patch.object(companion,'APP',Path(folder)),patch.object(companion,'MEDIA_NOTICES',notices),\
                patch.object(companion,'VOICE_CHECK',None),patch.object(companion,'speak'),\
                patch('voice_inventory.report',side_effect=OSError('Access is denied')):
            companion.handle('voice check','awake')
            self.assertEqual(notices.get(timeout=5),'Voice check could not be saved: Access is denied')

