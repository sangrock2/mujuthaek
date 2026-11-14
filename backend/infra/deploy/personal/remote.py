"""SSH/SCP using only the temporary key and host keys obtained through authenticated AWS APIs."""
import argparse
import json
import subprocess
import re
import shlex
from datetime import datetime, timezone, timedelta
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / "runtime"


def run(action, value):
    endpoint = json.loads((RUNTIME / "endpoint.json").read_text())
    from aws_personal import AWS, INSTANCE
    if endpoint.get("instance") != INSTANCE:
        raise RuntimeError("Saved SSH target is not the active deployment; refresh access first")
    expires = endpoint.get("expires_at")
    if not expires or datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(timezone.utc) + timedelta(seconds=30):
        if not endpoint.get("profile") or not endpoint.get("account"):
            raise RuntimeError("Refresh SSH access with the selected personal profile first")
        AWS(endpoint["profile"], endpoint["account"]).access(instance=INSTANCE)
        endpoint = json.loads((RUNTIME / "endpoint.json").read_text())
    options = ["-i", str(RUNTIME / "ssh-key"), "-o", f"UserKnownHostsFile={RUNTIME / 'known_hosts'}",
               "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    target = f"{endpoint['user']}@{endpoint['host']}"
    if action == "exec":
        return subprocess.run(["ssh", *options, target, value]).returncode
    if action == "upload-private":
        source = Path(value)
        if source.is_symlink() or not source.is_file() or not re.fullmatch(r'[.A-Za-z0-9_-]+', source.name):
            raise ValueError("Private upload requires a regular file with a safe name")
        command = 'umask 077; set -C; cat > ' + shlex.quote('/home/ubuntu/' + source.name)
        with source.open('rb') as stream:
            return subprocess.run(["ssh", *options, target, command], stdin=stream).returncode
    return subprocess.run(["scp", *options, value, f"{target}:/home/ubuntu/{Path(value).name}"]).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["exec", "upload", "upload-private"])
    parser.add_argument("value")
    args = parser.parse_args()
    raise SystemExit(run(args.action, args.value))
