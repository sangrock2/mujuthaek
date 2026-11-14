import importlib.util
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('configure_domain_tls', BASE / 'configure_domain_tls.py')
tls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tls)


class DomainTls(unittest.TestCase):
    def test_expansion_preserves_the_existing_ip_and_short_lived_renewal_profile(self):
        args = tls.issuance_args({'identifier': '3.34.67.209', 'cert_name': 'mujuthaek-prod', 'email': 'owner@example.com'})
        self.assertEqual(args[args.index('--ip-address') + 1], '3.34.67.209')
        self.assertEqual(args[args.index('-d') + 1], 'api.mujuthaek.store')
        self.assertEqual(args[args.index('--preferred-profile') + 1], 'shortlived')
        self.assertIn('--expand', args)

    def test_another_certificate_or_host_cannot_be_expanded(self):
        for identifier, name in [('192.0.2.1', 'mujuthaek-prod'), ('3.34.67.209', 'other-project')]:
            with self.assertRaises(ValueError):
                tls.issuance_args({'identifier': identifier, 'cert_name': name})
