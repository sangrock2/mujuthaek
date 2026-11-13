"""Install the personal deployment's daily DB backup timer on its Linux host."""
import os
import subprocess
from pathlib import Path

BASE = Path("/opt/mujuthaek-source/backend/infra/deploy/personal")

if os.name != "posix" or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
    raise SystemExit("Run as root from the personal deployment directory on its Linux host")

service = f"""[Unit]
Description=Mujuthaek personal PostgreSQL backups to private S3
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory={BASE}
ExecStart=/bin/bash {BASE}/backup.sh
UMask=0077
TimeoutStartSec=15min
"""
timer = """[Unit]
Description=Daily Mujuthaek personal DB backup at 04:10 KST

[Timer]
OnCalendar=*-*-* 19:10:00 UTC
Persistent=true
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
"""
for suffix, body in [("service", service), ("timer", timer)]:
    target = Path(f"/etc/systemd/system/mujuthaek-personal-backup.{suffix}")
    target.write_text(body)
    target.chmod(0o644)
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run(["systemctl", "enable", "--now", "mujuthaek-personal-backup.timer"], check=True)
