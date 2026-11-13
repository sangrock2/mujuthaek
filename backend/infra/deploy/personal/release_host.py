"""Immutable release archives and version-specific application rollback for the personal host."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
SERVICES = ('api', 'notification')
AWS_IMAGE = 'amazon/aws-cli:2.36.28'


def release_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{6,95}', value):
        raise ValueError('Invalid release ID')
    return value


def manifest(value):
    release_id(value['release'])
    if set(value['images']) != set(SERVICES):
        raise ValueError('Only api and notification can be deployed')
    for service, image in value['images'].items():
        if image['tag'] != f"mujuthaek-personal-{service}:{value['release']}":
            raise ValueError('Unexpected image repository/tag')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image['id']):
            raise ValueError('Image ID must be immutable')
    if not re.fullmatch(r'[0-9a-f]{64}', value['archive_sha256']):
        raise ValueError('Invalid archive checksum')
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
                               AWS_IMAGE, *args], check=True, capture_output=True, text=True)

    def download(self, key, name):
        self.aws('s3', 'cp', f's3://{self.bucket}/deployments/{key}', f'/releases/{name}', '--only-show-errors')
        return self.runtime / name

    def upload(self, name, key):
        self.aws('s3', 'cp', f'/releases/{name}', f's3://{self.bucket}/deployments/{key}',
                 '--only-show-errors', '--sse', 'AES256')

    def compose(self, *args):
        return subprocess.run(['docker', 'compose', '--env-file', '.env', '--env-file', 'versions.env',
                               '-f', 'compose.prod.yml', *args], cwd=BASE, check=True,
                              capture_output=True, text=True)

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

    def healthy(self):
        for _ in range(60):
            result = subprocess.run(['curl', '-fsS', '--max-time', '3', 'http://127.0.0.1:8080/actuator/health'],
                                    capture_output=True, text=True)
            if result.returncode == 0 and json.loads(result.stdout).get('status') == 'UP':
                # Check notification too; its endpoint is private to the Docker network.
                try:
                    self.compose('exec', '-T', 'notification', 'bash', '-c',
                                 'exec 3<>/dev/tcp/127.0.0.1/8081; printf "GET /actuator/health HTTP/1.0\\r\\n\\r\\n" >&3; cat <&3 | grep -q \'"status":"UP"\'')
                    return
                except subprocess.CalledProcessError:
                    pass
            time.sleep(3)
        raise RuntimeError('Application health check failed')

    def select(self, release):
        path = BASE / 'versions.env'
        text = path.read_text()
        text = '\n'.join(line for line in text.splitlines()
                         if not line.startswith(('API_RELEASE=', 'NOTIFICATION_RELEASE=')))
        path.write_text(text + f'\nAPI_RELEASE={release}\nNOTIFICATION_RELEASE={release}\n')
        self.compose('config', '--quiet')
        self.compose('up', '-d', '--no-deps', '--no-build', '--pull', 'never', *SERVICES)
        self.healthy()
        self.compose('exec', '-T', 'nginx', 'nginx', '-t')
        self.compose('exec', '-T', 'nginx', 'nginx', '-s', 'reload')

    def apply(self, request):
        target = release_id(request['release'])
        old = self.current()
        if old['release'] == target:
            return old
        data = manifest(json.loads(self.download(f'releases/{target}/manifest.json', 'candidate.json').read_text()))
        if data['release'] != target:
            raise ValueError('Manifest identity mismatch')
        schema = self.schema()
        if request['mode'] == 'rollback':
            saved = json.loads(self.download(f'states/{target}.json', 'target-state.json').read_text())
            if saved['schema'] != schema:
                raise RuntimeError('DB schema differs: application-only rollback requires review')
        archive = self.download(f'releases/{target}/images.tar.gz', 'images.tar.gz')
        with archive.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != data['archive_sha256']:
            raise ValueError('Archive checksum mismatch')
        subprocess.run(['docker', 'load', '-i', str(archive)], check=True, capture_output=True)
        for service, image in data['images'].items():
            actual = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']],
                                    check=True, capture_output=True, text=True).stdout.strip()
            if actual != image['id']:
                raise ValueError(f'{service} image digest mismatch')
        # A backup failure aborts before changing running applications.
        subprocess.run(['bash', str(BASE / 'backup.sh')], cwd=BASE, check=True, capture_output=True)
        try:
            self.select(target)
        except Exception:
            if self.schema() != schema:
                raise RuntimeError('Deployment failed after DB migration; automatic app rollback blocked')
            self.select(old['release'])
            raise
        state = {'release': target, 'previous': old['release'], 'schema': self.schema(),
                 'commit': data.get('commit'), 'applied_at': int(time.time())}
        (self.runtime / 'current.json').write_text(json.dumps(state))
        (self.runtime / 'state.json').write_text(json.dumps(state))
        self.upload('state.json', f'states/{target}.json')
        return state

    def poll(self):
        request = json.loads(self.download('desired.json', 'desired.json').read_text())
        release_id(request['request'])
        if request['mode'] not in ('deploy', 'rollback'):
            raise ValueError('Invalid mode')
        marker = self.runtime / 'last-request'
        if marker.exists() and marker.read_text() == request['request']:
            return
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


if __name__ == '__main__':
    import fcntl

    host = Host()
    with (host.runtime / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        host.poll()
