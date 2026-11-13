"""Coordinate a build/release or historical rollback; no DB restore is performed."""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def run(script, *args):
    subprocess.run([sys.executable, str(SCRIPTS / script), *args], check=True)


def smoke():
    for path, status in [('/', 200), ('/api/v1/regions', 200)]:
        with urllib.request.urlopen('https://mujuthaek.vercel.app' + path, timeout=30) as response:
            if response.status != status:
                raise RuntimeError('Public smoke check failed')


def main():
    if os.environ['GITHUB_REPOSITORY'] != 'sangrock2/mujuthaek' or os.environ['GITHUB_REF'] != 'refs/heads/main':
        raise RuntimeError('Wrong repository/ref')
    request = 'run-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    run('frontend_release.py', 'remember')
    old = os.environ.get('ROLLBACK_RELEASE', '')
    if old:
        run('backend_release.py', 'info', old)
        run('frontend_release.py', 'restore-candidate')
        run('backend_release.py', 'rollback', old, '--request', request)
    else:
        release = os.environ['GITHUB_SHA'] + '-' + os.environ['GITHUB_RUN_ID']
        run('frontend_release.py', 'candidate')
        for service in ('api', 'notification'):
            subprocess.run(['docker', 'build', '--platform', 'linux/amd64', '-f',
                            f'backend/services/{service}/Dockerfile', '-t',
                            f'mujuthaek-personal-{service}:{release}', 'backend'], check=True)
        # No shell interpolation; stream the tar directly into gzip.
        with Path('images.tar.gz').open('wb') as output:
            save = subprocess.Popen(['docker', 'save', *(f'mujuthaek-personal-{s}:{release}' for s in ('api', 'notification'))], stdout=subprocess.PIPE)
            gzip = subprocess.run(['gzip', '-c'], stdin=save.stdout, stdout=output)
            save.stdout.close()
            if save.wait() or gzip.returncode:
                raise RuntimeError('Image archive failed')
        run('backend_release.py', 'publish', release, '--commit', os.environ['GITHUB_SHA'])
        run('backend_release.py', 'deploy', release, '--request', request)
    try:
        run('frontend_release.py', 'promote')
        smoke()
    except Exception:
        run('frontend_release.py', 'restore-before')
        # A migration/schema mismatch is deliberately refused by the host.
        previous = json.loads(Path('deployment-result.json').read_text()).get('previous')
        if previous:
            run('backend_release.py', 'rollback', previous, '--request', request + '-recovery')
        raise


if __name__ == '__main__':
    main()
