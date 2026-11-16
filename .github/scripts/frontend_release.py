"""Release the fixed Vercel project through the standard-library REST client."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import vercel_rest as rest

PROJECT, TEAM = rest.PROJECT, rest.TEAM


def remember_current():
    current = rest.project()['targets']['production']
    Path('frontend-before.json').write_text(json.dumps({k: current[k] for k in ('id', 'url')}))


def restore_before():
    old = json.loads(Path('frontend-before.json').read_text())
    rest.promote(old['id'])


def candidate(cwd=None, commit=None):
    if commit is None:
        commit = os.environ.get('GITHUB_SHA') or subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    value = rest.candidate(commit)
    Path('frontend-deployment.json').write_text(json.dumps({k: value[k] for k in ('id', 'url')}))


def restore_candidate():
    data = json.loads(Path('target-release.json').read_text())
    commit = (data.get('frontend') or {}).get('commit', data.get('commit'))
    if commit and re.fullmatch('[0-9a-f]{40}', commit):
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'origin/main'], check=True)
        candidate(commit=commit)
    elif data.get('frontend'):
        Path('frontend-deployment.json').write_text(json.dumps(data['frontend']))
    else:
        raise RuntimeError('This historical release has no frontend source/deployment record')


def promote():
    value = json.loads(Path('frontend-deployment.json').read_text())
    rest.promote(value['id'])
    print('Promoted the selected personal frontend deployment')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('candidate', 'promote', 'restore-candidate', 'remember', 'restore-before'))
    action = parser.parse_args().action
    if not os.environ.get('VERCEL_TOKEN'):
        raise SystemExit('Configure the VERCEL_TOKEN repository secret first')
    {'candidate': candidate, 'promote': promote, 'restore-candidate': restore_candidate,
     'remember': remember_current, 'restore-before': restore_before}[action]()
