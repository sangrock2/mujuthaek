"""Switch publication after the owner reviews real samples; never display credentials."""
import argparse
import json
import os
from pathlib import Path

from configure_collection import BASE, compose, merge, private_file


def switch(mode, *, sample_reviewed=False):
    if mode not in ('manual', 'verified') or (mode == 'verified' and not sample_reviewed):
        raise ValueError('Verified publication requires explicit confirmation of real sample review')
    env = BASE / '.env'
    original = env.read_text(encoding='utf-8')
    values = dict(line.split('=', 1) for line in original.splitlines() if '=' in line and not line.startswith('#'))
    if values.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
        raise RuntimeError('Not the personal collection environment')
    pending = private_file(merge(original, {'EXTRACTION_PUBLICATION_MODE': mode}))
    try:
        config = json.loads(compose(pending, 'config', '--format', 'json').stdout)
        if config['services']['extraction']['environment'].get('EXTRACTION_PUBLICATION_MODE') != mode:
            raise RuntimeError('Publication mode was not bound')
        os.replace(pending, env)
        try:
            compose(env, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'extraction')
        except Exception:
            os.replace(private_file(original), env)
            compose(env, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'extraction')
            raise RuntimeError('Publication switch failed; previous settings restored') from None
        record = BASE / 'runtime/worker-current.json'
        if record.exists():
            data = json.loads(record.read_text())
            data['publication_mode'] = mode
            record.write_text(json.dumps(data))
    finally:
        pending.unlink(missing_ok=True)


def main():
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('manual', 'verified'))
    parser.add_argument('--sample-reviewed', action='store_true')
    args = parser.parse_args()
    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the verified personal host')
    with (BASE / 'runtime/releases/lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        switch(args.mode, sample_reviewed=args.sample_reviewed)
    print(json.dumps({'ok': True, 'publication_mode': args.mode, 'held_results_released': False}))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError):
        raise SystemExit('Publication switch failed; credential values were not displayed') from None
