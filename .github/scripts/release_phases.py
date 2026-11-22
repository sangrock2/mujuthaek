"""Coordinate isolated frontend and AWS jobs without executing npm code in an OIDC job."""
import argparse
import json
import os
import re
from pathlib import Path

import backend_release as backend
import deployment_plan as planner
import frontend_release as frontend
import production_release as production


def read(name):
    return json.loads(Path(name).read_text(encoding='utf-8'))


def write(name, value):
    Path(name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def trusted_context(frontend_job=False):
    if os.environ.get('GITHUB_REPOSITORY') != 'sangrock2/mujuthaek' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise RuntimeError('Production requires the trusted repository and main branch')
    if frontend_job:
        if any(os.environ.get(name) for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                                                'AWS_SESSION_TOKEN', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN',
                                                'ACTIONS_ID_TOKEN_REQUEST_URL')):
            raise RuntimeError('Frontend tools must run in a job without AWS or OIDC credentials')
    elif os.environ.get('VERCEL_TOKEN'):
        raise RuntimeError('AWS release jobs must not receive the frontend deployment token')


def deployment(value, commit=None):
    """Treat npm-job artifacts as data; permit only the small expected deployment record."""
    if not isinstance(value, dict) or set(value) - {'id', 'url', 'commit'}:
        raise ValueError('Invalid frontend deployment record')
    if not isinstance(value.get('id'), str) or not re.fullmatch(r'dpl_[A-Za-z0-9_]{1,100}', value['id']):
        raise ValueError('Invalid frontend deployment ID')
    host = value.get('url')
    if (not isinstance(host, str) or len(host) > 253 or not host.endswith('.vercel.app')
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                   for label in host.split('.'))):
        raise ValueError('Invalid frontend deployment host')
    result = {'id': value['id'], 'url': value['url']}
    source = commit if commit is not None else value.get('commit')
    if commit is not None and value.get('commit') not in (None, commit):
        raise ValueError('Frontend deployment source disagrees with the planned source')
    if source is not None:
        if not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{40}', source):
            raise ValueError('Invalid frontend source commit')
        result['commit'] = source
    return result


def context():
    plan, base = read('deployment-plan.json'), read('base-release.json')
    if not isinstance(plan, dict) or not isinstance(base, dict):
        raise ValueError('Invalid plan or base release')
    if plan.get('base_release') != backend.identity(base['release']):
        raise ValueError('Plan and base release disagree')
    if (not isinstance(plan.get('commit'), str) or not re.fullmatch(r'[0-9a-f]{40}', plan['commit'])
            or plan.get('commit') != os.environ.get('GITHUB_SHA')):
        raise ValueError('Plan belongs to a different source commit')
    selected = plan.get('components')
    if (not isinstance(selected, list) or not all(isinstance(name, str) for name in selected)
            or len(selected) != len(set(selected)) or set(selected) - set(planner.COMPONENTS)):
        raise ValueError('Invalid selected components')
    if not isinstance(plan.get('rollback'), bool):
        raise ValueError('Rollback selection must be a boolean')
    release = backend.identity(plan['release'])
    return plan, base, release


def source_commit(manifest):
    return (manifest.get('frontend') or {}).get('commit') or manifest.get('commit')


def previous_frontend(base):
    before = deployment(read('frontend-before.json'), source_commit(base))
    if base.get('frontend'):
        expected = deployment(base['frontend'], source_commit(base))
        if before != expected:
            raise RuntimeError('Frontend production changed outside the planned release; reconcile first')
    return before


def selected_frontend(plan, base, release):
    if 'frontend' not in plan['components']:
        return deployment(base['frontend'], source_commit(base))
    expected_commit = plan['commit']
    if plan['rollback']:
        target = read('target-release.json')
        if target.get('release') != release:
            raise ValueError('Rollback manifest identity mismatch')
        expected_commit = source_commit(target)
    return deployment(read('frontend-deployment.json'), expected_commit)


def acknowledgement(plan, base, release):
    applied = read('backend-applied.json')
    request = backend.identity('run-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'])
    if (not isinstance(applied, dict) or applied.get('release') != release
            or applied.get('request') != request):
        raise ValueError('Backend acknowledgement belongs to another release request')
    info = deployment(applied['frontend'])
    if info != selected_frontend(plan, base, release):
        raise ValueError('Backend and frontend deployment records disagree')
    return applied, info


