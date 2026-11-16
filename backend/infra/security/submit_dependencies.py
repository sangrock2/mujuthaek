"""Publish resolved Maven runtime inventories; never execute downloaded artifact contents."""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO = 'sangrock2/mujuthaek'


def snapshot(directory, env):
    if env.get('GITHUB_REPOSITORY') != REPO or env.get('GITHUB_REF') != 'refs/heads/main':
        raise ValueError('Dependency submission requires the canonical main branch')
    if env.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch'):
        raise ValueError('Untrusted workflow event')
    sha = env.get('GITHUB_SHA', '')
    run_id = env.get('GITHUB_RUN_ID', '')
    attempt = env.get('GITHUB_RUN_ATTEMPT', '')
    if not re.fullmatch(r'[a-f0-9]{40}', sha) or not run_id.isdigit() or not attempt.isdigit():
        raise ValueError('Invalid workflow identity')
    manifests = {}
    for service in ('api', 'notification'):
        path = directory / f'{service}.json'
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError('Invalid inventory file')
        items = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(items, list) or not 1 <= len(items) <= 10_000:
            raise ValueError('Invalid inventory size')
        resolved = {}
        for item in items:
            package, version = item['package'], item['version']
            if package['ecosystem'] != 'Maven' or not isinstance(version, str):
                raise ValueError('Unexpected package ecosystem')
            parts = package['name'].split(':')
            if len(parts) != 2 or not all(re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in parts):
                raise ValueError('Invalid Maven coordinate')
            if not re.fullmatch(r'[A-Za-z0-9_.+~-]{1,128}', version):
                raise ValueError('Invalid Maven version')
            purl = f'pkg:maven/{quote(parts[0], safe=".")}/{quote(parts[1], safe="")}@{quote(version, safe="")}'
            # Inventory contains resolved runtime artifacts, not enough information to label edges direct/indirect.
            resolved[purl] = {'package_url': purl, 'scope': 'runtime'}
        name = f'backend/services/{service}/build.gradle'
        manifests[name] = {'name': name, 'file': {'source_location': name}, 'resolved': resolved}
    return {'version': 0, 'sha': sha, 'ref': 'refs/heads/main',
            'job': {'id': f'{run_id}-{attempt}', 'correlator': 'mujuthaek-resolved-maven-runtime',
                    'html_url': f'https://github.com/{REPO}/actions/runs/{run_id}'},
            'detector': {'name': 'mujuthaek-strict-gradle-inventory', 'version': '1',
                         'url': f'https://github.com/{REPO}/blob/{sha}/backend/infra/security/dependencies.init.gradle'},
            'scanned': datetime.now(timezone.utc).isoformat(), 'manifests': manifests}


def main():
    try:
        body = snapshot(Path('inventories'), os.environ)
        request = urllib.request.Request(
            f'https://api.github.com/repos/{REPO}/dependency-graph/snapshots',
            data=json.dumps(body).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                     'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
                     'X-GitHub-Api-Version': '2022-11-28'})
        # The provider origin is fixed; credentials must never follow redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            if response.status != 201:
                raise ValueError('Dependency submission was not accepted')
        print('Resolved runtime inventories submitted for API and notification.')
        return 0
    except Exception:
        print('Dependency submission failed; provider responses and credentials are withheld.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
