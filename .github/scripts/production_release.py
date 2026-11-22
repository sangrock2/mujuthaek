"""Coordinate a build/release or historical rollback; no DB restore is performed."""
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from uuid import UUID

import backend_release as backend
import deployment_plan
import frontend_release as frontend


PUBLIC_ORIGIN = 'https://mujuthaek.vercel.app'
ACTIVE_NOTICES_PATH = '/api/v1/notices?field=HOUSING&statuses=APPLYING,UPCOMING,ALWAYS&size=1'


def public_json(origin, path, payload=None):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    request = urllib.request.Request(origin + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: expected HTTP 200, got {response.status}')
        if response.headers.get_content_type() != 'application/json':
            raise RuntimeError(f'{path}: expected a JSON response')
        return json.load(response)


def smoke_notice_journey(origin):
    page = public_json(origin, ACTIVE_NOTICES_PATH)
    items = page.get('items') if isinstance(page, dict) else None
    if not isinstance(items, list):
        raise RuntimeError('Public notice list response is missing items')
    if not items:
        print('Notice detail and related benefits skipped: no active public housing notices')
        return
    try:
        notice_id = str(UUID(items[0]['id']))
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise RuntimeError('Public notice list returned an invalid notice ID') from error
    detail = public_json(origin, f'/api/v1/notices/{notice_id}')
    header = detail.get('header') if isinstance(detail, dict) else None
    if (not isinstance(header, dict) or header.get('id') != notice_id or header.get('field') != 'HOUSING'
            or not isinstance(header.get('title'), str) or not header['title'].strip()):
        raise RuntimeError('Public housing notice detail did not match the selected notice')
    benefits = public_json(origin, f'/api/v1/eligibility/notices/{notice_id}/benefits', {'applicant': {}})
    if not isinstance(benefits, list) or any(
        not isinstance(item, dict) or not item.get('id') or not item.get('title')
        or item.get('overall') not in ('ELIGIBLE', 'NEEDS_INPUT') for item in benefits
    ):
        raise RuntimeError('Related benefits returned an invalid response')
    print(f'Public housing notice detail and related benefits verified ({len(benefits)} results)')


def smoke(*, check_notice_journey=False):
    for path, status in [('/', 200), ('/api/v1/regions', 200)]:
        with urllib.request.urlopen(PUBLIC_ORIGIN + path, timeout=30) as response:
            if response.status != status:
                raise RuntimeError('Public smoke check failed')
            if path.startswith('/api/'):
                if 'application/json' not in response.headers.get('Content-Type', ''):
                    raise RuntimeError('API returned an HTML page instead of JSON')
                json.load(response)
    if check_notice_journey:
        smoke_notice_journey(PUBLIC_ORIGIN)


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
        smoke(check_notice_journey='api' in selected and not rollback)
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
            # Host-written values: kept to one line without workflow command markers.
            for service, image in result.get('images', {}).items():
                output.write(f"{backend.log_safe(service, 32)}: `{backend.log_safe(image['tag'], 120)}`\n\n")
            output.write(f"Frontend source: `{info.get('commit')}`\n\nFrontend: https://mujuthaek.vercel.app\n")


if __name__ == '__main__':
    main()
