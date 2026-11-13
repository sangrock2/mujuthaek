"""Coordinate a build/release or historical rollback; no DB restore is performed."""
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import backend_release as backend
import deployment_plan
import frontend_release as frontend


def smoke():
    for path, status in [('/', 200), ('/api/v1/regions', 200)]:
        with urllib.request.urlopen('https://mujuthaek.vercel.app' + path, timeout=30) as response:
            if response.status != status:
                raise RuntimeError('Public smoke check failed')
            if path.startswith('/api/'):
                if 'application/json' not in response.headers.get('Content-Type', ''):
                    raise RuntimeError('API returned an HTML page instead of JSON')
                json.load(response)


def frontend_source(data):
    info = data.get('frontend') or {}
    return info.get('commit', data.get('commit')) or info.get('id')


def archive_images(release, services):
    for service in services:
        subprocess.run(['docker', 'build', '--platform', 'linux/amd64', '-f',
                        f'backend/services/{service}/Dockerfile', '-t',
                        f'mujuthaek-personal-{service}:{release}', 'backend'], check=True)
    if not services:
        return
    with Path('images.tar.gz').open('wb') as output:
        save = subprocess.Popen(['docker', 'save', *(f'mujuthaek-personal-{s}:{release}' for s in services)], stdout=subprocess.PIPE)
        gzip = subprocess.run(['gzip', '-c'], stdin=save.stdout, stdout=output)
        save.stdout.close()
        if save.wait() or gzip.returncode:
            raise RuntimeError('Image archive failed')


def complete(release, info):
    Path('production-current.json').write_text(json.dumps({'release': release, 'frontend': info}))
    backend.put('releases/current.json', 'production-current.json')


def main():
    if os.environ['GITHUB_REPOSITORY'] != 'sangrock2/mujuthaek' or os.environ['GITHUB_REF'] != 'refs/heads/main':
        raise RuntimeError('Wrong repository/ref')
    request = 'run-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    rollback = os.environ.get('ROLLBACK_RELEASE', '')
    plan = deployment_plan.plan(os.environ['GITHUB_SHA'])
    base = json.loads(Path('base-release.json').read_text())
    if not rollback and not plan['components']:
        print('No runtime changes; deployment skipped')
        return
    frontend.remember_current()
    before = json.loads(Path('frontend-before.json').read_text())
    before['commit'] = (base.get('frontend') or {}).get('commit', base.get('commit'))
    if rollback:
        target = backend.get(f'releases/{backend.identity(rollback)}/manifest.json', 'target-release.json')
        change_frontend = frontend_source(base) != frontend_source(target)
        if change_frontend:
            frontend.restore_candidate()
            info = json.loads(Path('frontend-deployment.json').read_text())
            info['commit'] = (target.get('frontend') or {}).get('commit', target.get('commit'))
        else:
            info = before
        release = rollback
        selected = ['frontend'] if change_frontend else []
        selected += [s for s in ('api', 'notification') if target['images'][s] != base['images'][s]]
    else:
        selected = plan['components']
        change_frontend = 'frontend' in selected
        release = os.environ['GITHUB_SHA'] + '-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
        if change_frontend:
            frontend.candidate()
            info = json.loads(Path('frontend-deployment.json').read_text())
            info['commit'] = os.environ['GITHUB_SHA']
        else:
            info = before
        services = [s for s in ('api', 'notification') if s in selected]
        archive_images(release, services)
        backend.publish(release, os.environ['GITHUB_SHA'], base=base, services=services, frontend=info)
    Path('deployment-plan.json').write_text(json.dumps({**plan, 'components': selected}, indent=2))
    # A missing acknowledgement is uncertain, not evidence that the host failed.
    # Do not issue a competing recovery request on a result-download timeout.
    backend.request(release, 'rollback' if rollback else 'deploy', request, expected_base=base['release'])
    try:
        if change_frontend:
            frontend.promote()
        smoke()
        complete(release, info)
    except Exception:
        try:
            if change_frontend:
                frontend.restore_before()
        finally:
            backend.request(base['release'], 'rollback', request + '-recovery', expected_base=release)
        complete(base['release'], before)
        raise
    result = json.loads(Path('deployment-result.json').read_text())
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a', encoding='utf-8') as output:
            output.write(f"Release: `{result['release']}`\n\nPrevious: `{base['release']}`\n\nChanged: {', '.join(selected) or 'none'}\n\n")
            for service, image in result.get('images', {}).items():
                output.write(f"{service}: `{image['tag']}`\n\n")
            output.write(f"Frontend source: `{info.get('commit')}`\n\nFrontend: https://mujuthaek.vercel.app\n")


if __name__ == '__main__':
    main()
