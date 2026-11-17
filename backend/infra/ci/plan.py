"""Select CI by changed inputs; never interpolate repository filenames into shell code."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

FLAGS = ('frontend', 'api', 'notification', 'collector', 'extraction', 'platform',
         'contracts', 'infra', 'gateway', 'broker', 'e2e', 'dependencies', 'workflows', 'full_secrets')
BACKEND = ('api', 'notification', 'collector', 'extraction', 'platform', 'infra', 'gateway', 'broker')


def validate(value):
    if not isinstance(value, dict) or set(value) != set(FLAGS) or any(type(x) is not bool for x in value.values()):
        raise ValueError('Invalid CI selection')
    return value


def affected(paths):
    selected = set()
    for path in paths:
        if not isinstance(path, str) or not path or path.startswith('/') or '..' in path.split('/'):
            raise ValueError('Invalid repository path')
        if path.startswith(('docs/', '.github/ISSUE_TEMPLATE/')) or path.endswith('.md') or path == 'LICENSE':
            continue
        name = path.rsplit('/', 1)[-1]
        if name in ('package.json', 'pnpm-lock.yaml', 'package-lock.json', 'uv.lock', 'pyproject.toml',
                    'requirements.txt', 'requirements-dev.txt', 'build.gradle.kts', 'settings.gradle.kts',
                    'gradle.properties', 'verification-metadata.xml', 'gradle-wrapper.properties', 'libs.versions.toml'):
            selected.add('dependencies')
        if path.startswith(('frontend/e2e/', 'backend/infra/e2e/')) or path.startswith('frontend/scripts/e2e'):
            selected.add('e2e')
        elif path.startswith('frontend/') or path == '.vercelignore':
            selected.add('frontend')
            if not path.startswith(('frontend/tests/', 'frontend/scripts/test-')):
                selected.add('e2e')
        elif path.startswith('backend/services/api/'):
            selected.add('api')
            if '/src/test/' not in path:
                selected.add('e2e')
        elif path.startswith('backend/services/notification/'):
            selected.add('notification')
        elif path.startswith('backend/services/collector/'):
            selected.add('collector')
        elif path.startswith('backend/services/extraction/'):
            selected.add('extraction')
            if path.startswith('backend/services/extraction/data/legal-dong-codes/'):
                selected.update(('api', 'e2e'))
        elif path.startswith('backend/libs/python-platform/'):
            selected.update(('platform', 'collector', 'extraction'))
            if any(x in path for x in ('outbox', 'managed_topology')):
                selected.add('broker')
        elif path.startswith('backend/libs/'):
            selected.update(('api', 'notification', 'e2e'))
        elif path.startswith('backend/gradle/') or path in ('backend/build.gradle.kts', 'backend/settings.gradle.kts', 'backend/gradle.properties'):
            selected.update(('api', 'notification', 'e2e', 'dependencies'))
        elif path.startswith('backend/contracts/'):
            selected.update(('contracts', 'api', 'notification', 'platform', 'collector', 'extraction', 'broker', 'e2e'))
        elif path == 'backend/.dockerignore':
            selected.update(('api', 'notification', 'collector', 'extraction', 'infra', 'e2e'))
        elif path.startswith('backend/infra/'):
            selected.add('infra')
            if any(x in path.lower() for x in ('nginx', 'caddy', 'gateway', 'verify_https', 'certificates', 'compose.prod')):
                selected.add('gateway')
            if path.endswith('dependencies.init.gradle'):
                selected.update(('api', 'notification', 'dependencies'))
            if any(x in path for x in ('service_isolation', 'compose.isolated', 'broker')):
                selected.add('broker')
        elif path.startswith('.github/workflows/'):
            selected.update(('workflows', 'infra', 'dependencies'))
            workflow_checks = {'web.yml': 'frontend', 'contracts.yml': 'contracts',
                               'collector-native.yml': 'collector', 'e2e.yml': 'e2e'}
            if name in workflow_checks:
                selected.add(workflow_checks[name])
            if name == 'workers.yml':
                selected.update(('collector', 'extraction'))
            if name == 'secret-scan.yml':
                selected.add('full_secrets')
        elif path.startswith('.github/scripts/'):
            selected.add('infra')
            if name in ('frontend_release.py', 'vercel_rest.py'):
                selected.update(('frontend', 'e2e'))
            if name in ('backend_release.py', 'release_phases.py', 'production_release.py'):
                selected.update(('frontend', 'api', 'notification', 'e2e'))
        elif path.startswith('.gitleaks'):
            selected.update(('infra', 'full_secrets'))
        elif path in ('.gitignore', '.gitattributes', 'CODEOWNERS') or path.startswith('.github/'):
            selected.add('infra')
        else:
            # A new shared build input must not silently lose coverage.
            selected.update(FLAGS)
    return {key: key in selected for key in FLAGS}


def changed(base, head):
    if not all(re.fullmatch('[0-9a-f]{40}', x or '') for x in (base, head)):
        raise ValueError('Expected full commit identities')
    merge_base = subprocess.check_output(['git', 'merge-base', base, head], text=True).strip()
    data = subprocess.check_output(['git', 'diff', '--no-renames', '--name-only', '-z', merge_base, head])
    return data.decode('utf-8').split('\0')[:-1], merge_base


def python_locks(paths):
    roots = ('backend/services/collector', 'backend/services/extraction', 'backend/libs/python-platform')
    return [root + '/uv.lock' for root in roots
            if any(path in (root + '/uv.lock', root + '/pyproject.toml') for path in paths)]


def emit(selection, base='', head='', paths=()):
    validate(selection)
    output = {key: str(value).lower() for key, value in selection.items()}
    output.update(selection=json.dumps(selection, separators=(',', ':')),
                  backend=str(any(selection[x] for x in BACKEND)).lower(),
                  java_any=str(selection['api'] or selection['notification']).lower(),
                  java_matrix=json.dumps([x for x in ('api', 'notification') if selection[x]] or ['api']),
                  python_locks=json.dumps(python_locks(paths)), base_sha=base, head_sha=head)
    if target := os.getenv('GITHUB_OUTPUT'):
        with open(target, 'a', encoding='utf-8') as stream:
            stream.writelines(f'{key}={value}\n' for key, value in output.items())
    print(json.dumps(selection, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base')
    parser.add_argument('--head')
    parser.add_argument('--deployment-plan', type=Path)
    parser.add_argument('--selection')
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    if args.selection:
        emit(validate(json.loads(args.selection)))
    elif args.deployment_plan:
        value = json.loads(args.deployment_plan.read_text())
        if not isinstance(value.get('paths'), list):
            raise ValueError('Missing deployment change inventory')
        selection = affected(value['paths'])
        for component in value.get('components', []):
            if component not in ('frontend', 'api', 'notification'):
                raise ValueError('Unknown deployment component')
            selection[component] = True
            if component in ('frontend', 'api'):
                selection['e2e'] = True
        emit(selection, paths=value['paths'])
    elif args.all:
        emit(dict.fromkeys(FLAGS, True))
    else:
        paths, base = changed(args.base, args.head)
        emit(affected(paths), base, args.head, paths)


if __name__ == '__main__':
    main()
