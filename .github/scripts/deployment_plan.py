"""Select runtime components against the last successfully completed release."""
import json
import os
import subprocess
from pathlib import Path

import backend_release as backend

COMPONENTS = ('frontend', 'api', 'notification')


def affected(paths):
    selected = set()
    for path in paths:
        if path.startswith(('docs/', '.github/ISSUE_TEMPLATE/')) or path.endswith('.md'):
            continue
        if '/src/test/' in path or '/src/e2e/' in path or path.startswith(('frontend/tests/', 'frontend/e2e/')):
            continue
        if path.startswith('frontend/') or path == '.vercelignore':
            selected.add('frontend')
        elif path.startswith('backend/services/api/'):
            selected.add('api')
        elif path.startswith('backend/services/notification/'):
            selected.add('notification')
        elif path.startswith('backend/services/extraction/data/legal-dong-codes/'):
            selected.add('api')
        elif path.startswith('backend/contracts/'):
            selected.update(('api', 'notification'))
        elif path.startswith('backend/libs/python-platform/'):
            continue
        elif path.startswith('backend/libs/') or path == 'backend/.dockerignore':
            selected.update(('api', 'notification'))
        elif path.startswith('.github/scripts/') or path in (
                '.github/workflows/production.yml', 'backend/infra/deploy/personal/release_host.py'):
            # Protocol changes exercise the full release path once.
            selected.update(COMPONENTS)
        elif path.startswith(('backend/infra/', 'backend/services/collector/', 'backend/services/extraction/', '.github/')):
            # Infrastructure and inactive workers have their own installation path.
            continue
        elif path in ('.gitignore', '.gitattributes', 'LICENSE', 'CODEOWNERS'):
            continue
        else:
            # Unknown shared build input: prefer an extra deployment to a missed one.
            selected.update(COMPONENTS)
    return [component for component in COMPONENTS if component in selected]


def changed_paths(base, target):
    subprocess.run(['git', 'merge-base', '--is-ancestor', base, target], check=True)
    # --no-renames reports both old and new paths for cross-service moves/deletions.
    result = subprocess.run(['git', 'diff', '--no-renames', '--name-only', '-z', base, target],
                            check=True, capture_output=True)
    return result.stdout.decode().split('\0')[:-1]


def plan(target):
    baseline = backend.get('releases/current.json', 'production-current.json')
    base = backend.get(f"releases/{backend.identity(baseline['release'])}/manifest.json", 'base-release.json')
    state = backend.get('states/current.json', 'server-current.json')
    if state.get('protocol', 1) < 2:
        raise RuntimeError('Install the selective-release host protocol before deployment')
    if state['release'] != base['release']:
        raise RuntimeError('Server and completed production release differ; reconcile the previous deployment first')
    source = base.get('commit')
    paths = changed_paths(source, target) if source else []
    selected = affected(paths) if source else list(COMPONENTS)
    return {'base_release': base['release'], 'commit': target, 'components': selected, 'paths': paths}


def main():
    if os.environ.get('ROLLBACK_RELEASE'):
        data = {'components': list(COMPONENTS), 'rollback': True}
    else:
        data = plan(os.environ['GITHUB_SHA'])
    Path('deployment-plan.json').write_text(json.dumps(data, indent=2))
    enabled = bool(data['components'])
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write(f"deploy={str(enabled).lower()}\n")
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write('Deployment plan: ' + (', '.join(data['components']) or 'skipped (no runtime changes)') + '\n')
    print(json.dumps(data))


if __name__ == '__main__':
    main()
