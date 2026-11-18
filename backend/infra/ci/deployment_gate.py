"""Fail a release that only prepared artifacts but never applied/promoted/finalized them."""
import json
import os

STAGES = ('frontend-prepare', 'backend-apply', 'frontend-promote', 'finalize')


def verify(deploy, needs):
    if not isinstance(needs, dict) or deploy not in ('true', 'false'):
        raise ValueError('Missing or invalid release evidence')
    for name in ('guard', 'plan'):
        if not isinstance(needs.get(name), dict) or needs[name].get('result') != 'success':
            raise ValueError('Release guard or plan did not succeed')
    expected = 'success' if deploy == 'true' else 'skipped'
    for name in STAGES:
        if not isinstance(needs.get(name), dict) or needs[name].get('result') != expected:
            raise ValueError('Release phase did not reach the expected outcome: ' + name)


if __name__ == '__main__':
    verify(os.environ.get('RELEASE_DEPLOY'), json.loads(os.environ['RELEASE_RESULTS']))
    print('Release execution evidence verified.')
