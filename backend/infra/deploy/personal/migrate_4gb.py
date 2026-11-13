"""Prepare a verified personal 4GB target and transport over AWS-authenticated SSH only."""
import argparse
import ipaddress
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from aws_personal import AWS, BASE, RUNTIME

OLD = "mujuthaek-personal-20261113"
NEW = OLD + "-4gb"


def aws():
    return AWS("mujuthaek", "659355919826")


def require_owned(client, name):
    instance = client.call("lightsail", "get-instance", "--instance-name", name)["instance"]
    if not any(t["key"] == "Project" and t.get("value") == "mujuthaek-personal" for t in instance.get("tags", [])):
        raise RuntimeError("Resource ownership mismatch")
    return instance


def create():
    client = aws()
    client.verify()
    require_owned(client, OLD)
    bundle = next(b for b in client.call("lightsail", "get-bundles")["bundles"] if b["bundleId"] == "medium_3_0")
    if not (bundle["isActive"] and bundle["price"] == 24 and bundle["ramSizeInGb"] == 4 and bundle["diskSizeInGb"] == 80):
        raise RuntimeError("Target bundle changed")
    existing = client.call("lightsail", "get-instances")["instances"]
    if any(i["name"] == NEW for i in existing):
        if require_owned(client, NEW)["bundleId"] != "medium_3_0":
            raise RuntimeError("Existing target bundle mismatch")
    else:
        client.call("lightsail", "create-instances", "--instance-names", NEW, "--availability-zone", "ap-northeast-2a",
                    "--blueprint-id", "ubuntu_24_04", "--bundle-id", "medium_3_0", "--ip-address-type", "dualstack",
                    "--user-data", (BASE / "cloud-init.sh").read_text().replace("\r\n", "\n"),
                    "--tags", "key=Project,value=mujuthaek-personal", "key=ManagedBy,value=codex-personal-deployment")
    print("Verified/created dedicated 4GB target at $24/month; source retained")


def connect(target):
    runtime = RUNTIME / ("migration-" + target)
    endpoint_file = runtime / "endpoint.json"
    instance = OLD if target == "old" else NEW
    endpoint = json.loads(endpoint_file.read_text()) if endpoint_file.exists() else None
    if endpoint is None or datetime.fromisoformat(endpoint["expires_at"].replace("Z", "+00:00")) < datetime.now(timezone.utc) + timedelta(seconds=45):
        client = aws()
        require_owned(client, instance)
        client.access(instance=instance, runtime=runtime)
        endpoint = json.loads(endpoint_file.read_text())
    options = ["-i", str(runtime / "ssh-key"), "-o", f"UserKnownHostsFile={runtime / 'known_hosts'}",
               "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
               "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3"]
    return options, f"{endpoint['user']}@{endpoint['host']}"


def execute(target, command):
    options, peer = connect(target)
    subprocess.run(["ssh", *options, peer, command], check=True)


def transfer(source_command, destination_command):
    src_options, src = connect("old")
    dst_options, dst = connect("new")
    reader = subprocess.Popen(["ssh", *src_options, src, source_command], stdout=subprocess.PIPE)
    writer = subprocess.Popen(["ssh", *dst_options, dst, destination_command], stdin=reader.stdout)
    reader.stdout.close()
    status = writer.wait()
    source_status = reader.wait()
    if status or source_status:
        raise RuntimeError(f"Encrypted transfer failed (source={source_status}, target={status})")


def upload(path, target="new"):
    if target not in {"old", "new"}:
        raise ValueError("Select the verified source or target")
    options, peer = connect(target)
    subprocess.run(["scp", *options, str(path), f"{peer}:/home/ubuntu/{Path(path).name}"], check=True)


def firewall():
    client = aws()
    client.verify(require_credits=False)
    require_owned(client, NEW)
    ip = str(ipaddress.IPv4Address(urllib.request.urlopen("https://checkip.amazonaws.com", timeout=15).read().decode().strip()))
    ports = [{"fromPort": 22, "toPort": 22, "protocol": "tcp", "cidrs": [ip + "/32"]},
             {"fromPort": 80, "toPort": 80, "protocol": "tcp", "cidrs": ["0.0.0.0/0"], "ipv6Cidrs": ["::/0"]},
             {"fromPort": 443, "toPort": 443, "protocol": "tcp", "cidrs": ["0.0.0.0/0"], "ipv6Cidrs": ["::/0"]}]
    client.call("lightsail", "put-instance-public-ports", "--instance-name", NEW, "--port-infos", json.dumps(ports))
    print("Target firewall restricted to operator SSH and public HTTPS/ACME")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "firewall", "old", "new", "images"])
    parser.add_argument("command", nargs="?")
    args = parser.parse_args()
    if args.action == "create":
        create()
    elif args.action == "firewall":
        firewall()
    elif args.action in {"old", "new"}:
        execute(args.action, args.command)
    else:
        transfer("sudo docker image save mujuthaek-personal-api:20261113-1 mujuthaek-personal-notification:20261113-1 mujuthaek-personal-frontend:20261113-1 | gzip -1", "gzip -d | sudo docker image load")
