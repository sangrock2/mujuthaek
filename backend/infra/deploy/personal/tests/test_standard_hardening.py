"""Check standard deployment parity without starting a container or reading real .env files."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DEPLOY = ROOT / 'backend/infra/deploy'
spec = importlib.util.spec_from_file_location('standard_gateway_probe', ROOT / 'backend/infra/security/test_gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class StandardDeployment(unittest.TestCase):
    def test_standard_gateway_has_the_same_security_properties(self):
        rendered = (DEPLOY / 'nginx/default.conf').read_text(encoding='utf-8').replace('${API_PUBLIC_HOST}', 'api.example.test')
        self.assertEqual(len(gateway.static_checks(rendered)), 3)
        for name in ('compose.prod.yml', 'compose.dev.yml'):
            text = (DEPLOY / name).read_text(encoding='utf-8')
            self.assertIn('API_PUBLIC_HOST: ${API_PUBLIC_HOST:?', text)
            self.assertIn('NGINX_ENVSUBST_FILTER: ^API_PUBLIC_HOST$', text)
            self.assertIn('/etc/nginx/templates/default.conf.template:ro', text)
            self.assertNotIn('env_file: .env', text)

    def test_optional_metrics_agents_have_no_docker_socket_or_whole_host_mount(self):
        text = (DEPLOY / 'compose.prod.yml').read_text(encoding='utf-8')
        self.assertNotRegex(text, r'(?m)^  cadvisor:')
        self.assertNotIn('/var/run:', text)
        self.assertNotRegex(text, r'(?m)^\s+- /:/')
        self.assertIn('/proc:/host/proc:ro', text)
        self.assertIn('/sys:/host/sys:ro', text)

    @unittest.skipUnless(shutil.which('docker'), 'Compose CLI unavailable')
    def test_compose_resolves_only_each_services_explicit_secret_allowlist(self):
        for name in ('prod', 'dev'):
            with self.subTest(environment=name), tempfile.TemporaryDirectory() as folder:
                path = DEPLOY / f'compose.{name}.yml'
                required = set(re.findall(r'\$\{([A-Z][A-Z0-9_]*)(?::\?|\})', path.read_text(encoding='utf-8')))
                settings = {key: 'synthetic-only' for key in required}
                settings.update(API_PUBLIC_HOST='api.example.test', API_TLS_CERT_DIR=folder,
                                API_TAG='example', NOTIFICATION_TAG='example', COLLECTOR_TAG='example', EXTRACTION_TAG='example',
                                RABBITMQ_USER='testuser', RABBITMQ_PASSWORD='test-password', RDS_HOST='db.example.test',
                                UNRELATED_TOKEN='never-forward-this', JWT_SECRET='synthetic-jwt',
                                OPENAI_API_KEY='synthetic-model', PUSH_VAPID_PRIVATE_KEY='synthetic-push',
                                API_DB_PASSWORD='synthetic-api-db', NOTIFICATION_DB_PASSWORD='synthetic-notification-db')
                envfile = Path(folder) / 'synthetic.env'
                envfile.write_text(''.join(f'{key}={value}\n' for key, value in settings.items()), encoding='utf-8')
                environment = {key: value for key, value in os.environ.items()
                               if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'USERPROFILE',
                                                  'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMW6432', 'PROGRAMFILES(X86)'}}
                result = subprocess.run(['docker', 'compose', '--env-file', str(envfile), '-f', str(path),
                                         'config', '--format', 'json'], check=True, capture_output=True, text=True,
                                        env=environment, timeout=30)
                services = json.loads(result.stdout)['services']
                for service, value in services.items():
                    self.assertNotIn('UNRELATED_TOKEN', value.get('environment', {}), service)
                for service in ('collector', 'extraction', 'notification'):
                    if service in services:
                        self.assertNotIn('JWT_SECRET', services[service].get('environment', {}), service)
                        self.assertNotIn('API_DB_PASSWORD', services[service].get('environment', {}), service)
                for service in ('collector', 'extraction', 'api'):
                    if service in services:
                        self.assertNotIn('PUSH_VAPID_PRIVATE_KEY', services[service].get('environment', {}), service)
                self.assertNotIn('OPENAI_API_KEY', services['api']['environment'])
                self.assertNotIn('OPENAI_API_KEY', services['notification']['environment'])


if __name__ == '__main__':
    unittest.main()
