"""Install a backup-only key after verifying its identity and a synthetic S3 read/write."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
import time
import re
from pathlib import Path

from configure_collection import BASE
from release_host import AWS_IMAGE, Host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--uploader-sha256', required=True)
    parser.add_argument('--script-sha256', required=True)
    args = parser.parse_args()
    source = args.input
    host = Host()
    if source.is_symlink() or not source.is_file() or source.resolve().parent != Path('/home/ubuntu') or source.stat().st_mode & 0o077:
        raise RuntimeError('Expected a private regular staging file on the verified host')
    data = dict(line.split('=', 1) for line in source.read_text(encoding='utf-8').splitlines() if '=' in line)
    expected = {'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION', 'S3_BUCKET', 'BACKUP_IDENTITY_ARN'}
    if set(data) != expected or data['S3_BUCKET'] != host.bucket or data['AWS_REGION'] != 'ap-northeast-2':
        raise RuntimeError('Backup destination does not match the verified deployment')
    if not data['BACKUP_IDENTITY_ARN'].endswith(':user/mujuthaek-personal-backup'):
        raise RuntimeError('Unexpected backup identity')
    staged = {}
    for name, expected_hash in [('backup_upload.py', args.uploader_sha256), ('backup.sh', args.script_sha256)]:
        file = Path('/home/ubuntu') / name
        if file.is_symlink() or not file.is_file() or not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
            raise RuntimeError('Expected reviewed backup source files')
        content = file.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise RuntimeError('Backup source checksum mismatch')
        staged[name] = content
    compile(staged['backup_upload.py'], 'backup_upload.py', 'exec')
    subprocess.run(['bash', '-n', '/home/ubuntu/backup.sh'], check=True, capture_output=True)
    import fcntl
    with (BASE / 'runtime/releases/lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        timer = 'mujuthaek-personal-backup.timer'
        timer_active = subprocess.run(['systemctl', 'is-active', '--quiet', timer]).returncode == 0
        if timer_active:
            subprocess.run(['systemctl', 'stop', timer], check=True)
        try:
            deadline = time.monotonic() + 900
            while subprocess.run(['systemctl', 'is-active', '--quiet', 'mujuthaek-personal-backup.service']).returncode == 0:
                if time.monotonic() > deadline:
                    raise RuntimeError('Existing backup is still running; cutover deferred')
                time.sleep(5)
            with (BASE / 'runtime/backup.lock').open('w') as backup_lock:
                fcntl.flock(backup_lock, fcntl.LOCK_EX)
                install(source, data, host, staged)
        finally:
            if timer_active:
                subprocess.run(['systemctl', 'start', timer], check=True)
    source.unlink()


def replace_private(path, content, mode):
    descriptor, temporary = tempfile.mkstemp(prefix='.backup-install-', dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(source, data, host, staged):
    target = BASE / 'runtime/backup-aws.env'
    original = target.read_bytes()
    original_sources = {name: (BASE / name).read_bytes() for name in staged}
    with tempfile.TemporaryDirectory(prefix='backup-probe-', dir=BASE / 'runtime') as temporary:
        probe = Path(temporary)
        body = probe / 'probe.json'
        body.write_text('{"purpose":"backup-permission-check"}', encoding='utf-8')
        def aws(credentials, *command):
            result = subprocess.run(['docker', 'run', '--rm', '--pull', 'never', '--env-file', str(credentials),
                '--mount', f'type=bind,src={probe},dst=/probe', AWS_IMAGE, *command],
                capture_output=True, text=True, check=True, timeout=120)
            return json.loads(result.stdout or '{}')
        identity = aws(source, 'sts', 'get-caller-identity')
        if identity['Arn'] != data['BACKUP_IDENTITY_ARN']:
            raise RuntimeError('Backup credentials do not match expected identity')
        key = 'backups/security-checks/' + uuid.uuid4().hex + '.json'
        aws(source, 's3api', 'put-object', '--bucket', host.bucket, '--key', key,
            '--body', '/probe/probe.json', '--server-side-encryption', 'AES256', '--if-none-match', '*')
        aws(source, 's3api', 'get-object', '--bucket', host.bucket, '--key', key, '/probe/received.json')
        if (probe / 'received.json').read_bytes() != body.read_bytes():
            raise RuntimeError('Backup read/write verification failed')
        try:
            aws(source, 's3api', 'put-object', '--bucket', host.bucket, '--key', key,
                '--body', '/probe/probe.json', '--server-side-encryption', 'AES256', '--if-none-match', '*')
        except subprocess.CalledProcessError as error:
            if 'PreconditionFailed' not in error.stderr:
                raise
        else:
            raise RuntimeError('Backup overwrite protection was not enforced')
        descriptor, temporary_env = tempfile.mkstemp(prefix='.backup-aws-', dir=target.parent)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write(''.join(f'{name}={data[name]}\n' for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION', 'BACKUP_IDENTITY_ARN')))
        try:
            for name, content in staged.items():
                replace_private(BASE / name, content, 0o700 if name.endswith('.sh') else 0o600)
            os.replace(temporary_env, target)
            if aws(target, 'sts', 'get-caller-identity')['Arn'] != identity['Arn']:
                raise RuntimeError('Installed backup identity differs')
        except Exception:
            target.write_bytes(original)
            target.chmod(0o600)
            for name, content in original_sources.items():
                replace_private(BASE / name, content, 0o700 if name.endswith('.sh') else 0o600)
            raise
        finally:
            Path(temporary_env).unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'get_put_verified': True, 'overwrite_blocked': True,
        'bucket_fingerprint': hashlib.sha256(host.bucket.encode()).hexdigest(),
        'identity_fingerprint': hashlib.sha256(identity['Arn'].encode()).hexdigest(),
        'key_fingerprint': hashlib.sha256(data['AWS_ACCESS_KEY_ID'].encode()).hexdigest()}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Backup credential cutover failed; app permissions must remain unchanged.') from None
