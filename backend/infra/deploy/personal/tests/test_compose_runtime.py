import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compose_runtime import compose_command


class ComposeRuntimeTests(unittest.TestCase):
    def test_activation_survives_release_and_alternate_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            folder = base / 'runtime/service-isolation'
            folder.mkdir(parents=True)
            activation = folder / 'activation.env'
            activation.write_text('SERVICE_ISOLATION_READY=verified-v1\n')
            activation.chmod(0o600)
            command = compose_command(base, 'pending.env', profiles=('workers',))
            self.assertIn('pending.env', command)
            self.assertIn(str(activation), command)
            self.assertEqual(command[-2:], ['-f', str(base / 'compose.isolated.yml')])

    def test_unverified_or_public_activation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            folder = base / 'runtime/service-isolation'
            folder.mkdir(parents=True)
            activation = folder / 'activation.env'
            activation.write_text('SERVICE_ISOLATION_READY=\n')
            activation.chmod(0o600)
            with self.assertRaises(RuntimeError):
                compose_command(base)
            if os.name == 'posix':
                activation.write_text('SERVICE_ISOLATION_READY=verified-v1\n')
                activation.chmod(0o644)
                with self.assertRaises(RuntimeError):
                    compose_command(base)
