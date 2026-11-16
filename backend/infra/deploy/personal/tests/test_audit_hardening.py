"""Regression checks for the 2026-11-16 security audit's defense-in-depth items (gateway, host, CI)."""
import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(ROOT / '.github/scripts'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gateway = load('audit_gateway', ROOT / 'backend/infra/security/test_gateway.py')
host = load('audit_release_host', BASE / 'release_host.py')
packager = load('audit_package_release', BASE / 'package_release.py')
oidc = load('audit_setup_github_release', BASE / 'setup_github_release.py')
import backend_release as backend
from test_release import image_archive


def service(source, name):
    match = re.search(r'(?ms)^  ' + re.escape(name) + r':\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)', source)
    return match[0] if match else ''


class Gateway(unittest.TestCase):
    def setUp(self):
        self.config = (BASE / 'nginx/default.conf').read_text(encoding='utf-8')

    def test_static_gateway_properties_hold(self):
        self.assertEqual(set(gateway.static_checks(self.config)), {
            'every_proxied_location_has_ip_and_total_limits', 'unsafe_path_rule_blocks_only_path_segments',
            'tls_and_forwarded_host_pinned'})
        self.assertEqual(gateway.server_names(self.config)[0], 'api.mujuthaek.store')

    def test_static_checks_catch_each_regression(self):
        rule = re.search(r'(?m)^    if \(\$request_uri .*\n', self.config)[0]
        broken = {
            'unsafe rule removed': self.config.replace(rule, ''),
            'query semicolons blocked': self.config.replace('^[^?]*(;', '(;'),
            'client host forwarded': self.config.replace('X-Forwarded-Host $server_name;', 'X-Forwarded-Host $host;'),
            'tickets on': self.config.replace('ssl_session_tickets off;', 'ssl_session_tickets on;', 1),
            'no hsts': self.config.replace('    add_header Strict-Transport-Security "max-age=31536000" always;\n', ''),
            'unknown host served': self.config.replace('    return 444;\n', ''),
        }
        for name, config in broken.items():
            with self.subTest(name), self.assertRaises(AssertionError):
                gateway.static_checks(config)

    def test_compose_mounts_only_tracked_shipped_nginx_files(self):
        # Security audit: the port-80 file was an untracked copy, so tests checked a different file than production.
        compose = (BASE / 'compose.prod.yml').read_text(encoding='ascii')
        mounts = re.findall(r'(?m)^      - \./(nginx/[\w.-]+):/etc/nginx/conf\.d/', compose)
        self.assertEqual(sorted(mounts), ['nginx/acme.conf', 'nginx/default.conf'])
        for mount in mounts:
            self.assertTrue((BASE / mount).is_file(), mount)
            self.assertTrue(packager.allowed('backend/infra/deploy/personal/' + mount), mount)
        self.assertEqual(gateway.ACME, BASE / 'nginx/acme.conf')
        self.assertEqual(gateway.CONFIG, BASE / 'nginx/default.conf')
        acme = (BASE / 'nginx/acme.conf').read_text(encoding='utf-8')
        self.assertIn('listen 80 default_server;', acme)
        self.assertNotIn('proxy_pass', acme)


class HostManifest(unittest.TestCase):
    def setUp(self):
        self.source = (BASE / 'compose.prod.yml').read_text(encoding='ascii')

    def test_broker_runs_without_the_management_plugin(self):
        broker = service(self.source, 'rabbitmq')
        self.assertRegex(broker, r'\n    image: rabbitmq:4\.1@sha256:[a-f0-9]{64}\n')
        self.assertNotIn('management', broker.split('image:')[1].splitlines()[0])
        self.assertNotIn('15672', self.source)
        # Every broker command the personal scripts run is a core CLI command.
        for path in BASE.glob('*.py'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('15672', text, path.name)
            self.assertNotIn('rabbitmqadmin', text, path.name)

    def test_metrics_token_is_optional_for_both_java_services(self):
        for name in ('api', 'notification'):
            self.assertIn('\n      METRICS_TOKEN: ${METRICS_TOKEN:-}\n', service(self.source, name), name)
        # A fresh host generates it with the other runtime secrets; an existing host .env simply leaves it empty.
        self.assertIn('"METRICS_TOKEN"', (BASE / 'setup_resources.py').read_text(encoding='utf-8'))

    def test_database_init_passes_no_password_on_a_command_line(self):
        script = (BASE / 'db-init.sh').read_text(encoding='utf-8')
        self.assertNotRegex(script, r'--set="?password=')
        self.assertIn('\\getenv password :password_variable', script)
        notification = (ROOT / 'backend/infra/db/init/03-notification.sh').read_text(encoding='utf-8')
        self.assertNotRegex(notification, r"-c \"create role[^\n]*password")
        for name in ('backend/infra/docker-compose.yml', 'backend/infra/deploy/compose.prod.yml',
                     'backend/infra/deploy/compose.dev.yml', 'backend/infra/deploy/personal/compose.prod.yml'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertNotIn('-password=', text, name)
            if 'flyway/flyway' in text and name != 'backend/infra/deploy/personal/compose.prod.yml':
                self.assertIn('FLYWAY_PASSWORD: ${', text, name)

    def test_team_extraction_publication_fails_closed_by_default(self):
        for name in ('compose.prod.yml', 'compose.dev.yml'):
            text = (ROOT / 'backend/infra/deploy' / name).read_text(encoding='utf-8')
            self.assertIn('      EXTRACTION_PUBLICATION_MODE: ${EXTRACTION_PUBLICATION_MODE:-manual}\n', service(text, 'extraction'))

    def test_worker_images_keep_code_and_environment_read_only(self):
        for name in ('collector', 'extraction'):
            text = (ROOT / f'backend/services/{name}/Dockerfile').read_text(encoding='utf-8')
            self.assertNotIn('chown', text, name)
            self.assertIn('--compile-bytecode', text, name)
            self.assertRegex(text, rf'(?m)^USER {name}$')
            # The runtime user is created after every COPY/RUN that writes /app, and nothing is handed to it.
            self.assertLess(max(text.rfind('\nCOPY '), text.rfind('uv sync')), text.find('useradd'))


class Packaging(unittest.TestCase):
    def test_certificate_state_and_host_credentials_are_never_packaged(self):
        prefix = 'backend/infra/deploy/personal/'
        for name in ('letsencrypt/accounts/acme-v02.api.letsencrypt.org/directory/abc/private_key.json',
                     'letsencrypt/accounts/acme-v02.api.letsencrypt.org/directory/abc/regr.json',
                     'letsencrypt/renewal/mujuthaek-prod.conf', 'letsencrypt-work/backups/x', 'letsencrypt-logs/letsencrypt.log',
                     'tls/fullchain.pem', 'acme-webroot/.well-known/acme-challenge/token', 'release-host.env',
                     'backup-aws.env', 'accounts/private_key.json', 'private_key.json', 'runtime/backups/api.dump',
                     'api-20261116.dump', '.env', 'tls-settings-prod.json'):
            with self.subTest(name):
                self.assertFalse(packager.allowed(prefix + name))
        for name in ('compose.prod.yml', 'nginx/acme.conf', 'nginx/default.conf', 'release_host.py', 'db-init.sh'):
            self.assertTrue(packager.allowed(prefix + name), name)


class ImageLoading(unittest.TestCase):
    TAGS = ['mujuthaek-personal-api:release-123', 'mujuthaek-personal-notification:release-123']

    def test_archive_tags_must_match_the_release_before_docker_load(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'images.tar.gz'
            for tags in ([self.TAGS[0]], [*self.TAGS, 'nginx:1.29-alpine'], [*self.TAGS, 'amazon/aws-cli:2.36.28'],
                         ['mujuthaek-personal-api:release-999', self.TAGS[1]]):
                image_archive(archive, tags)
                with self.subTest(tags=tags), patch.object(host.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'tags differ'):
                        host.load_images(archive, self.TAGS, timeout=5)
                    run.assert_not_called()
            archive.write_bytes(b'not an archive')
            with patch.object(host.subprocess, 'run') as run, self.assertRaisesRegex(ValueError, 'unreadable'):
                host.load_images(archive, self.TAGS, timeout=5)
            run.assert_not_called()

    def test_loaded_tags_are_verified_after_docker_load(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'images.tar.gz'
            image_archive(archive, ['docker.io/library/' + self.TAGS[0], self.TAGS[1]])
            good = ''.join(f'Loaded image: {tag}\n' for tag in self.TAGS)
            with patch.object(host.subprocess, 'run', return_value=SimpleNamespace(stdout=good)) as run:
                host.load_images(archive, self.TAGS, timeout=5)
            self.assertEqual(run.call_args.args[0], ['docker', 'load', '-i', str(archive)])
            with patch.object(host.subprocess, 'run', return_value=SimpleNamespace(stdout='Loaded image: nginx:1.29-alpine\n')):
                with self.assertRaisesRegex(ValueError, 'Loaded image tags differ'):
                    host.load_images(archive, self.TAGS, timeout=5)

    def test_every_docker_load_on_the_host_goes_through_the_tag_check(self):
        for path in BASE.glob('*.py'):
            text = path.read_text(encoding='utf-8')
            loads = re.findall(r"\['docker', 'load'", text)
            if path.name == 'release_host.py':
                self.assertEqual(len(loads), 1)
                self.assertIn("require_tags(path, expected)\n    result = subprocess.run(['docker', 'load'", text)
            else:
                self.assertEqual(loads, [], path.name)

    def test_aws_cli_image_is_never_pulled_implicitly(self):
        sources = {path.name: path.read_text(encoding='utf-8') for path in BASE.glob('*.py')}
        self.assertEqual([name for name, text in sources.items() if 'amazon/aws-cli:' in text], ['release_host.py'])
        uses = 0
        for name, text in sources.items():
            # Each command that runs the CLI image, from its `docker run` up to the image argument.
            for match in re.finditer(r'(?<!import )AWS_IMAGE,', text):
                command = text[:match.start()].rsplit('docker', 1)[-1]
                with self.subTest(script=name):
                    self.assertRegex(command, r"""^['"], ['"]run['"]""")
                    self.assertRegex(command, r"""['"]--pull['"], ['"]never['"]""")
                uses += 1
        self.assertGreaterEqual(uses, 4)
        obj = host.Host.__new__(host.Host)
        obj.credentials, obj.runtime = Path('/c'), Path('/r')
        with patch.object(host.subprocess, 'run') as run:
            obj.aws('s3', 'ls')
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('--pull') + 1], 'never')
        self.assertIn(host.AWS_IMAGE, args)


class ConfigDrift(unittest.TestCase):
    def test_release_records_host_file_digests_and_host_reports_differences(self):
        self.assertEqual(backend.HOST_FILES, host.HOST_FILES)
        recorded = backend.host_file_digests()
        self.assertEqual(host.config_drift(BASE, recorded), [])
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder)
            (copy / 'nginx').mkdir()
            for name in host.HOST_FILES:
                # Line endings from a Windows checkout are not drift.
                (copy / name).write_bytes((BASE / name).read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            self.assertEqual(host.config_drift(copy, recorded), [])
            (copy / 'compose.prod.yml').write_text('edited on the server\n')
            (copy / 'nginx/acme.conf').unlink()
            self.assertEqual(host.config_drift(copy, recorded), ['compose.prod.yml', 'nginx/acme.conf'])
        self.assertEqual(host.config_drift(BASE, None), [])

    def test_publish_adds_the_digests_to_the_manifest(self):
        base = {'release': 'release-old', 'images': {s: {'tag': f'mujuthaek-personal-{s}:release-old', 'id': 'sha256:' + 'a' * 64}
                                                     for s in host.SERVICES}}
        with tempfile.TemporaryDirectory() as folder:
            previous = Path.cwd()
            import os
            os.chdir(folder)
            try:
                with patch.object(backend, 'put'):
                    data = backend.publish('release-new', 'c' * 40, base=base, services=[])
            finally:
                os.chdir(previous)
        self.assertEqual(set(data['host_files']), set(host.HOST_FILES))
        self.assertEqual(host.manifest(data)['host_files'], data['host_files'])


class CiLogs(unittest.TestCase):
    def test_host_strings_cannot_start_workflow_commands(self):
        for value in ('a\n::add-mask::x', 'x\r\n::stop-commands::t', 'p\u2028::warning::w', '::error::e', 'a\x85::set-env::'):
            text = backend.log_safe(value)
            self.assertNotRegex(text, r'[\r\n\x85\u2028\u2029]')
            self.assertNotIn('::', text)
        self.assertEqual(len(backend.log_safe('x' * 500)), 200)

    def test_progress_and_failure_messages_are_printed_on_single_neutral_lines(self):
        progress = {'status': 'running', 'request': 'request-123', 'release': 'release-new',
                    'phase': 'loading\n::add-mask::secret-looking'}
        failure = {'ok': False, 'request': 'request-123', 'release': 'release-new',
                   'message': 'bad\n::error file=x::injected'}
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            previous = Path.cwd()
            import os
            os.chdir(folder)
            try:
                with patch.object(backend, 'get', side_effect=[{'release': 'release-new'}, progress, failure]), \
                        patch.object(backend, 'put'), patch.object(backend.time, 'sleep'), \
                        contextlib.redirect_stdout(output):
                    with self.assertRaises(RuntimeError) as error:
                        backend.request('release-new', 'deploy', 'request-123')
            finally:
                os.chdir(previous)
        lines = output.getvalue().splitlines() + str(error.exception).splitlines()
        self.assertEqual(len(str(error.exception).splitlines()), 1)
        self.assertFalse([line for line in lines if line.lstrip().startswith('::')])
        self.assertNotIn('::', output.getvalue() + str(error.exception))


class RepositoryHygiene(unittest.TestCase):
    def test_environment_files_are_ignored_but_examples_stay_tracked(self):
        lines = (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
        for rule in ('.env*', '!.env.example', '!*.example'):
            self.assertIn(rule, lines)
        self.assertLess(lines.index('.env*'), lines.index('!*.example'))


class GithubOidc(unittest.TestCase):
    def test_trust_is_pinned_to_workflow_files_on_main(self):
        trust = oidc.trust_policy('repo:sangrock2/mujuthaek', oidc.RELEASE_WORKFLOWS)
        condition = trust['Statement'][0]['Condition']['StringEquals']
        self.assertEqual(condition['token.actions.githubusercontent.com:aud'], 'sts.amazonaws.com')
        self.assertEqual(condition['token.actions.githubusercontent.com:sub'], [
            'repo:sangrock2/mujuthaek:ref:refs/heads/main:workflow_ref:'
            'sangrock2/mujuthaek/.github/workflows/production.yml@refs/heads/main',
            'repo:sangrock2/mujuthaek:ref:refs/heads/main:workflow_ref:'
            'sangrock2/mujuthaek/.github/workflows/workers.yml@refs/heads/main'])
        self.assertNotIn('StringLike', json.dumps(trust))

    def test_subject_template_must_be_default_or_exactly_workflow_scoped(self):
        self.assertEqual(oidc.subject_prefix({'use_default': True}), 'repo:sangrock2/mujuthaek')
        self.assertEqual(oidc.subject_prefix({'use_default': False, 'include_claim_keys': oidc.SUB_CLAIM_KEYS}),
                         'repo:sangrock2/mujuthaek')
        for value in ({'use_default': False, 'include_claim_keys': ['repo']},
                      {'use_default': True, 'sub_claim_prefix': 'repo:attacker/mujuthaek'}):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                oidc.subject_prefix(value)

    def test_plan_role_only_reads_release_state(self):
        statements = oidc.plan_policy()['Statement']
        self.assertEqual({action for statement in statements for action in [statement['Action']]}, {'s3:GetObject'})
        self.assertNotIn('Put', json.dumps(statements))
        self.assertEqual(oidc.PLAN_WORKFLOWS, ('production.yml',))

    def test_each_workflow_assumes_only_roles_that_trust_it(self):
        trusted = {'AWS_DEPLOY_ROLE_ARN': set(oidc.RELEASE_WORKFLOWS), 'AWS_PLAN_ROLE_ARN': set(oidc.PLAN_WORKFLOWS),
                   'AWS_OPERATIONS_ROLE_ARN': {'operations.yml'}}
        for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
            for line in path.read_text(encoding='utf-8').splitlines():
                if 'role-to-assume:' not in line:
                    continue
                for name in re.findall(r'(?:vars|secrets)\.(\w+)', line):
                    with self.subTest(workflow=path.name, role=name):
                        self.assertIn(path.name, trusted[name])
        production = (ROOT / '.github/workflows/production.yml').read_text(encoding='utf-8')
        plan = production.split('\n  plan:\n')[1].split('\n  web-check:\n')[0]
        self.assertIn('vars.AWS_PLAN_ROLE_ARN', plan)

    def test_jobs_that_can_mint_cloud_tokens_restore_no_shared_cache(self):
        for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
            text = path.read_text(encoding='utf-8')
            for job in re.split(r'(?m)^  (?=[\w-]+:\n)', text.split('\njobs:\n', 1)[-1]):
                if 'id-token: write' in job:
                    with self.subTest(workflow=path.name, job=job.split(':', 1)[0]):
                        self.assertNotRegex(job, r'enable-cache: true|cache: (pip|npm|pnpm|gradle)|actions/cache@')
                        self.assertNotIn('setup-gradle', job)


if __name__ == '__main__':
    unittest.main()
