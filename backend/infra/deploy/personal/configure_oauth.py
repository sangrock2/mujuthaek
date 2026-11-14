"""Apply owner-supplied OAuth credentials without printing or versioning their values."""
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
INPUT = Path('/home/ubuntu/.env.oauth')
KEYS = ('KAKAO_CLIENT_ID', 'KAKAO_CLIENT_SECRET', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET')


def credentials(text):
    values = {}
    for line in text.lstrip('\ufeff').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if name not in KEYS or name in values or not separator or not re.fullmatch(r'[A-Za-z0-9._-]+', value):
            raise ValueError('Invalid, duplicate, or empty OAuth entry; values were not displayed')
        values[name] = value
    if set(values) != set(KEYS) or not values['GOOGLE_CLIENT_ID'].endswith('.apps.googleusercontent.com'):
        raise ValueError('Missing OAuth entries or invalid Google client ID; values were not displayed')
    return values


def merge(original, values):
    lines = [line for line in original.splitlines() if line.partition('=')[0].strip() not in KEYS]
    return '\n'.join(lines + [f'{name}={values[name]}' for name in KEYS]) + '\n'


def private_file(content):
    descriptor, name = tempfile.mkstemp(prefix='.env.oauth-', dir=BASE)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(content)
    return Path(name)


def compose(env, *args):
    return subprocess.run(['docker', 'compose', '--env-file', str(env), '--env-file', 'versions.env',
                           '-f', 'compose.prod.yml', *args], cwd=BASE, check=True,
                          capture_output=True, text=True)


def healthy():
    for _ in range(60):
        result = subprocess.run(['curl', '-fsS', '--max-time', '3', 'http://127.0.0.1:8080/actuator/health'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            try:
                if json.loads(result.stdout).get('status') == 'UP':
                    return
            except ValueError:
                pass
        time.sleep(3)
    raise RuntimeError('API health check failed')


def restart(env):
    compose(env, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'api')
    healthy()
    compose(env, 'exec', '-T', 'nginx', 'nginx', '-t')
    compose(env, 'exec', '-T', 'nginx', 'nginx', '-s', 'reload')


def apply(values):
    original_path = BASE / '.env'
    original = original_path.read_text(encoding='utf-8')
    settings = dict(line.split('=', 1) for line in original.splitlines() if line and not line.startswith('#'))
    if settings.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
        raise RuntimeError('Unexpected personal deployment')
    if settings.get('OAUTH_REDIRECT_BASE_URL') != 'https://mujuthaek.vercel.app':
        raise RuntimeError('Unexpected OAuth callback origin')
    pending = private_file(merge(original, values))
    changed = False
    try:
        # Capture the resolved Compose data in memory; never print it.
        config = json.loads(compose(pending, 'config', '--format', 'json').stdout)
        environment = config['services']['api']['environment']
        if any(environment.get(name) != value for name, value in values.items()):
            raise RuntimeError('Compose did not bind all OAuth settings')
        os.replace(pending, original_path)
        changed = True
        restart(original_path)
        container = compose(original_path, 'ps', '-q', 'api').stdout.strip()
        result = subprocess.run(['docker', 'inspect', container], check=True, capture_output=True, text=True)
        actual = dict(entry.split('=', 1) for entry in json.loads(result.stdout)[0]['Config']['Env'])
        if any(actual.get(name) != value for name, value in values.items()):
            raise RuntimeError('API container did not receive all OAuth settings')
    except Exception:
        if changed:
            restore = private_file(original)
            os.replace(restore, original_path)
            try:
                restart(original_path)
            except Exception:
                raise RuntimeError('OAuth update failed and previous API recovery is unconfirmed') from None
        raise RuntimeError('OAuth update failed; previous configuration retained or restored') from None
    finally:
        pending.unlink(missing_ok=True)


def main():
    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the verified personal host')
    if INPUT.is_symlink() or not INPUT.is_file() or INPUT.stat().st_mode & 0o077:
        raise RuntimeError('OAuth input must be a private regular file')
    values = credentials(INPUT.read_text(encoding='utf-8-sig'))
    import fcntl
    with (BASE / 'runtime/releases/lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        apply(values)
    INPUT.unlink()
    print(json.dumps({'ok': True, 'providers': ['kakao', 'google'], 'api_health': 'UP',
                      'credential_values_printed': False, 'other_services_restarted': False}))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
