"""Upload through the dedicated identity; never regenerate credentials from the app environment."""
import os
import subprocess
import sys
from pathlib import Path

MAX_SINGLE_PUT = 5 * 1024 ** 3


def upload_command(base, path):
    backup = Path(path).resolve()
    if backup.parent != (base / 'runtime/backups').resolve() or backup.suffix != '.dump' or not backup.is_file():
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
            'amazon/aws-cli:2.36.28', 's3api', 'put-object', '--body', '/backup.dump',
            '--bucket', bucket, '--key', 'backups/' + backup.name,
            '--server-side-encryption', 'AES256', '--if-none-match', '*']


def main():
    base = Path(__file__).resolve().parent
    if os.name != 'posix' or os.geteuid() != 0:
        raise RuntimeError('Run only as root on the deployment host')
    credentials = base / 'runtime/backup-aws.env'
    if credentials.stat().st_uid != 0 or credentials.stat().st_mode & 0o077:
        raise RuntimeError('Backup credentials must be private and root-owned')
    subprocess.run(upload_command(base, sys.argv[1]), check=True, timeout=600,
                   stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
