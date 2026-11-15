"""Activate owner-approved web push without replacing existing keys or mail settings."""
import base64
import json
import os
import re
from pathlib import Path

from configure_collection import merge, private_file
from configure_oauth import compose, restart as restart_api
from configure_ses import restart as restart_notification

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
INPUT = Path('/home/ubuntu/.env.push')
PUBLIC = 'PUSH_VAPID_PUBLIC_KEY'
PRIVATE = 'PUSH_VAPID_PRIVATE_KEY'
SUBJECT = 'PUSH_VAPID_SUBJECT'


def credentials(text):
    values = {}
    for line in text.lstrip('\ufeff').splitlines():
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or key in values:
            raise ValueError('Invalid or duplicate push setting; values not displayed')
        values[key] = value
    if set(values) != {PUBLIC, PRIVATE, SUBJECT} or values[SUBJECT] != 'mailto:contact@mujuthaek.store':
        raise ValueError('Unexpected push settings; values not displayed')
    for key, length in ((PUBLIC, 65), (PRIVATE, 32)):
        value = values[key]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
            raise ValueError('Invalid VAPID key encoding')
        raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        if len(raw) != length or key == PUBLIC and raw[0] != 4:
            raise ValueError('Invalid VAPID key format')
    return values


def bind_environment(source, service, values):
    match = re.search(r'(?ms)^  ' + re.escape(service) + r':\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)', source)
    if not match or '    environment:\n' not in match[0]:
        raise RuntimeError('Service environment not found')
    section = match[0]
    for key in values:
        section = re.sub(r'(?m)^      ' + re.escape(key) + r':[^\n]*\n', '', section)
    entries = ''.join(f'      {key}: {value}\n' for key, value in values.items())
    section = section.replace('    environment:\n', '    environment:\n' + entries, 1)
    return source[:match.start()] + section + source[match.end():]


def manifest_settings(source):
    source = bind_environment(source, 'api', {PUBLIC: '${PUSH_VAPID_PUBLIC_KEY:-}'})
    return bind_environment(source, 'notification', {
        'NOTIFICATION_PUSH_PROVIDER': '${NOTIFICATION_PUSH_PROVIDER:-log}',
        PUBLIC: '${PUSH_VAPID_PUBLIC_KEY:-}', PRIVATE: '${PUSH_VAPID_PRIVATE_KEY:-}',
        SUBJECT: '${PUSH_VAPID_SUBJECT:-mailto:contact@mujuthaek.store}',
    })


def apply(values):
    env = BASE / '.env'
    manifest = BASE / 'compose.prod.yml'
    old_env, old_manifest = env.read_text(), manifest.read_text()
    previous = dict(line.split('=', 1) for line in old_env.splitlines() if '=' in line and not line.startswith('#'))
    if previous.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
        raise RuntimeError('Not the personal deployment')
    if previous.get(PUBLIC) and previous[PUBLIC] != values[PUBLIC]:
        raise RuntimeError('An existing VAPID key cannot be replaced by this installer')
    if previous.get(PRIVATE) and previous[PRIVATE] != values[PRIVATE]:
        raise RuntimeError('An existing VAPID key cannot be replaced by this installer')
    pending = private_file(merge(old_env, {**values, 'NOTIFICATION_PUSH_PROVIDER': 'webpush'}))
    changed = False
    try:
        os.replace(private_file(manifest_settings(old_manifest)), manifest)
        resolved = json.loads(compose(pending, 'config', '--format', 'json').stdout)['services']
        api, notification = resolved['api']['environment'], resolved['notification']['environment']
        if api.get(PUBLIC) != values[PUBLIC] or PRIVATE in api:
            raise RuntimeError('API public-only key forwarding failed')
        if any(notification.get(key) != value for key, value in values.items()) or notification.get('NOTIFICATION_PUSH_PROVIDER') != 'webpush':
            raise RuntimeError('Notification push forwarding failed')
        os.replace(pending, env)
        changed = True
        # Startup validates the P-256 key pair; failure restores the previous environment and manifest.
        restart_notification(env)
        restart_api(env)
    except Exception:
        os.replace(private_file(old_manifest), manifest)
        if changed:
            os.replace(private_file(old_env), env)
            restart_notification(env)
            restart_api(env)
        raise
    finally:
        pending.unlink(missing_ok=True)


def main():
    import fcntl
    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the personal deployment host')
    if INPUT.is_symlink() or not INPUT.is_file() or INPUT.stat().st_mode & 0o077:
        raise RuntimeError('Push input must be a private regular file')
    try:
        values = credentials(INPUT.read_text())
        with (BASE / 'runtime/releases/lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            apply(values)
    finally:
        INPUT.unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'push_provider': 'webpush', 'api_health': 'UP', 'notification_health': 'UP', 'device_receipt_pending': True}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Push configuration failed: ' + type(error).__name__ + '; key values not displayed') from None
