"""Use only the personal Vercel project; keep token values out of command output."""
import argparse
import json
import os
import re
import shutil
import tempfile
import subprocess
import urllib.request
from pathlib import Path

PROJECT = 'prj_TgaOO5IH8i8ETBXwM5bv2n7gtkj8'
TEAM = 'mujuthaek'


def vercel(*args, cwd=None):
    # The token is read by Vercel from the environment, not printed or embedded in artifacts.
    result = subprocess.run(['vercel', *args, '--scope', TEAM, '--yes', '--json', '--token', os.environ['VERCEL_TOKEN']], cwd=cwd,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Vercel operation failed; check token scope and deployment permissions')
    return json.loads(result.stdout)


def remember_current():
    url = f'https://api.vercel.com/v9/projects/{PROJECT}?teamId=team_BpOTTz4f6CcMVITAdEzieKXr'
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['VERCEL_TOKEN']})
    with urllib.request.urlopen(request, timeout=30) as response:
        project = json.load(response)
    if project['id'] != PROJECT:
        raise RuntimeError('Wrong Vercel project')
    current = project['targets']['production']
    Path('frontend-before.json').write_text(json.dumps({k: current[k] for k in ('id', 'url')}))


def restore_before():
    old = json.loads(Path('frontend-before.json').read_text())
    vercel('promote', old['url'])


def candidate(cwd=None):
    data = vercel('deploy', '--project', PROJECT, '--prod', '--skip-domain', cwd=cwd)
    deployment = data.get('deployment', data)
    if deployment.get('readyState') != 'READY':
        raise RuntimeError('Vercel build is not ready')
    Path('frontend-deployment.json').write_text(json.dumps({k: deployment[k] for k in ('id', 'url')}))


def restore_candidate():
    data = json.loads(Path('target-release.json').read_text())
    commit = data.get('commit')
    if commit and re.fullmatch('[0-9a-f]{40}', commit):
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'origin/main'], check=True)
        with tempfile.TemporaryDirectory() as directory:
            archive = subprocess.run(['git', 'archive', '--format=tar', commit], check=True, capture_output=True)
            subprocess.run(['tar', '-xf', '-', '-C', directory], input=archive.stdout, check=True)
            shutil.copyfile('.vercelignore', Path(directory) / '.vercelignore')
            candidate(cwd=directory)
    elif data.get('frontend'):
        # Initial local deployment has no Git SHA; promotion may be plan-limited.
        Path('frontend-deployment.json').write_text(json.dumps(data['frontend']))
    else:
        raise RuntimeError('This historical release has no frontend source/deployment record')


def promote():
    data = json.loads(Path('frontend-deployment.json').read_text())
    vercel('promote', data['url'])
    print('Promoted the selected personal frontend deployment')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('candidate', 'promote', 'restore-candidate', 'remember', 'restore-before'))
    action = p.parse_args().action
    if not os.environ.get('VERCEL_TOKEN'):
        raise SystemExit('Configure the VERCEL_TOKEN repository secret first')
    {'candidate': candidate, 'promote': promote, 'restore-candidate': restore_candidate, 'remember': remember_current, 'restore-before': restore_before}[action]()
