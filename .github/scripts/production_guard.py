"""Reject production deployment from direct pushes or PRs that bypassed dev."""
import json
import os
import subprocess

sha = os.environ['GITHUB_SHA']
repository = os.environ['GITHUB_REPOSITORY']
if repository != 'sangrock2/mujuthaek' or os.environ['GITHUB_REF'] != 'refs/heads/main':
    raise SystemExit('Only the personal repository main branch can deploy')
result = subprocess.run(['gh', 'api', f'repos/{repository}/commits/{sha}/pulls'],
                        check=True, capture_output=True, text=True)
prs = json.loads(result.stdout)
valid = any(pr.get('merged_at') and pr.get('merge_commit_sha') == sha and
            pr['base']['ref'] == 'main' and pr['head']['ref'] == 'dev' and
            (pr['head'].get('repo') or {}).get('full_name') == repository for pr in prs)
if not valid:
    raise SystemExit('Production requires a merged dev → main PR for this exact commit')
print('Validated production PR direction')
