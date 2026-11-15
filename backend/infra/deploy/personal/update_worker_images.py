"""Update already configured worker images without changing credentials, budgets or publication mode."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time

from configure_collection import BASE, merge, private_file
from release_host import Host

WORKERS = ('extraction', 'collector')


def updated_settings(original, release):
    if not re.fullmatch(r'[0-9a-f]{40}', release):
        raise ValueError('Worker release must be a full commit ID')
    return merge(original, {'COLLECTOR_RELEASE': release, 'EXTRACTION_RELEASE': release})


def compose(host, *args):
    return host.compose('--profile', 'workers', *args, timeout=120)


def migration_hash(image):
    program = "from pathlib import Path; import hashlib; p=Path('migrations'); files=sorted(p.glob('V*.sql')); assert files; print(hashlib.sha256(b''.join(f.name.encode()+b'\\0'+f.read_bytes() for f in files)).hexdigest())"
    result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                             '--security-opt', 'no-new-privileges', '--cpus', '0.10', '--memory', '64m',
                             '--entrypoint', 'python', image, '-c', program],
                            capture_output=True, text=True, check=True, timeout=120)
    value = result.stdout.strip()
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise RuntimeError('Worker migration fingerprint unavailable')
    return value


def wait_worker(host, service):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        ids = compose(host, 'ps', '-q', service).stdout.split()
        if len(ids) != 1:
            raise RuntimeError('Expected exactly one worker container')
        info = json.loads(subprocess.run(['docker', 'inspect', ids[0]], capture_output=True,
                                        text=True, check=True, timeout=15).stdout)[0]
        if info['State'].get('Health', {}).get('Status') == 'healthy':
            return
        if not info['State']['Running']:
            raise RuntimeError('Worker exited before becoming healthy')
        time.sleep(5)
    raise RuntimeError('Worker readiness deadline exceeded')


def update(host, release):
    path = BASE / '.env'
    original = path.read_text(encoding='utf-8')
    new_text = updated_settings(original, release)
    config = json.loads(compose(host, 'config', '--format', 'json').stdout)['services']
    for service in WORKERS:
        if not config[service]['image'].startswith('mujuthaek-personal-' + service + ':'):
            raise RuntimeError('Unexpected existing worker image')
    checksum = host.download(f'releases/workers/{release}/worker-images.sha256', f'workers-{release}.sha256').read_text().split()[0]
    if not re.fullmatch(r'[0-9a-f]{64}', checksum):
        raise RuntimeError('Invalid worker archive checksum')
    with host.worker_cpu_budget():
        archive = host.download(f'releases/workers/{release}/worker-images.tar.gz', f'workers-{release}.tar.gz')
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != checksum:
                raise RuntimeError('Worker archive checksum mismatch')
        subprocess.run(['docker', 'load', '-i', str(archive)], capture_output=True, check=True, timeout=600)
    # This helper performs image-only updates. Schema changes need the dedicated migration path.
    for service in WORKERS:
        new_image = f'mujuthaek-personal-{service}:{release}'
        if migration_hash(config[service]['image']) != migration_hash(new_image):
            raise RuntimeError('Worker database migrations changed; image-only update refused')
    pending = private_file(new_text)
    changed = False
    try:
        os.replace(pending, path)
        changed = True
        proposed = json.loads(compose(host, 'config', '--format', 'json').stdout)['services']
        for service in WORKERS:
            if proposed[service]['image'] != f'mujuthaek-personal-{service}:{release}':
                raise RuntimeError('Worker release was overridden by another environment file')
            if proposed[service]['environment'] != config[service]['environment']:
                raise RuntimeError('Worker environment changed; update refused')
        for service in WORKERS:
            compose(host, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', service)
            wait_worker(host, service)
    except Exception:
        if changed:
            restore = private_file(original)
            os.replace(restore, path)
            for service in WORKERS:
                compose(host, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', service)
                wait_worker(host, service)
        raise
    finally:
        pending.unlink(missing_ok=True)
    record = BASE / 'runtime/worker-current.json'
    previous = json.loads(record.read_text()) if record.exists() else {}
    record.write_text(json.dumps({**previous, 'commit': release, 'archive_sha256': checksum, 'image_only_update': True}))
    print('Worker images updated and healthy; previous runtime settings preserved.')


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True)
    args = parser.parse_args()
    updated_settings('', args.release)
    if os.name != 'posix' or os.geteuid() != 0:
        raise RuntimeError('Run only as root on the verified personal host')
    with (BASE / 'runtime/releases/lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        update(Host(), args.release)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Worker image update failed; inspect private host status before retrying.') from None
