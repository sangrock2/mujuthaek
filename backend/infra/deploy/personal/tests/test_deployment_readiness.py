"""Regression checks for burst-starved startup, bounded probes and safe recovery."""
import importlib.util
import json
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
sys.path.insert(0, str(BASE))
import install_runtime_update as installer
sys.path.insert(0, str(ROOT / '.github/scripts'))
import backend_release as backend


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
