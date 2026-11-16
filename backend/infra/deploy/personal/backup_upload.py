"""Upload through the dedicated identity; never regenerate credentials from the app environment."""
import os
import json
import hashlib
import subprocess
import sys
from pathlib import Path

from release_host import AWS_IMAGE

MAX_SINGLE_PUT = 5 * 1024 ** 3


def upload_command(base, path):
    source = Path(path)
    backup = source.resolve()
    if source.is_symlink() or backup.parent != (base / 'runtime/backups').resolve() or not backup.name.endswith(('.dump', '.dump.cms')) or not backup.is_file():
        raise ValueError('Only deployment DB backup files can be uploaded')
    if backup.stat().st_size > MAX_SINGLE_PUT:
        raise ValueError('Backup exceeds the supported single-upload size; use a reviewed multipart path')
    env = base / 'runtime/backup-aws.env'
    # Missing backup credentials must fail closed rather than inherit the app's S3 key.
    values = dict(line.split('=', 1) for line in env.read_text().splitlines() if '=' in line)
    if not values.get('BACKUP_IDENTITY_ARN', '').endswith(':user/mujuthaek-personal-backup'):
        raise ValueError('Dedicated backup credentials are required')
    bucket = next(line.split('=', 1)[1] for line in (base / '.env').read_text().splitlines() if line.startswith('S3_BUCKET='))
    return ['docker', 'run', '--rm', '--pull', 'never', '--env-file', str(env),
            '--mount', f'type=bind,src={backup},dst=/backup.dump,readonly',
            AWS_IMAGE, 's3api', 'put-object', '--body', '/backup.dump',
            '--bucket', bucket, '--key', 'backups/' + backup.name,
            '--server-side-encryption', 'AES256', '--if-none-match', '*']


def upload_backup(base, path):
    source = Path(path).resolve()
    # Validate the source and dedicated identity before encryption or upload.
    upload_command(base, path)
    marker = base / 'runtime/backup-encryption.json'
    encrypted = None
    if marker.exists() or marker.is_symlink():
        if marker.is_symlink() or (os.name == 'posix' and (marker.stat().st_uid != 0 or marker.stat().st_mode & 0o077)):
            raise RuntimeError('Encryption activation must be private and root-owned')
        settings = json.loads(marker.read_text())
        certificate = base / 'runtime/backup-recipient.pem'
        if certificate.is_symlink() or not certificate.is_file() or settings.get('certificate_sha256') != hashlib.sha256(certificate.read_bytes()).hexdigest():
            raise RuntimeError('Backup recipient certificate does not match verified recovery escrow')
        if settings.get('format') != 'cms-aes256gcm-rsa-oaep-sha256-v1' or source.suffix != '.dump':
            raise RuntimeError('Unsupported backup encryption configuration')
        from backup_crypto import transform
        encrypted = source.with_suffix('.dump.cms')
        transform(source, encrypted, certificate)
    subprocess.run(upload_command(base, encrypted or source), check=True, timeout=600,
                   stdout=subprocess.DEVNULL)
    # A successful encrypted upload leaves only ciphertext on this host for new backups.
    if encrypted:
        source.unlink()


def main():
    base = Path(__file__).resolve().parent
    if os.name != 'posix' or os.geteuid() != 0:
        raise RuntimeError('Run only as root on the deployment host')
    credentials = base / 'runtime/backup-aws.env'
    if credentials.stat().st_uid != 0 or credentials.stat().st_mode & 0o077:
        raise RuntimeError('Backup credentials must be private and root-owned')
    upload_backup(base, sys.argv[1])


if __name__ == '__main__':
    main()
