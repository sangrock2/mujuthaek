"""Install the polling release service and register the existing images as the first rollback point."""
import gzip
import importlib.util
import json
import os
import subprocess
import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
if BASE != Path('/opt/mujuthaek-source/backend/infra/deploy/personal') or os.geteuid() != 0:
    raise SystemExit('Run as root on the personal host')
spec = importlib.util.spec_from_file_location('release_host', BASE / 'release_host.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
host = module.Host()
current = host.runtime / 'current.json'
if not current.exists():
    release = '20261113-1'
    archive = host.runtime / 'images.tar.gz'
    tags = [f'mujuthaek-personal-{s}:{release}' for s in module.SERVICES]
    with archive.open('wb') as output:
        save = subprocess.Popen(['docker', 'save', *tags], stdout=subprocess.PIPE)
        zipped = subprocess.run(['gzip', '-c'], stdin=save.stdout, stdout=output)
        save.stdout.close()
        if save.wait() or zipped.returncode:
            raise RuntimeError('Cannot archive initial images')
    images = {s: {'tag': tag, 'id': subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag],
              check=True, capture_output=True, text=True).stdout.strip()} for s, tag in zip(module.SERVICES, tags)}
    with archive.open('rb') as source:
        checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    data = module.manifest({'release': release, 'commit': None, 'images': images, 'archive_sha256': checksum,
                           'frontend': {'id': 'dpl_6NSfrXQhmjKTLFiT2u2qskEJqQRb',
                                        'url': 'https://mujuthaek-123tduo8i-mujuthaek.vercel.app'}})
    (host.runtime / 'manifest.json').write_text(json.dumps(data))
    host.upload('images.tar.gz', f'releases/{release}/images.tar.gz')
    host.upload('manifest.json', f'releases/{release}/manifest.json')
    state = {'release': release, 'previous': None, 'schema': host.schema(), 'commit': None}
    current.write_text(json.dumps(state))
    (host.runtime / 'state.json').write_text(json.dumps(state))
    host.upload('state.json', f'states/{release}.json')
    (host.runtime / 'desired.json').write_text(json.dumps({'request': 'initial-registration', 'mode': 'deploy', 'release': release}))
    host.upload('desired.json', 'desired.json')
    (host.runtime / 'last-request').write_text('initial-registration')
service = f'''[Unit]
Description=Mujuthaek release requests from private S3
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory={BASE}
ExecStart=/usr/bin/python3 {BASE}/release_host.py
UMask=0077
TimeoutStartSec=25min
'''
timer = '''[Unit]
Description=Check Mujuthaek release request every minute

[Timer]
OnBootSec=1min
OnUnitInactiveSec=1min

[Install]
WantedBy=timers.target
'''
for suffix, body in [('service', service), ('timer', timer)]:
    p = Path('/etc/systemd/system/mujuthaek-personal-release.' + suffix)
    p.write_text(body)
    p.chmod(0o644)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'enable', '--now', 'mujuthaek-personal-release.timer'], check=True)
print(json.dumps({'initial_release': host.current()['release'], 'timer': 'installed', 'existing_containers_restarted': False}))
