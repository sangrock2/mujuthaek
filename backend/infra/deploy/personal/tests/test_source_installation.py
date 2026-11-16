import hashlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_reviewed_source as installer


class SourceInstallation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='synthetic-source-install-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'source'
        self.base = self.root / 'backend/infra/deploy/personal'
        (self.base / 'runtime').mkdir(parents=True)
        (self.base / 'nginx').mkdir()
        self.config = self.base / 'nginx/default.conf'
        self.config.write_bytes(b'old gateway')
        self.secret = self.base / '.env'
        self.secret.write_bytes(b'synthetic private configuration')
        self.archive = Path(temporary.name) / 'reviewed.tar.gz'

    def package(self, files):
        with tarfile.open(self.archive, 'w:gz') as archive:
            for name, body in files.items():
                item = tarfile.TarInfo(name)
                item.size = len(body)
                archive.addfile(item, io.BytesIO(body))

    def run_install(self, fail=False, active=True):
        validations = 0
        def command(*args):
            nonlocal validations
            if args[-1] == '-t':
                validations += 1
                if fail and validations == 1:
                    raise RuntimeError('synthetic nginx validation failure')
            return ''
        with ExitStack() as stack:
            for key, value in [('ROOT', self.root), ('BASE', self.base), ('ARCHIVE', self.archive),
                               ('EXPECTED', hashlib.sha256(self.archive.read_bytes()).hexdigest())]:
                stack.enter_context(patch.object(installer, key, value))
            stack.enter_context(patch.object(os, 'name', 'posix'))
            stack.enter_context(patch.object(os, 'geteuid', return_value=0, create=True))
            stack.enter_context(patch.object(installer.subprocess, 'run', side_effect=lambda args: SimpleNamespace(
                returncode=0 if args[-1].endswith('.timer') and active else 1)))
            mock = stack.enter_context(patch.object(installer, 'run', side_effect=command))
            with redirect_stdout(io.StringIO()):
                installer.main()
            return mock

    def test_failed_reload_restores_public_files_removes_added_files_and_preserves_secrets(self):
        self.package({'backend/infra/deploy/personal/nginx/default.conf': b'new invalid gateway', 'backend/new.py': b'new'})
        with self.assertRaisesRegex(RuntimeError, 'synthetic nginx'):
            self.run_install(fail=True)
        self.assertEqual(self.config.read_bytes(), b'old gateway')
        self.assertFalse((self.root / 'backend/new.py').exists())
        self.assertEqual(self.secret.read_bytes(), b'synthetic private configuration')

    def test_success_normalizes_shells_and_does_not_enable_an_inactive_timer(self):
        self.package({'backend/script.sh': b'#!/bin/sh\r\nexit 0\r\n'})
        commands = self.run_install(active=False)
        self.assertEqual((self.root / 'backend/script.sh').read_bytes(), b'#!/bin/sh\nexit 0\n')
        self.assertFalse(any(call.args[:2] == ('systemctl', 'start') for call in commands.call_args_list))

    def test_private_runtime_archive_member_is_rejected_before_any_mutation(self):
        self.package({'backend/infra/deploy/personal/runtime/private.data': b'refuse'})
        with self.assertRaisesRegex(RuntimeError, 'archive member'):
            self.run_install()
        self.assertEqual(self.config.read_bytes(), b'old gateway')
