"""A skipped check is acceptable only when the validated plan did not select it."""
import json
import os

from plan import BACKEND, validate


def verify(selection, results, backend=False, production=False):
    s = validate(selection)
    required = {'plan': True}
    if production:
        required.update({'web-check': s['frontend'], 'backend-check': any(s[x] for x in BACKEND),
                         'contracts-check': s['contracts'], 'e2e-check': s['e2e']})
    elif backend:
        required.update(java=s['api'] or s['notification'], collector=s['collector'],
                        extraction=s['extraction'], platform=s['platform'], infra=s['infra'], gateway=s['gateway'], broker=s['broker'])
    else:
        required.update(dependencies=s['dependencies'], web=s['frontend'],
                        backend=any(s[x] for x in BACKEND), contracts=s['contracts'],
                        e2e=s['e2e'], workflows=s['workflows'], secrets=True)
    for name, needed in required.items():
        expected = 'success' if needed else 'skipped'
        if results.get(name, {}).get('result') != expected:
            raise ValueError(f'CI gate: {name} must be {expected}')


if __name__ == '__main__':
    verify(json.loads(os.environ['CI_SELECTION']), json.loads(os.environ['CI_RESULTS']),
           os.getenv('CI_GATE') == 'backend', os.getenv('CI_GATE') == 'production')
    print('All selected checks passed; only unselected checks were skipped.')
