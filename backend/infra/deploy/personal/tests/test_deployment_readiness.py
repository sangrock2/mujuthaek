"""Regression checks for burst-starved startup, bounded probes and safe recovery."""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
spec = importlib.util.spec_from_file_location('readiness_host', BASE / 'release_host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
gateway_spec = importlib.util.spec_from_file_location('gateway_harness', ROOT / 'backend/infra/security/test_gateway.py')
gateway = importlib.util.module_from_spec(gateway_spec)
gateway_spec.loader.exec_module(gateway)
sys.path.insert(0, str(BASE))
import install_runtime_update as installer
sys.path.insert(0, str(ROOT / '.github/scripts'))
import backend_release as backend

# Variables the live host's .env already has. It gets no new ones before the next deploy, so anything else the
# manifest reads must have a default.
LIVE_REQUIRED = {
    'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'S3_BUCKET', 'POSTGRES_PASSWORD', 'API_DB_PASSWORD',
    'NOTIFICATION_DB_PASSWORD', 'COLLECTOR_DB_PASSWORD', 'EXTRACTION_DB_PASSWORD', 'RABBITMQ_PASSWORD', 'RELEASE',
    'JWT_SECRET', 'PUBLIC_ORIGIN', 'NOTIFICATION_INTERNAL_TOKEN', 'COLLECTOR_ADMIN_TOKEN', 'EXTRACTION_REVIEW_TOKEN',
    'TRAFFIC_INGEST_TOKEN', 'API_TLS_CERT_DIR',
}


def service(source, name):
    match = re.search(r'(?ms)^  ' + re.escape(name) + r':\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)', source)
    return match[0] if match else ''


class Clock:
    def __init__(self): self.now = 0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class Readiness(unittest.TestCase):
    def test_runtime_manifest_preserves_mail_keys_and_is_idempotent(self):
        source = (BASE / 'compose.prod.yml').read_text()
        result = installer.runtime_manifest(source)
        self.assertEqual(installer.runtime_manifest(result), result)
        self.assertIn('NOTIFICATION_MAIL_PROVIDER: ${NOTIFICATION_MAIL_PROVIDER:-log}', result)
        self.assertIn('PUSH_VAPID_PRIVATE_KEY: ${PUSH_VAPID_PRIVATE_KEY:-}', result)
        self.assertEqual(result.count('cpus: "0.10"'), 1)
        self.assertEqual(result.count('cpus: "0.15"'), 1)

    def test_virtual_thread_scheduler_is_not_a_single_carrier(self):
        # 보안 감사 M-1: ActiveProcessorCount=1만 두면 가상 스레드 실행기도 1개라 CPU를 쓰는 요청 하나가 모든 요청을 멈췄어요
        source = (BASE / 'compose.prod.yml').read_text().replace(' -Djdk.virtualThreadScheduler.parallelism=4', '')
        result = installer.runtime_manifest(source)
        self.assertEqual(installer.runtime_manifest(result), result)
        options = [line for line in result.splitlines() if line.startswith('      JAVA_TOOL_OPTIONS:')]
        self.assertEqual(len(options), 2)  # api, notification
        for line in options:
            self.assertIn('-XX:ActiveProcessorCount=1', line)
            self.assertEqual(line.count('-Djdk.virtualThreadScheduler.parallelism=4'), 1)
        self.assertEqual(installer.runtime_manifest((BASE / 'compose.prod.yml').read_text()), installer.runtime_manifest(result))

    def test_four_minute_startup_succeeds_within_the_deadline(self):
        obj = host.Host.__new__(host.Host)
        clock = Clock()
        obj.probe = Mock(side_effect=lambda service: 'UP' if clock.now >= 275 else 'unreachable')
        with patch.object(host.time, 'monotonic', clock.monotonic), patch.object(host.time, 'sleep', clock.sleep):
            obj.healthy(('api',), timeout=600)
        self.assertGreaterEqual(clock.now, 275)
        self.assertLess(clock.now, 600)

    def test_readiness_stops_at_deadline_and_names_the_service(self):
        obj = host.Host.__new__(host.Host)
        obj.probe = Mock(return_value='unreachable')
        clock = Clock()
        with patch.object(host.time, 'monotonic', clock.monotonic), patch.object(host.time, 'sleep', clock.sleep):
            with self.assertRaisesRegex(RuntimeError, 'notification=unreachable'):
                obj.healthy(('notification',), timeout=12)
        self.assertEqual(clock.now, 12)

    def test_malformed_or_hung_health_response_is_not_ready(self):
        obj = host.Host.__new__(host.Host)
        with patch.object(host.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='<html>bad gateway</html>')) as command:
            self.assertEqual(obj.probe('api'), 'unreachable')
            self.assertEqual(command.call_args.kwargs['timeout'], 5)
        with patch.object(host.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='[]')):
            self.assertEqual(obj.probe('api'), 'not-ready')
        obj.compose = Mock(side_effect=subprocess.TimeoutExpired('probe', 6))
        self.assertEqual(obj.probe('notification'), 'unreachable')
        self.assertEqual(obj.compose.call_args.kwargs['timeout'], 6)

    def test_jvms_start_sequentially_and_proxy_reloads_after_api(self):
        with tempfile.TemporaryDirectory() as folder:
            obj = host.Host.__new__(host.Host)
            events = []
            obj.compose = lambda *args: events.append(('up', args[-1])) if args[0] == 'up' else None
            obj.healthy = lambda services=None, **kwargs: events.append(('healthy', services))
            obj.reload_nginx = lambda: events.append(('reload',))
            (Path(folder) / 'versions.env').write_text('RELEASE=release-old\n')
            with patch.object(host, 'BASE', Path(folder)):
                obj.select('release-new')
            self.assertEqual(events[:5], [('up','api'), ('healthy',('api',)), ('reload',), ('up','notification'), ('healthy',('notification',))])

    def test_worker_cpu_limits_are_restored_even_after_a_failed_deployment(self):
        with tempfile.TemporaryDirectory() as folder:
            obj = host.Host.__new__(host.Host)
            obj.runtime = Path(folder)
            updates = []
            def command(args, **kwargs):
                if args[:2] == ['docker','inspect']:
                    service = 'collector' if 'collector' in args[-1] else 'extraction'
                    data = {'Id': service + '-id', 'State': {'Running': True}, 'Config': {'Labels': {'com.docker.compose.project':'mujuthaek-personal'}}, 'HostConfig': {'NanoCpus':100_000_000 if service == 'collector' else 150_000_000}}
                    return SimpleNamespace(returncode=0, stdout=json.dumps([data]))
                updates.append(args[-2:])
                return SimpleNamespace(returncode=0)
            with patch.object(host.subprocess,'run',side_effect=command):
                with self.assertRaisesRegex(RuntimeError, 'candidate failed'):
                    with obj.worker_cpu_budget():
                        raise RuntimeError('candidate failed')
            self.assertEqual(updates,[['0.03','collector-id'],['0.03','extraction-id'],['0.1','collector-id'],['0.15','extraction-id']])

    def test_candidate_is_stopped_before_schema_check_and_never_rolled_back_after_migration(self):
        obj = host.Host.__new__(host.Host)
        obj.ensure_images = Mock()
        obj.select = Mock(side_effect=RuntimeError('unhealthy'))
        events = []
        obj.compose = lambda *args: events.append(args[0])
        def schema(): events.append('schema'); return 'schema-new'
        obj.schema = schema
        images = {s: {'tag':s + ':release-new'} for s in host.SERVICES}
        with patch.object(host.subprocess,'run'):
            with self.assertRaisesRegex(RuntimeError,'automatic app rollback blocked'):
                obj.prepare_and_activate('release-new',{'format':2,'images':images},{'release':'release-old'},images,list(host.SERVICES),'schema-old')
        self.assertEqual(events,['stop','schema','up'])
        obj.select.assert_called_once_with('release-new',images,list(host.SERVICES))

    def test_progress_is_only_published_when_runner_negotiated_it(self):
        with tempfile.TemporaryDirectory() as folder:
            obj = host.Host.__new__(host.Host)
            obj.runtime = Path(folder)
            obj.upload = Mock()
            obj._request = {'request':'request-123','release':'release-new'}
            obj.progress('starting-api')
            obj.upload.assert_not_called()
            obj._request['progress_protocol'] = 1
            obj.progress('starting-api')
            obj.upload.assert_called_once_with('progress.json','results/request-123.json')

    def test_busy_timer_defers_without_failing_or_reading_stale_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = SimpleNamespace(LOCK_EX=1, LOCK_NB=2, flock=Mock(side_effect=BlockingIOError()))
            with patch.dict(sys.modules,{'fcntl':fake}), patch.object(host,'BASE',Path(folder)), \
                    patch.object(host,'__file__',str(Path(folder)/'release_host.py')), \
                    patch.object(host,'os',SimpleNamespace(name='posix',geteuid=lambda:0)), patch.object(host,'Host') as construct:
                host.main()
            construct.assert_not_called()


