"""Bounded standard-library Vercel client. Credentials come only from the job's explicit environment."""
import json
import os
import re
import time
import urllib.error
import urllib.request

PROJECT = 'prj_TgaOO5IH8i8ETBXwM5bv2n7gtkj8'
TEAM = 'team_BpOTTz4f6CcMVITAdEzieKXr'
REPOSITORY = 1445740935


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def api(path, body=None, method=None):
    if any(os.environ.get(key) for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                                          'AWS_SESSION_TOKEN', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN')):
        raise RuntimeError('Run Vercel in a separate job without AWS or OIDC credentials')
    if not re.fullmatch(r'/v[0-9]+/[A-Za-z0-9/_-]+', path):
        raise ValueError('Invalid Vercel resource path')
    if method not in (None, 'GET', 'POST', 'PATCH'):
        raise ValueError('Unsupported Vercel operation')
    request = urllib.request.Request('https://api.vercel.com' + path + '?teamId=' + TEAM,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={'Authorization': 'Bearer ' + os.environ['VERCEL_TOKEN'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            content = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Vercel operation failed (HTTP {error.code}); response withheld') from None
    except (OSError, urllib.error.URLError):
        raise RuntimeError('Vercel operation failed; network details withheld') from None
    if len(content) > 2 * 1024 * 1024:
        raise RuntimeError('Vercel response limit exceeded')
    return json.loads(content) if content else {}


def project():
    result = api('/v9/projects/' + PROJECT)
    link = result.get('link') or {}
    if (result.get('id') != PROJECT or result.get('rootDirectory') != 'frontend'
            or link.get('type') != 'github' or str(link.get('repoId')) != str(REPOSITORY)):
        raise RuntimeError('Vercel project/source binding mismatch')
    return result


def deployment_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'dpl_[A-Za-z0-9]+', value):
        raise ValueError('Invalid deployment identity')
    return value


def checked_deployment(value, commit=None):
    deployment_id(value.get('id'))
    if value.get('projectId') != PROJECT or value.get('ownerId') != TEAM:
        raise RuntimeError('Deployment belongs to another project/team')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.vercel\.app', value.get('url', '')):
        raise RuntimeError('Unexpected deployment hostname')
    if commit and (value.get('meta') or {}).get('githubCommitSha') != commit:
        raise RuntimeError('Deployment source commit mismatch')
    return value


def candidate(commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit or ''):
        raise ValueError('A full source commit is required')
    before = ((project().get('targets') or {}).get('production') or {}).get('id')
    deployment_id(before)
    created = api('/v13/deployments', {'name': 'mujuthaek', 'project': PROJECT, 'target': 'production',
        'autoAssignCustomDomains': False,
        'projectSettings': {'rootDirectory': 'frontend', 'commandForIgnoringBuildStep': ''},
        'gitSource': {'type': 'github', 'repoId': str(REPOSITORY), 'ref': commit, 'sha': commit}})
    identity = deployment_id(created.get('id'))
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        value = checked_deployment(api('/v13/deployments/' + identity), commit)
        if value.get('readyState') == 'READY':
            current = ((project().get('targets') or {}).get('production') or {}).get('id')
            if current != before:
                raise RuntimeError('Production changed during candidate preparation')
            return value
        if value.get('readyState') in ('ERROR', 'CANCELED'):
            raise RuntimeError('Vercel candidate build failed; build output withheld')
        time.sleep(5)
    raise TimeoutError('Vercel candidate build outcome is uncertain')


def promote(identity):
    identity = deployment_id(identity)
    value = checked_deployment(api('/v13/deployments/' + identity))
    if value.get('readyState') != 'READY' or value.get('target') != 'production':
        raise RuntimeError('Only ready production builds may be promoted')
    project()
    api('/v10/projects/' + PROJECT + '/promote/' + identity, {})
    # Promotion resets this project setting. Keep future Git pushes behind release checks.
    api('/v9/projects/' + PROJECT, {'autoAssignCustomDomains': False}, method='PATCH')
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        current = (project().get('targets') or {}).get('production') or {}
        if current.get('id') == identity:
            return
        time.sleep(3)
    raise TimeoutError('Vercel promotion outcome is uncertain')
