"""Immutable release archives and version-specific application rollback for the personal host."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
SERVICES = ('api', 'notification')
AWS_IMAGE = 'amazon/aws-cli:2.36.28'
READINESS_SECONDS = 600


def release_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{6,95}', value):
        raise ValueError('Invalid release ID')
    return value


def manifest(value):
    release_id(value['release'])
    if value.get('format', 1) not in (1, 2):
        raise ValueError('Unsupported release format')
    if set(value['images']) != set(SERVICES):
        raise ValueError('Only api and notification can be deployed')
    for service, image in value['images'].items():
        prefix = f'mujuthaek-personal-{service}:'
        if not image['tag'].startswith(prefix):
            raise ValueError('Unexpected image repository/tag')
        release_id(image['tag'][len(prefix):])
        if value.get('format', 1) == 1 and image['tag'] != prefix + value['release']:
            raise ValueError('Unexpected legacy image tag')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image['id']):
            raise ValueError('Image ID must be immutable')
    services = value.get('archive_services', list(SERVICES))
    if len(services) != len(set(services)) or not set(services) <= set(SERVICES):
        raise ValueError('Unexpected archive services')
    if services and not re.fullmatch(r'[0-9a-f]{64}', value['archive_sha256'] or ''):
        raise ValueError('Invalid archive checksum')
    if value.get('format', 1) == 2:
        for service in services:
            if value['images'][service]['tag'] != f"mujuthaek-personal-{service}:{value['release']}":
                raise ValueError('Archived image must belong to this release')
    return value


class Host:
    def __init__(self):
        if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
            raise RuntimeError('Run only on the verified personal deployment host')
        self.runtime = BASE / 'runtime/releases'
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.values = dict(line.split('=', 1) for line in (BASE / '.env').read_text().splitlines()
                           if line and not line.startswith('#'))
        self.bucket = self.values['S3_BUCKET']
        if self.bucket != 'mujuthaek-personal-659355919826-raw':
            raise RuntimeError('Unexpected bucket')
        self.credentials = BASE / 'release-host.env'
        if not self.credentials.is_file():
            raise RuntimeError('Separate host release credentials are required')
        info = self.credentials.stat()
        if info.st_uid != 0 or info.st_mode & 0o077:
            raise RuntimeError('Host release credentials must be root-owned and mode 600')

    def aws(self, *args):
        return subprocess.run(['docker', 'run', '--rm', '--env-file', str(self.credentials),
                               '--mount', f'type=bind,src={self.runtime},dst=/releases',
                               AWS_IMAGE, *args], check=True, capture_output=True, text=True, timeout=120)

    def download(self, key, name):
        self.aws('s3', 'cp', f's3://{self.bucket}/deployments/{key}', f'/releases/{name}', '--only-show-errors')
        return self.runtime / name

    def upload(self, name, key):
        self.aws('s3', 'cp', f'/releases/{name}', f's3://{self.bucket}/deployments/{key}',
                 '--only-show-errors', '--sse', 'AES256')

    def compose(self, *args, timeout=120):
        return subprocess.run(['docker', 'compose', '--env-file', '.env', '--env-file', 'versions.env',
                               '-f', 'compose.prod.yml', *args], cwd=BASE, check=True,
                              capture_output=True, text=True, timeout=timeout)

    def progress(self, phase, **details):
        request = getattr(self, '_request', None)
        if not request:
            return
        value = {'status': 'running', 'request': request['request'], 'release': request['release'],
                 'phase': phase, 'updated_at': int(time.time()), **details}
        print(json.dumps(value), flush=True)
        (self.runtime / 'progress.json').write_text(json.dumps(value))
        # Old runners expect only a final result. Streaming is explicitly negotiated.
        if request.get('progress_protocol') == 1:
            try:
                self.upload('progress.json', f"results/{request['request']}.json")
            except (subprocess.SubprocessError, OSError):
                print('Progress upload unavailable; final outcome will still be published', flush=True)

    @contextmanager
    def worker_cpu_budget(self):
        changed = []
        try:
            for service in ('collector', 'extraction'):
                result = subprocess.run(['docker', 'inspect', f'mujuthaek-personal-{service}-1'],
                                        capture_output=True, text=True, timeout=15)
                if result.returncode:
                    continue
                info = json.loads(result.stdout)[0]
                if not info['State']['Running']:
                    continue
                if info['Config']['Labels'].get('com.docker.compose.project') != 'mujuthaek-personal':
                    raise RuntimeError('Unexpected worker compose project')
                previous = info['HostConfig']['NanoCpus']
                if previous and previous <= 30_000_000:
                    continue
                record = {'id': info['Id'], 'service': service, 'nanocpus': previous}
                # Record before updating so interrupted maintenance can be reconciled.
                changed.append(record)
                recovery = self.runtime / 'worker-cpu-budget.json'
                recovery.write_text(json.dumps(changed))
                recovery.chmod(0o600)
                subprocess.run(['docker', 'update', '--cpus', '0.03', info['Id']],
                               check=True, capture_output=True, timeout=20)
            yield
        finally:
            failures = []
            for record in changed:
                try:
                    subprocess.run(['docker', 'update', '--cpus', str(record['nanocpus'] / 1_000_000_000), record['id']],
                                   check=True, capture_output=True, timeout=20)
                except (subprocess.SubprocessError, OSError):
                    failures.append(record['service'])
            if failures:
                print(json.dumps({'warning': 'worker_cpu_restore_failed', 'services': failures}), flush=True)

    def schema(self):
        versions = []
        for database, table in [('api', 'common.flyway_schema_history'),
                                ('notification', 'public.flyway_schema_history')]:
            value = self.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', database,
                                 '-tAc', f'select version,checksum,success from {table} order by installed_rank').stdout
            versions.append(value)
        return hashlib.sha256('\n'.join(versions).encode()).hexdigest()

    def current(self):
        return json.loads((self.runtime / 'current.json').read_text())

    def probe(self, service):
        try:
            if service == 'api':
                result = subprocess.run(['curl', '-fsS', '--max-time', '3', 'http://127.0.0.1:8080/actuator/health'],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode:
                    return 'unreachable'
            else:
                result = self.compose('exec', '-T', 'nginx', 'wget', '-T', '3', '-qO-',
                                      'http://notification:8081/actuator/health', timeout=6)
            body = json.loads(result.stdout)
            return 'UP' if isinstance(body, dict) and body.get('status') == 'UP' else 'not-ready'
        except (subprocess.SubprocessError, ValueError, OSError):
            return 'unreachable'

    def healthy(self, services=None, timeout=READINESS_SECONDS):
        services = tuple(SERVICES if services is None else services)
        started = time.monotonic()
        deadline = started + timeout
        reported = started - 90
        latest = {service: 'not-checked' for service in services}
        while time.monotonic() < deadline:
            latest = {service: self.probe(service) for service in services}
            if all(value == 'UP' for value in latest.values()):
                return
            now = time.monotonic()
            if now - reported >= 90:
                self.progress('waiting-for-readiness', services=latest, elapsed_seconds=int(now - started))
                reported = now
            time.sleep(min(3, max(0, deadline - time.monotonic())))
        raise RuntimeError('Readiness timed out: ' + ', '.join(f'{s}={v}' for s, v in latest.items()))

    def reload_nginx(self):
        self.compose('exec', '-T', 'nginx', 'nginx', '-t')
        self.compose('exec', '-T', 'nginx', 'nginx', '-s', 'reload')

    def select(self, release, images=None, services=None):
        services = list(SERVICES if services is None else services)
        images = images or {s: {'tag': f'mujuthaek-personal-{s}:{release}'} for s in SERVICES}
        path = BASE / 'versions.env'
        text = path.read_text()
        text = '\n'.join(line for line in text.splitlines()
                         if not line.startswith(('API_RELEASE=', 'NOTIFICATION_RELEASE=')))
        for service in SERVICES:
            text += f"\n{service.upper()}_RELEASE={images[service]['tag'].split(':', 1)[1]}"
        path.write_text(text + '\n')
        self.compose('config', '--quiet')
        deadline = time.monotonic() + READINESS_SECONDS
        # Start JVMs in sequence so they do not compete for exhausted burst capacity.
        for service in services:
            self.progress('starting-' + service)
            self.compose('up', '-d', '--no-deps', '--no-build', '--pull', 'never', service)
            self.healthy((service,), timeout=max(1, deadline - time.monotonic()))
            if service == 'api':
                self.reload_nginx()
        self.healthy(timeout=max(1, deadline - time.monotonic()))
        self.reload_nginx()

    def load_archive(self, data, name):
        archive = self.download(f"releases/{data['release']}/images.tar.gz", name)
        with archive.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != data['archive_sha256']:
            raise ValueError('Archive checksum mismatch')
        subprocess.run(['docker', 'load', '-i', str(archive)], check=True, capture_output=True, timeout=300)

    def ensure_images(self, data, services):
        loaded = set()
        for service in services:
            image = data['images'][service]
            result = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']],
                                    capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip() == image['id']:
                continue
            origin = release_id(image['tag'].split(':', 1)[1])
            if origin not in loaded:
                source = manifest(json.loads(self.download(f'releases/{origin}/manifest.json', f'origin-{origin}.json').read_text()))
                if source['release'] != origin or source['images'][service] != image:
                    raise ValueError('Image origin mismatch')
                if service not in source.get('archive_services', list(SERVICES)):
                    raise ValueError('Image missing from origin archive')
                self.load_archive(source, f'images-{origin}.tar.gz')
                loaded.add(origin)
            actual = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']],
                                    check=True, capture_output=True, text=True).stdout.strip()
            if actual != image['id']:
                raise ValueError(f'{service} image digest mismatch')

    def apply(self, request):
        target = release_id(request['release'])
        old = self.current()
        if old['release'] == target:
            return old
        if request.get('expected_base') and old['release'] != request['expected_base']:
            raise RuntimeError('Current release differs from the planned base; reconcile before retrying')
        data = manifest(json.loads(self.download(f'releases/{target}/manifest.json', 'candidate.json').read_text()))
        if data['release'] != target:
            raise ValueError('Manifest identity mismatch')
        schema = self.schema()
        previous_images = old.get('images')
        if data.get('format') == 2 and not previous_images:
            previous = manifest(json.loads(self.download(f"releases/{old['release']}/manifest.json", 'previous.json').read_text()))
            if previous['release'] != old['release']:
                raise ValueError('Previous manifest identity mismatch')
            previous_images = previous['images']
        services = [s for s in SERVICES if not previous_images or previous_images[s] != data['images'][s]]
        if request['mode'] == 'rollback' and services:
            saved = json.loads(self.download(f'states/{target}.json', 'target-state.json').read_text())
            if saved['schema'] != schema:
                raise RuntimeError('DB schema differs: application-only rollback requires review')
        if services:
            with self.worker_cpu_budget():
                self.prepare_and_activate(target, data, old, previous_images, services, schema)
        state = {'protocol': 2, 'release': target, 'previous': old['release'], 'schema': self.schema(),
                 'commit': data.get('commit'), 'images': data['images'], 'changed_services': services,
                 'applied_at': int(time.time())}
        (self.runtime / 'current.json').write_text(json.dumps(state))
        (self.runtime / 'state.json').write_text(json.dumps(state))
        self.progress('saving-release-state')
        self.upload('state.json', f'states/{target}.json')
        self.upload('state.json', 'states/current.json')
        return state

    def prepare_and_activate(self, target, data, old, previous_images, services, schema):
        self.progress('loading-images')
        if services:
            if data.get('format') == 2 or previous_images:
                self.ensure_images(data, services)
            else:
                self.load_archive(data, 'images.tar.gz')
                for service, image in data['images'].items():
                    actual = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']],
                                            check=True, capture_output=True, text=True).stdout.strip()
                    if actual != image['id']:
                        raise ValueError(f'{service} image digest mismatch')
            # A backup failure aborts before changing running applications.
            self.progress('database-backup')
            subprocess.run(['bash', str(BASE / 'backup.sh')], cwd=BASE, check=True, capture_output=True, timeout=300)
        try:
            if services:
                if previous_images:
                    self.select(target, data['images'], services)
                else:
                    self.select(target)
        except Exception:
            self.progress('checking-rollback-safety')
            # Stop the failed candidate before comparing schemas: a still-starting JVM
            # could otherwise commit a migration between the check and rollback.
            self.compose('stop', '--timeout', '30', *services)
            if self.schema() != schema or old.get('schema', schema) != schema:
                self.compose('up', '-d', '--no-deps', '--no-build', '--pull', 'never', *services)
                raise RuntimeError('Deployment failed after DB migration; candidate restarted, automatic app rollback blocked')
            self.progress('restoring-previous-applications')
            if previous_images:
                self.select(old['release'], previous_images, services)
            else:
                self.select(old['release'])
            raise

    def poll(self):
        request = json.loads(self.download('desired.json', 'desired.json').read_text())
        release_id(request['request'])
        if request['mode'] not in ('deploy', 'rollback'):
            raise ValueError('Invalid mode')
        marker = self.runtime / 'last-request'
        if marker.exists() and marker.read_text() == request['request']:
            return
        self._request = request
        self.progress('request-received')
        try:
            state = self.apply(request)
            outcome = {'ok': True, **state}
        except Exception as error:
            # No subprocess output/credentials are sent to CI logs.
            outcome = {'ok': False, 'error': type(error).__name__, 'message': str(error) if isinstance(error, (ValueError, RuntimeError)) else 'Host operation failed'}
        outcome['request'] = request['request']
        (self.runtime / 'result.json').write_text(json.dumps(outcome))
        self.upload('result.json', f"results/{request['request']}.json")
        marker.write_text(request['request'])


def main():
    import fcntl
    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only on the verified personal deployment host')
    runtime = BASE / 'runtime/releases'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (runtime / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another deployment/configuration task holds the lock; deferred to the next timer tick', flush=True)
            return
        Host().poll()


if __name__ == '__main__':
    main()