class ResultProtocol(unittest.TestCase):
    def test_progress_is_waited_for_instead_of_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path.cwd()
            import os
            os.chdir(folder)
            try:
                progress = {'status':'running','request':'request-123','release':'release-new','phase':'starting-api'}
                final = {'ok':True,'request':'request-123','release':'release-new'}
                with patch.object(backend,'get',side_effect=[{'release':'release-new'},progress,final]), \
                        patch.object(backend,'put') as put, patch.object(backend.time,'sleep'):
                    backend.request('release-new','deploy','request-123')
                request = json.loads(Path('desired.json').read_text())
                self.assertEqual(request['progress_protocol'],1)
                put.assert_called_once_with('desired.json','desired.json')
            finally:
                os.chdir(old)

    def test_repeated_result_access_error_is_uncertain_not_an_automatic_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path.cwd()
            import os
            os.chdir(folder)
            try:
                failure = subprocess.CalledProcessError(1,['aws'],stderr='AccessDenied')
                with patch.object(backend,'get',side_effect=[{'release':'release-new'},failure,failure,failure]), \
                        patch.object(backend,'put') as put, patch.object(backend.time,'sleep'):
                    with self.assertRaisesRegex(TimeoutError,'inspect server status'):
                        backend.request('release-new','deploy','request-123')
                    self.assertEqual(put.call_count,1)
            finally:
                os.chdir(old)


