import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_upload import upload_backup


class BackupEncryptionActivation(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        (self.base / 'runtime/backups').mkdir(parents=True)
        self.source = self.base / 'runtime/backups/synthetic.dump'
        self.source.write_bytes(b'synthetic plaintext')
        (self.base / '.env').write_text('S3_BUCKET=example-bucket\n')
        (self.base / 'runtime/backup-aws.env').write_text('BACKUP_IDENTITY_ARN=arn:aws:iam::123456789012:user/mujuthaek-personal-backup\n')
        (self.base / 'runtime/backup-recipient.pem').write_bytes(b'synthetic certificate')
        self.marker = self.base / 'runtime/backup-encryption.json'
        self.marker.write_text(json.dumps({'format': 'cms-aes256gcm-rsa-oaep-sha256-v1',
            'certificate_sha256': hashlib.sha256(b'synthetic certificate').hexdigest()}))
        self.marker.chmod(0o600)

    def encrypt(self, source, destination, certificate):
        destination.write_bytes(b'synthetic ciphertext')

    def test_only_ciphertext_uploaded_plaintext_removed_after_success(self):
        with patch('backup_crypto.transform', side_effect=self.encrypt), patch('backup_upload.subprocess.run') as run:
            upload_backup(self.base, self.source)
        command = run.call_args.args[0]
        self.assertIn('backups/synthetic.dump.cms', command)
        self.assertFalse(self.source.exists())
        self.assertTrue(self.source.with_suffix('.dump.cms').exists())

    def test_failed_upload_preserves_plaintext_for_recovery(self):
        with patch('backup_crypto.transform', side_effect=self.encrypt), patch('backup_upload.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'docker')):
            with self.assertRaises(subprocess.CalledProcessError):
                upload_backup(self.base, self.source)
        self.assertTrue(self.source.exists())

    def test_changed_recipient_never_uploads_plaintext(self):
        (self.base / 'runtime/backup-recipient.pem').write_bytes(b'different certificate')
        with patch('backup_upload.subprocess.run') as run:
            with self.assertRaises(RuntimeError):
                upload_backup(self.base, self.source)
        run.assert_not_called()
        self.assertTrue(self.source.exists())
