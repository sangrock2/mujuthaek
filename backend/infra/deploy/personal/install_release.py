"""Install the polling service; restore missing local state only from a verified archived baseline."""
import importlib.util
import json
import os
import subprocess
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
    # The polling identity cannot publish images or issue deployment requests.
    # Restore only an already archived baseline whose running images/schema match.
    data = module.manifest(json.loads(host.download('releases/20261113-1/manifest.json', 'initial-manifest.json').read_text()))
    state = json.loads(host.download('states/20261113-1.json', 'initial-state.json').read_text())
    if state['schema'] != host.schema():
        raise RuntimeError('Archived baseline schema differs; choose a recovery release explicitly')
    for service, image in data['images'].items():
        container = host.compose('ps', '-q', service).stdout.strip()
        actual = subprocess.run(['docker', 'inspect', '--format', '{{.Image}}', container],
                                check=True, capture_output=True, text=True).stdout.strip()
        if actual != image['id']:
            raise RuntimeError('Running image differs from archived baseline; stop for operator review')
    current.write_text(json.dumps(state))
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
