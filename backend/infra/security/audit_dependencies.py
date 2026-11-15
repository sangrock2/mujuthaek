"""Audit exact resolved versions against OSV; fail closed on provider errors."""
import argparse
import json
import sys
import tomllib
import urllib.request
from pathlib import Path


def audit(packages):
    findings = []
    for start in range(0, len(packages), 100):
        batch = packages[start:start + 100]
        request = urllib.request.Request('https://api.osv.dev/v1/querybatch',
                                         data=json.dumps({'queries': batch}).encode(),
                                         headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=60) as response:
            results = json.load(response)['results']
        if len(results) != len(batch):
            raise ValueError('Incomplete vulnerability provider response')
        for package, result in zip(batch, results):
            if not isinstance(result, dict) or set(result) - {'vulns'}:
                raise ValueError('Incomplete or failed individual vulnerability query')
            if not isinstance(result.get('vulns', []), list):
                raise ValueError('Invalid vulnerability query result')
            for vulnerability in result.get('vulns', []):
                findings.append({'package': package['package']['name'], 'version': package['version'],
                                 'id': vulnerability['id']})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path, nargs='?')
    parser.add_argument('--uv-lock', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.uv_lock:
            unique = set()
            for path in args.uv_lock:
                lock = tomllib.loads(path.read_text(encoding='utf-8'))
                unique.update((package['name'], package['version']) for package in lock['package']
                              if 'registry' in package.get('source', {}))
            packages = [{'package': {'ecosystem': 'PyPI', 'name': name}, 'version': version}
                        for name, version in sorted(unique)]
        else:
            packages = json.loads(args.inventory.read_text(encoding='utf-8'))
        if not packages:
            raise ValueError('Empty inventory is not a successful audit')
        findings = audit(packages)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'packages_checked': len(packages), 'findings': findings}, indent=2), encoding='utf-8')
        print(f'Checked {len(packages)} resolved dependencies; findings: {len(findings)}.')
        for finding in findings:
            print(f'{finding["id"]}: {finding["package"]}@{finding["version"]}')
        return 1 if findings else 0
    except Exception:
        print('Vulnerability provider/inventory unavailable; check did not pass.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
