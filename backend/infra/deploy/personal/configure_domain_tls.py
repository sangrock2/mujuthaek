"""Add the personal API DNS name to the existing short-lived IP certificate without stopping nginx."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from certificates import activate, certbot

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
DOMAIN = 'api.mujuthaek.store'
ADDRESS = '3.34.67.209'


def issuance_args(settings):
    if settings.get('identifier') != ADDRESS or settings.get('cert_name') != 'mujuthaek-prod':
        raise ValueError('Unexpected personal certificate lineage')
    return ['certonly', '--non-interactive', '--agree-tos', '--email', settings['email'],
            '--cert-name', settings['cert_name'], '--webroot', '--webroot-path', '/var/www/certbot',
            '--ip-address', ADDRESS, '-d', DOMAIN, '--preferred-profile', 'shortlived', '--expand']


def reload_nginx():
    command = ['docker', 'compose', '--env-file', '.env', '--env-file', 'versions.env', '-f', 'compose.prod.yml', 'exec', '-T', 'nginx', 'nginx']
    subprocess.run([*command, '-t'], cwd=BASE, check=True, capture_output=True)
    subprocess.run([*command, '-s', 'reload'], cwd=BASE, check=True, capture_output=True)


def main():
    import fcntl

    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the verified personal deployment host')
    settings_path = BASE / 'tls-settings.prod.json'
    settings = json.loads(settings_path.read_text())
    values = dict(line.split('=', 1) for line in (BASE / '.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    if values.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
        raise RuntimeError('Unexpected personal environment')
    arguments = issuance_args(settings)
    # Match the existing certificate renewal lock as well as the deployment lock.
    with (BASE / 'runtime/releases/lock').open('w') as deploy_lock, (BASE / '.tls.lock').open('w') as tls_lock:
        fcntl.flock(deploy_lock, fcntl.LOCK_EX)
        fcntl.flock(tls_lock, fcntl.LOCK_EX)
        old_target = os.readlink(BASE / 'tls/current')
        certbot(BASE, *arguments, '--dry-run')
        certbot(BASE, *arguments)
        certificate = BASE / 'letsencrypt/live' / settings['cert_name'] / 'cert.pem'
        subprocess.run(['openssl', 'verify', '-purpose', 'sslserver', '-verify_hostname', DOMAIN,
                        '-untrusted', str(certificate.parent / 'chain.pem'), str(certificate)], check=True, capture_output=True)
        try:
            activate(BASE, settings)
            reload_nginx()
        except Exception:
            pending = BASE / 'tls/.domain-rollback'
            pending.symlink_to(old_target)
            os.replace(pending, BASE / 'tls/current')
            reload_nginx()
            raise
        settings['domain_aliases'] = [DOMAIN]
        settings_path.write_text(json.dumps(settings, indent=2) + '\n')
        settings_path.chmod(0o600)
        # Certbot renewal remembers both SANs; the existing timer activates this same lineage.
        subprocess.run(['systemctl', 'is-enabled', 'mujuthaek-certbot-prod.timer'], check=True, capture_output=True)
    print(json.dumps({'ok': True, 'identifiers': [ADDRESS, DOMAIN], 'nginx_stopped': False, 'existing_renewal_timer': True}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Domain TLS setup failed: ' + type(error).__name__) from None
