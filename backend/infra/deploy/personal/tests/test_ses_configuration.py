import importlib.util
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('configure_ses', BASE / 'configure_ses.py')
ses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ses)


class SesConfiguration(unittest.TestCase):
    def test_log_mode_is_usable_while_awaiting_production_approval(self):
        text = 'NOTIFICATION_AWS_ACCESS_KEY_ID=AKIA' + 'A' * 16 + '\nNOTIFICATION_AWS_SECRET_ACCESS_KEY=' + 'a' * 40 + '\nNOTIFICATION_MAIL_PROVIDER=log\n'
        self.assertEqual(ses.credentials(text)['NOTIFICATION_MAIL_PROVIDER'], 'log')

    def test_unknown_provider_and_invalid_credentials_fail_without_echoing(self):
        for text in ('NOTIFICATION_MAIL_PROVIDER=anything', 'NOTIFICATION_AWS_ACCESS_KEY_ID=${OTHER_SECRET}'):
            with self.assertRaises(ValueError) as failure:
                ses.credentials(text)
            self.assertNotIn('OTHER_SECRET', str(failure.exception))
