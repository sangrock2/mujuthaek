"""Apply private, SES-only notification credentials; retain log mode until production approval."""
import json
import os
import re
import time
from pathlib import Path

from configure_collection import merge, private_file
from configure_oauth import compose

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
INPUT = Path('/home/ubuntu/.env.ses')
KEYS = ('NOTIFICATION_AWS_ACCESS_KEY_ID', 'NOTIFICATION_AWS_SECRET_ACCESS_KEY')


def notification_environment(source):
    """Image releases do not replace the host manifest; bind only this service's SES settings."""
    match = re.search(r'(?ms)^  notification:\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)', source)
    if not match or '    environment:\n' not in match[0]:
        raise RuntimeError('Notification service environment was not found')
    values = {
        'NOTIFICATION_MAIL_PROVIDER': '${NOTIFICATION_MAIL_PROVIDER:-log}',
        'NOTIFICATION_MAIL_FROM': '${NOTIFICATION_MAIL_FROM:-noreply@mujuthaek.store}',
        'NOTIFICATION_MAIL_FEEDBACK_ADDRESS': '${NOTIFICATION_MAIL_FEEDBACK_ADDRESS:-contact@mujuthaek.store}',
        'NOTIFICATION_MAIL_CONSENT_API_URL': 'http://api:8080',
        'AWS_REGION': 'ap-northeast-2',
        'AWS_ACCESS_KEY_ID': '${NOTIFICATION_AWS_ACCESS_KEY_ID:-}',
        'AWS_SECRET_ACCESS_KEY': '${NOTIFICATION_AWS_SECRET_ACCESS_KEY:-}',
    }
    section = match[0]
    for key in values:
        section = re.sub(r'(?m)^      ' + re.escape(key) + r':[^\n]*\n', '', section)
    entries = ''.join(f'      {key}: {value}\n' for key, value in values.items())
    section = section.replace('    environment:\n', '    environment:\n' + entries, 1)
    return source[:match.start()] + section + source[match.end():]


def credentials(text):
    values = dict(line.split('=', 1) for line in text.splitlines() if line and not line.startswith('#'))
    if set(values) != {*KEYS, 'NOTIFICATION_MAIL_PROVIDER'} or values['NOTIFICATION_MAIL_PROVIDER'] not in {'log', 'ses'}:
        raise ValueError('Invalid SES settings')
    if not re.fullmatch(r'AKIA[A-Z0-9]{16}', values[KEYS[0]]) or not re.fullmatch(r'[A-Za-z0-9/+=]{40}', values[KEYS[1]]):
        raise ValueError('Invalid SES credentials; values were not displayed')
    return values


def restart(env):
    compose(env, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'notification')
    for _ in range(30):
        try:
            result = compose(env, 'exec', '-T', 'nginx', 'wget', '-qO-', 'http://notification:8081/actuator/health')
            if json.loads(result.stdout).get('status') == 'UP':
                return
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError('Notification service did not become healthy')


def main():
    import fcntl

    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the personal deployment host')
    if INPUT.is_symlink() or not INPUT.is_file() or INPUT.stat().st_mode & 0o077:
        raise RuntimeError('SES input must be a private regular file')
    try:
        updates = credentials(INPUT.read_text()) | {'NOTIFICATION_MAIL_FROM': 'noreply@mujuthaek.store',
                    'NOTIFICATION_MAIL_FEEDBACK_ADDRESS': 'contact@mujuthaek.store'}
        with (BASE / 'runtime/releases/lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            env = BASE / '.env'
            original = env.read_text()
            settings = dict(line.split('=', 1) for line in original.splitlines() if '=' in line and not line.startswith('#'))
            if settings.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
                raise RuntimeError('Wrong personal environment')
            pending = private_file(merge(original, updates))
            manifest = BASE / 'compose.prod.yml'
            old_manifest = manifest.read_text()
            changed = False
            try:
                os.replace(private_file(notification_environment(old_manifest)), manifest)
                config = json.loads(compose(pending, 'config', '--format', 'json').stdout)['services']['notification']['environment']
                expected = {'AWS_ACCESS_KEY_ID': updates[KEYS[0]], 'AWS_SECRET_ACCESS_KEY': updates[KEYS[1]],
                            'NOTIFICATION_MAIL_PROVIDER': updates['NOTIFICATION_MAIL_PROVIDER']}
                if any(config.get(name) != value for name, value in expected.items()):
                    raise RuntimeError('Notification SES credential forwarding failed')
                os.replace(pending, env)
                changed = True
                restart(env)
            except Exception:
                os.replace(private_file(old_manifest), manifest)
                if changed:
                    os.replace(private_file(original), env)
                    restart(env)
                raise
            finally:
                pending.unlink(missing_ok=True)
    finally:
        INPUT.unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'mail_provider': updates['NOTIFICATION_MAIL_PROVIDER'], 'notification_health': 'UP'}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Notification SES setup failed: ' + type(error).__name__) from None
