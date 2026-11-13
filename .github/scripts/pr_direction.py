"""Validate PR direction without running code from the PR."""
import json
import os


def allowed(event, repository):
    pr = event['pull_request']
    base = pr['base']['ref']
    head = pr['head']
    same = (head.get('repo') or {}).get('full_name') == repository
    return base == 'dev' or (base == 'main' and same and head['ref'] == 'dev')


if __name__ == '__main__':
    with open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8') as source:
        event = json.load(source)
    if not allowed(event, os.environ['GITHUB_REPOSITORY']):
        raise SystemExit('PRs must target dev; main accepts only this repository’s dev branch.')
