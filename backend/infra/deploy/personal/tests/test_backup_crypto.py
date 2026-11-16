import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_crypto import transform

OPENSSL = shutil.which('openssl')
if not OPENSSL and Path('C:/Program Files/Git/usr/bin/openssl.exe').is_file():
    OPENSSL = 'C:/Program Files/Git/usr/bin/openssl.exe'


@unittest.skipUnless(OPENSSL, 'OpenSSL unavailable')
class BackupCrypto(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='synthetic-backup-crypto-')
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.source, self.output, self.restored = [root / name for name in ('synthetic.dump', 'synthetic.cms', 'restored.dump')]
        self.key, self.cert = root / 'synthetic.key', root / 'synthetic.pem'
        subprocess.run([OPENSSL, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=synthetic-backup-test', '-keyout', str(self.key), '-out', str(self.cert)],
                       capture_output=True, check=True)
        self.source.write_bytes(b'PGDMP' + b'public synthetic test\n' * 1000)

    def test_streaming_authenticated_roundtrip(self):
        transform(self.source, self.output, self.cert, openssl=OPENSSL)
        transform(self.output, self.restored, self.cert, private_key=self.key, openssl=OPENSSL)
        self.assertEqual(self.source.read_bytes(), self.restored.read_bytes())

    def test_corruption_is_rejected_without_leaving_plaintext(self):
        transform(self.source, self.output, self.cert, openssl=OPENSSL)
        data = bytearray(self.output.read_bytes())
        data[-6] ^= 1
        self.output.write_bytes(data)
        with self.assertRaises(RuntimeError):
            transform(self.output, self.restored, self.cert, private_key=self.key, openssl=OPENSSL)
        self.assertFalse(self.restored.exists())

    def test_existing_destination_and_empty_recovery_key_fail_closed(self):
        self.restored.write_bytes(b'keep existing output')
        with self.assertRaises(FileExistsError):
            transform(self.source, self.restored, self.cert, openssl=OPENSSL)
        self.assertEqual(self.restored.read_bytes(), b'keep existing output')
        with self.assertRaises(ValueError):
            transform(self.source, self.output, self.cert, private_key='', openssl=OPENSSL)