class ProductionManifest(unittest.TestCase):
    def setUp(self):
        # Other checks read this file with the Windows locale code page, so it must stay ASCII.
        self.source = (BASE / 'compose.prod.yml').read_text(encoding='ascii')

    def test_an_existing_host_env_still_satisfies_every_required_variable(self):
        self.assertEqual(set(re.findall(r'\$\{(\w+):\?', self.source)), LIVE_REQUIRED)

    def test_api_gets_private_hash_salt_unsubscribe_key_and_ops_alerts_as_optional_values(self):
        # Security audit L-1/L-15 (empty: the API derives its own fallback) and L-24 (empty: alerts stay off).
        api = service(self.source, 'api')
        for line in ('TRAFFIC_IP_SALT: ${TRAFFIC_IP_SALT:-}', 'EMAIL_UNSUBSCRIBE_KEY: ${EMAIL_UNSUBSCRIBE_KEY:-}',
                     'SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL:-${EXTRACTION_SLACK_WEBHOOK_URL:-}}', 'MUJUTHAEK_ENV: prod'):
            self.assertIn('\n      ' + line + '\n', api)
        # A separately passed empty EXTRACTION_SLACK_WEBHOOK_URL would never be reached by Spring's fallback.
        self.assertNotIn('      EXTRACTION_SLACK_WEBHOOK_URL:', api)

    def test_no_stale_server_side_frontend_container(self):
        # Security audit L-20: Vercel serves the site; nothing on the host routes to an old Next.js container.
        self.assertEqual(service(self.source, 'frontend'), '')
        self.assertNotIn('mujuthaek-personal-frontend', self.source)
        self.assertIn('\n    depends_on: [api]\n', service(self.source, 'nginx'))
        conf = (BASE / 'nginx/default.conf').read_text(encoding='utf-8')
        self.assertEqual(set(re.findall(r'proxy_pass\s+(\S+);', conf)), {'http://api:8080'})
        self.assertIn('location / { return 302 https://mujuthaek.vercel.app$request_uri; }', conf)

    def test_host_manifest_update_keeps_new_settings(self):
        result = installer.runtime_manifest(self.source)
        self.assertIn('      MUJUTHAEK_ENV: prod\n', service(result, 'api'))
        self.assertEqual(service(result, 'frontend'), '')


class GatewayLimits(unittest.TestCase):
    def setUp(self):
        self.config = (BASE / 'nginx/default.conf').read_text(encoding='utf-8')

    def test_every_proxied_location_has_per_address_and_server_wide_limits(self):
        self.assertEqual(gateway.limit_gaps(self.config), [])
        names = [name for name, _ in gateway.locations(self.config)]
        for name in ('= /actuator/health', '/oauth2/', '/login/oauth2/', '/api/'):
            self.assertIn(name, names)

    def test_checker_reports_the_audited_gaps(self):
        # Security audit L-16: health had no limit at all and OAuth start only a per-address one.
        old = re.sub(r'(?ms)^    location = /actuator/health \{.*?^    \}\n',
                     '    location = /actuator/health { proxy_pass http://api:8080; }\n', self.config)
        old = old.replace('        limit_req zone=login_total burst=20 nodelay;\n', '')
        self.assertEqual(gateway.limit_gaps(old), ['= /actuator/health', '/oauth2/'])


class BrokerRetention(unittest.TestCase):
    def test_personal_data_dead_letter_queues_get_a_seven_day_cap_without_touching_others(self):
        # Security audit L-14: failed notification messages carry recipients' emails and push keys.
        command = host.dlq_retention_command()
        self.assertEqual(command[:9], ('exec', '-T', 'rabbitmq', 'rabbitmqctl', 'set_operator_policy',
                                       '--priority', '0', '--apply-to', 'queues'))
        name, pattern, definition = command[9:]
        self.assertEqual(name, 'mujuthaek-dlq-retention')
        self.assertEqual(definition, '{"message-ttl":604800000,"max-length":10000}')
        for queue in ('mujuthaek.notification.dlq', 'mujuthaek.api.push-subscription-expired.dlq'):
            self.assertRegex(queue, pattern)
        # Pipeline DLQs may still need reprocessing; a TTL policy would delete their old messages at once.
        for queue in ('mujuthaek.raw.collected.dlq', 'mujuthaek.raw.policy.dlq', 'mujuthaek.policy.extracted.dlq',
                      'mujuthaek.area.source-ready.dlq', 'mujuthaek.notification', 'mujuthaek.raw.collected',
                      'mujuthaek.dlx', 'other.notification.dlq', 'mujuthaek.notification.dlq.archive'):
            self.assertNotRegex(queue, pattern)