def plan_release():
    trusted_context()
    plan = planner.plan(os.environ['GITHUB_SHA'])
    base = read('base-release.json')
    rollback = os.environ.get('ROLLBACK_RELEASE', '')
    if rollback:
        release = backend.identity(rollback)
        target = backend.get(f'releases/{release}/manifest.json', 'target-release.json')
        if target.get('release') != release:
            raise ValueError('Rollback manifest identity mismatch')
        selected = ['frontend'] if production.frontend_source(base) != production.frontend_source(target) else []
        selected += [name for name in ('api', 'notification') if target['images'][name] != base['images'][name]]
    else:
        release = backend.identity(os.environ['GITHUB_SHA'] + '-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'])
        selected = plan['components']
    write('deployment-plan.json', dict(plan, release=release, rollback=bool(rollback), components=selected))
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write(f"deploy={str(bool(selected) or bool(rollback)).lower()}\nfrontend={str('frontend' in selected).lower()}\n")


def prepare_frontend():
    trusted_context(frontend_job=True)
    plan, base, release = context()
    frontend.remember_current()
    before = previous_frontend(base)
    write('frontend-before.json', before)
    info = before
    if 'frontend' in plan['components']:
        if plan['rollback']:
            target = read('target-release.json')
            if target.get('release') != release:
                raise ValueError('Rollback manifest identity mismatch')
            frontend.restore_candidate()
            commit = source_commit(target)
        else:
            frontend.candidate()
            commit = plan['commit']
        info = deployment(read('frontend-deployment.json'), commit)
    write('frontend-deployment.json', info)


def apply_backend():
    trusted_context()
    plan, base, release = context()
    previous_frontend(base)
    info = selected_frontend(plan, base, release)
    if not plan['rollback']:
        services = [name for name in ('api', 'notification') if name in plan['components']]
        production.archive_images(release, services)
        backend.publish(release, plan['commit'], base=base, services=services, frontend=info)
    request = 'run-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    # An uncertain acknowledgement is never converted into a competing rollback.
    backend.request(release, 'rollback' if plan['rollback'] else 'deploy', request, expected_base=base['release'])
    write('backend-applied.json', {'release': release, 'request': request, 'frontend': info})


def promote_frontend():
    trusted_context(frontend_job=True)
    plan, base, release = context()
    previous_frontend(base)
    _, info = acknowledgement(plan, base, release)
    # Normalize the provider-produced record again before the frontend helper reads it.
    write('frontend-deployment.json', info)
    change = 'frontend' in plan['components']
    outcome = {'release': release, 'ok': False, 'frontend_restored': not change}
    try:
        if change:
            frontend.promote()
        production.smoke(check_notice_journey='api' in plan['components'] and not plan['rollback'])
        outcome['ok'] = True
    except Exception:
        if change:
            try:
                frontend.restore_before()
                outcome['frontend_restored'] = True
            finally:
                write('frontend-outcome.json', outcome)
        raise
    finally:
        write('frontend-outcome.json', outcome)


def finalize_release():
    trusted_context()
    plan, base, release = context()
    before = previous_frontend(base)
    applied, info = acknowledgement(plan, base, release)
    outcome = read('frontend-outcome.json')
    if (not isinstance(outcome, dict) or set(outcome) != {'release', 'ok', 'frontend_restored'}
            or outcome.get('release') != release or not isinstance(outcome.get('ok'), bool)
            or not isinstance(outcome.get('frontend_restored'), bool)):
        raise ValueError('Release outcome identity mismatch')
    if outcome.get('ok') is True:
        production.complete(release, info)
        return
    if outcome.get('frontend_restored') is not True:
        # Keep the host at the applied release and the completion pointer at the base.
        # Their mismatch makes the next plan refuse to deploy until the frontend is reconciled.
        raise RuntimeError('Frontend recovery is uncertain; backend remains applied; reconcile before another release')
    backend.request(base['release'], 'rollback', applied['request'] + '-recovery', expected_base=release)
    production.complete(base['release'], before)
    raise RuntimeError('Frontend promotion failed; previous frontend and backend restored')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('plan', 'prepare-frontend', 'apply-backend', 'promote-frontend', 'finalize'))
    actions = {'plan': plan_release, 'prepare-frontend': prepare_frontend, 'apply-backend': apply_backend,
               'promote-frontend': promote_frontend, 'finalize': finalize_release}
    actions[parser.parse_args().phase]()
