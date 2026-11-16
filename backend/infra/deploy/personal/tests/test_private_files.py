"""Local permission initialization must complete before secret content is written."""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audited_private_files', BASE / 'private_files.py')
private = importlib.util.module_from_spec(spec)
spec.loader.exec_module(private)


class PrivateFiles(unittest.TestCase):
    def test_windows_creation_receives_the_owner_before_any_content_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'synthetic.env'
            def create(path, sid):
                self.assertFalse(path.exists())
                self.assertEqual(sid, 'S-1-5-21-1234')
                return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)

            identity = SimpleNamespace(stdout='"synthetic-user","S-1-5-21-1234"\n')
            with patch.object(private, '_windows', return_value=True), \
                    patch.object(private.subprocess, 'run', return_value=identity), \
                    patch.object(private, '_create_windows_file', side_effect=create):
                private.write_private_file(target, 'SYNTHETIC=example\n')
            self.assertEqual(target.read_text(), 'SYNTHETIC=example\n')

    def test_acl_failure_removes_empty_file_and_never_writes_content(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'synthetic.env'
            identity = SimpleNamespace(stdout='"synthetic-user","S-1-5-21-1234"\n')
            with patch.object(private, '_windows', return_value=True), \
                    patch.object(private.subprocess, 'run', return_value=identity), \
                    patch.object(private, '_create_windows_file', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    private.write_private_file(target, 'SYNTHETIC=example\n')
            self.assertFalse(target.exists())

    def test_existing_file_is_never_replaced_or_repermissioned(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'synthetic.env'
            target.write_text('existing')
            with patch.object(private, '_windows', return_value=False), patch.object(private.subprocess, 'run') as command:
                with self.assertRaises(FileExistsError):
                    private.write_private_file(target, 'replacement')
                command.assert_not_called()
            self.assertEqual(target.read_text(), 'existing')

    @unittest.skipUnless(os.name == 'nt', 'Windows native DACL creation')
    def test_native_creation_has_a_protected_dacl(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'synthetic.env'
            private.write_private_file(target, 'SYNTHETIC=example\n')
            shell = shutil.which('pwsh') or shutil.which('powershell')
            result = subprocess.run([shell, '-NoProfile', '-Command',
                                     '(Get-Acl -LiteralPath $env:PRIVATE_PROBE_PATH).AreAccessRulesProtected'],
                                    env=dict(os.environ, PRIVATE_PROBE_PATH=str(target)),
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'True')
            self.assertEqual(target.read_text(), 'SYNTHETIC=example\n')

    @unittest.skipIf(os.name == 'nt', 'POSIX mode semantics')
    def test_posix_file_is_private_from_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'synthetic.env'
            private.write_private_file(target, 'SYNTHETIC=example\n')
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
