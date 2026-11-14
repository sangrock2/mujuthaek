"""Connect personal address keys without logging values; coordinates may remain pending."""
import json
import os
import re
from pathlib import Path

from configure_collection import merge, private_file
from configure_oauth import compose, restart

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
INPUT = Path('/home/ubuntu/.env.maps')
KEYS = ('NEXT_PUBLIC_KAKAO_MAP_KEY', 'JUSO_SEARCH_API_KEY', 'JUSO_COORD_API_KEY')


def credentials(text):
    values = {}
    for line in text.lstrip('\ufeff').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if not separator or name not in KEYS or name in values or not re.fullmatch(r'[A-Za-z0-9._%/+=-]*', value):
            raise ValueError('Invalid map configuration; values were not displayed')
        values[name] = value
    if not re.fullmatch(r'[0-9a-fA-F]{32}', values.get(KEYS[0], '')) or not values.get(KEYS[1]):
        raise ValueError('Map JavaScript key and address search key are required; values were not displayed')
    values.setdefault(KEYS[2], '')
    return values


def apply(values):
    env = BASE / '.env'
    original = env.read_text(encoding='utf-8')
    settings = dict(line.split('=', 1) for line in original.splitlines() if '=' in line and not line.startswith('#'))
    if settings.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
        raise RuntimeError('Not the personal deployment')
    # An unapproved/blank coordinate key must not erase an existing working one.
    updates = {name: values[name] for name in KEYS[1:] if values[name]}
    pending = private_file(merge(original, updates))
    changed = False
    try:
        resolved = json.loads(compose(pending, 'config', '--format', 'json').stdout)['services']['api']['environment']
        if any(resolved.get(name) != value for name, value in updates.items()):
            raise RuntimeError('Address key forwarding failed')
        os.replace(pending, env)
        changed = True
        restart(env)
    except Exception:
        if changed:
            os.replace(private_file(original), env)
            restart(env)
        raise RuntimeError('Address configuration failed; previous settings retained or restored') from None
    finally:
        pending.unlink(missing_ok=True)


def main():
    import fcntl

    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the verified personal host')
    if INPUT.is_symlink() or not INPUT.is_file() or INPUT.stat().st_mode & 0o077:
        raise RuntimeError('Map input must be a private regular file')
    try:
        values = credentials(INPUT.read_text(encoding='utf-8-sig'))
        with (BASE / 'runtime/releases/lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            apply(values)
    finally:
        INPUT.unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'address_search_configured': True,
                      'coordinate_key_supplied': bool(values['JUSO_COORD_API_KEY']), 'api_health': 'UP'}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Map configuration failed; credential values were not displayed') from None
