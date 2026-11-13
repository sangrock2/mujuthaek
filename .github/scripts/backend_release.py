"""Publish immutable images and request a deployment over private S3 using GitHub OIDC."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

BUCKET = 'mujuthaek-personal-659355919826-raw'


def aws(*args, capture=True):
    return subprocess.run(['aws', *args, '--region', 'ap-northeast-2'], check=True,
                          capture_output=capture, text=True)


def identity(value):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{6,95}', value):
        raise ValueError('Invalid release ID')
    return value


def get(key, destination):
    aws('s3', 'cp', f's3://{BUCKET}/deployments/{key}', str(destination), '--only-show-errors')
    return json.loads(Path(destination).read_text())


def put(key, source, immutable=False):
    args = ['s3api', 'put-object', '--bucket', BUCKET, '--key', 'deployments/' + key,
            '--body', str(source), '--server-side-encryption', 'AES256']
    if immutable:
        args += ['--if-none-match', '*']
    aws(*args)


def publish(release, commit):
    identity(release)
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Commit must be a full SHA')
    images = {}
    for service in ('api', 'notification'):
        tag = f'mujuthaek-personal-{service}:{release}'
        digest = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag],
                                check=True, capture_output=True, text=True).stdout.strip()
        images[service] = {'tag': tag, 'id': digest}
    with Path('images.tar.gz').open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    data = {'release': release, 'commit': commit, 'images': images, 'archive_sha256': digest}
    if Path('frontend-deployment.json').exists():
        data['frontend'] = json.loads(Path('frontend-deployment.json').read_text())
    Path('manifest.json').write_text(json.dumps(data))
    put(f'releases/{release}/images.tar.gz', 'images.tar.gz', immutable=True)
    put(f'releases/{release}/manifest.json', 'manifest.json', immutable=True)


def request(release, mode, request_id):
    identity(release)
    identity(request_id)
    if mode not in ('deploy', 'rollback'):
        raise ValueError('Unknown deployment mode')
    data = get(f'releases/{release}/manifest.json', 'target-release.json')
    if data['release'] != release:
        raise ValueError('Manifest mismatch')
    Path('desired.json').write_text(json.dumps({'release': release, 'mode': mode, 'request': request_id}))
    put('desired.json', 'desired.json')
    for _ in range(156):
        try:
            result = get(f'results/{request_id}.json', 'deployment-result.json')
        except subprocess.CalledProcessError:
            time.sleep(10)
            continue
        if result.get('request') != request_id or result.get('release') != release or not result.get('ok'):
            raise RuntimeError(f'Deployment failed: {result.get("message", "check server journal")}')
        print(json.dumps(result))
        return
    raise TimeoutError('Server did not acknowledge request; inspect status before retrying')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('publish', 'deploy', 'rollback', 'info'))
    parser.add_argument('release')
    parser.add_argument('--commit')
    parser.add_argument('--request')
    args = parser.parse_args()
    if args.action == 'publish':
        publish(args.release, args.commit)
    elif args.action == 'info':
        identity(args.release)
        get(f'releases/{args.release}/manifest.json', 'target-release.json')
    else:
        request(args.release, args.action, args.request)
