import base64
import importlib.util
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('configure_push', BASE / 'configure_push.py')
push = importlib.util.module_from_spec(spec)
spec.loader.exec_module(push)


class PushConfiguration(unittest.TestCase):
    def test_manifest_keeps_mail_settings_and_private_key_out_of_api(self):
        source = 'services:\n  api:\n    environment:\n      FRONTEND_URL: ${FRONTEND_URL}\n  notification:\n    environment:\n      NOTIFICATION_MAIL_PROVIDER: ${NOTIFICATION_MAIL_PROVIDER:-log}\n      NOTIFICATION_PUSH_PROVIDER: log\n  postgres:\n    image: postgres\n'
        result = push.manifest_settings(source)
        api, notification = result.split('  notification:\n')
        self.assertNotIn('PUSH_VAPID_PRIVATE_KEY', api)
        self.assertIn('PUSH_VAPID_PRIVATE_KEY', notification)
        self.assertIn('NOTIFICATION_MAIL_PROVIDER: ${NOTIFICATION_MAIL_PROVIDER:-log}', notification)
        self.assertEqual(push.manifest_settings(result), result)

    def test_key_formats_are_checked_without_exposing_values(self):
        public = base64.urlsafe_b64encode(b'\x04' + b'\x01' * 64).decode().rstrip('=')
        private = base64.urlsafe_b64encode(b'\x02' * 32).decode().rstrip('=')
        text = f'{push.PUBLIC}={public}\n{push.PRIVATE}={private}\n{push.SUBJECT}=mailto:contact@mujuthaek.store\n'
        self.assertEqual(push.credentials(text)[push.PUBLIC], public)
        for invalid in (text + f'{push.PRIVATE}={private}\n', text.replace(private, 'bad-secret'), text.replace('contact@', 'unexpected@')):
            with self.assertRaises(ValueError) as failure:
                push.credentials(invalid)
            self.assertNotIn(private, str(failure.exception))
