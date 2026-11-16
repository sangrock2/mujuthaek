"""Validate then reload only the personal Nginx config, with a private rollback copy."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
CONTAINER = 'mujuthaek-personal-nginx-1'


def command(*args, text=None):
    result = subprocess.run(args, input=text, capture_output=True, text=True, encoding='utf-8', timeout=45)
    if result.returncode:
        raise RuntimeError('Gateway operation failed: ' + result.stderr[-800:])
    return result.stdout


def main():
    if os.name != 'posix' or os.geteuid() != 0 or not BASE.is_dir():
        raise RuntimeError('Run only on the verified personal deployment host')
    target = BASE / 'nginx/default.conf'
    candidate = Path('/home/ubuntu/gateway-audit.conf')
    if target.is_symlink() or candidate.is_symlink() or not candidate.is_file():
        raise RuntimeError('Expected regular gateway files')
    mounts = json.loads(command('docker', 'inspect', '--format', '{{json .Mounts}}', CONTAINER))
    if not any(m['Destination'] == '/etc/nginx/conf.d/default.conf' and m['Source'] == str(target) for m in mounts):
        raise RuntimeError('Gateway config mount differs')
    command('docker', 'cp', str(candidate), CONTAINER + ':/tmp/gateway-audit.conf')
    config = command('docker', 'exec', CONTAINER, 'cat', '/etc/nginx/nginx.conf')
    include = 'include /etc/nginx/conf.d/*.conf;'
    if config.count(include) != 1:
        raise RuntimeError('Inspect nonstandard Nginx configuration')
    command('docker', 'exec', '-i', CONTAINER, 'sh', '-c', 'cat > /tmp/nginx.audit.conf',
            text=config.replace(include, 'include /tmp/gateway-audit.conf;'))
    command('docker', 'exec', CONTAINER, 'nginx', '-t', '-c', '/tmp/nginx.audit.conf')
    before = target.read_bytes()
    backup = BASE / 'runtime/gateway-before-hardening.conf'
    if not backup.exists():
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(before)
    try:
        # Preserve the bind-mounted inode; replacing the host inode would leave Nginx on the old file.
        target.write_bytes(candidate.read_bytes())
        command('docker', 'exec', CONTAINER, 'nginx', '-t')
        command('docker', 'exec', CONTAINER, 'nginx', '-s', 'reload')
        code = command('curl', '--silent', '--show-error', '--output', '/dev/null', '--write-out', '%{http_code}',
                       '--max-time', '15', '--resolve', 'api.mujuthaek.store:443:127.0.0.1',
                       'https://api.mujuthaek.store/actuator/health').strip()
        if code != '200':
            raise RuntimeError('Gateway health check failed')
    except Exception:
        target.write_bytes(before)
        command('docker', 'exec', CONTAINER, 'nginx', '-s', 'reload')
        raise
    print(json.dumps({'ok': True, 'nginx_preflight': True, 'health': 200, 'app_restarts': 0,
                      'config_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
