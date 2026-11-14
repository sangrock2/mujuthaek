"""Activate the owner-configured custom OAuth/frontend origin; preserve existing secrets."""
import json
import os
from pathlib import Path

from configure_collection import merge, private_file
from configure_oauth import compose, restart

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
ORIGIN = 'https://mujuthaek.store'


def main():
    import fcntl
    import subprocess

    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the personal deployment host')
    with (BASE / 'runtime/releases/lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        env = BASE / '.env'
        original = env.read_text()
        settings = dict(line.split('=', 1) for line in original.splitlines() if '=' in line and not line.startswith('#'))
        if settings.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
            raise RuntimeError('Wrong personal environment')
        subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '10',
                        'https://api.mujuthaek.store/actuator/health'], check=True, capture_output=True)
        origins = sorted({ORIGIN, 'https://mujuthaek.vercel.app', *filter(None, settings.get('CORS_ORIGINS', '').split(','))})
        updates = {'FRONTEND_URL': ORIGIN, 'OAUTH_REDIRECT_BASE_URL': ORIGIN, 'CORS_ORIGINS': ','.join(origins)}
        pending = private_file(merge(original, updates))
        changed = False
        try:
            resolved = json.loads(compose(pending, 'config', '--format', 'json').stdout)['services']['api']['environment']
            if any(resolved.get(name) != value for name, value in updates.items()):
                raise RuntimeError('Custom origin forwarding failed')
            os.replace(pending, env)
            changed = True
            restart(env)
            compose(env, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'notification')
        except Exception:
            if changed:
                os.replace(private_file(original), env)
                restart(env)
                compose(env, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'notification')
            raise
        finally:
            pending.unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'frontend_url': ORIGIN, 'oauth_base': ORIGIN, 'general_email_provider': settings.get('NOTIFICATION_MAIL_PROVIDER', 'log')}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Custom origin setup failed: ' + type(error).__name__) from None
