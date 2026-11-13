"""Certbot webroot issuance/renewal for Docker nginx. Run on the Linux deployment host as root."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

CERTBOT_IMAGE = "certbot/certbot:v5.10.0"


def run(*args, capture=False, check=True, env=None):
    return subprocess.run(args, check=check, capture_output=capture, text=True, env=env)


def identifier_args(identifier):
    try:
        address = ipaddress.ip_address(identifier)
    except ValueError:
        if (
            len(identifier) > 253
            or "." not in identifier
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in identifier.split("."))
        ):
            raise ValueError("Use a public IP or an ASCII DNS hostname") from None
        return ["-d", identifier]
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise ValueError("IP certificate requires a public IP")
    return ["--ip-address", str(address), "--preferred-profile", "shortlived"]


def compose(base, environment, *args):
    env = dict(os.environ, API_TLS_CERT_DIR=str(base / "tls"))
    return run(
        "docker",
        "compose",
        "--project-directory",
        str(base),
        "-f",
        str(base / f"compose.{environment}.yml"),
        "--env-file",
        str(base / ".env"),
        "--env-file",
        str(base / "versions.env"),
        *args,
        env=env,
    )


def certbot(base, *args):
    command = ["docker", "run", "--rm"]
    for source, target in [
        ("letsencrypt", "/etc/letsencrypt"),
        ("letsencrypt-work", "/var/lib/letsencrypt"),
        ("letsencrypt-logs", "/var/log/letsencrypt"),
        ("acme-webroot", "/var/www/certbot"),
    ]:
        command += ["--mount", f"type=bind,src={base / source},dst={target}"]
    run(*command, CERTBOT_IMAGE, *args)


def activate(base, settings):
    lineage = base / "letsencrypt/live" / settings["cert_name"]
    identifier = settings["identifier"]
    try:
        ipaddress.ip_address(identifier)
        check_name = "-verify_ip"
    except ValueError:
        check_name = "-verify_hostname"
    run("openssl", "x509", "-in", str(lineage / "cert.pem"), "-noout", "-checkend", "3600", capture=True)
    run(
        "openssl",
        "verify",
        "-purpose",
        "sslserver",
        check_name,
        identifier,
        "-untrusted",
        str(lineage / "chain.pem"),
        str(lineage / "cert.pem"),
        capture=True,
    )
    certificate_key = run("openssl", "x509", "-in", str(lineage / "cert.pem"), "-noout", "-pubkey", capture=True).stdout
    private_key = run("openssl", "pkey", "-in", str(lineage / "privkey.pem"), "-pubout", capture=True).stdout
    if certificate_key != private_key:
        raise RuntimeError("Certificate and key do not match")
    tls = base / "tls"
    fingerprint = hashlib.sha256((lineage / "fullchain.pem").read_bytes()).hexdigest()
    release = tls / "releases" / fingerprint
    release.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, mode in [("fullchain.pem", 0o644), ("privkey.pem", 0o600)]:
        shutil.copyfile(lineage / name, release / name)
        (release / name).chmod(mode)
        link = tls / name
        if link.exists() and not link.is_symlink():
            raise RuntimeError("Existing TLS files need migration before managed renewal")
        if not link.is_symlink():
            link.symlink_to(f"current/{name}")
    pending = tls / f".current-{os.getpid()}"
    pending.symlink_to(Path("releases") / fingerprint)
    os.replace(pending, tls / "current")


def persist_tls_path(base):
    path = base / ".env"
    original = path.stat()
    lines = [line for line in path.read_text().splitlines() if not line.startswith("API_TLS_CERT_DIR=")]
    lines.append(f'API_TLS_CERT_DIR="{base / "tls"}"')
    descriptor, temporary = tempfile.mkstemp(prefix=".env-tls-", dir=base)
    with os.fdopen(descriptor, "w") as output:
        output.write("\n".join(lines) + "\n")
    os.chmod(temporary, original.st_mode & 0o777)
    if hasattr(os, "chown"):
        os.chown(temporary, original.st_uid, original.st_gid)
    os.replace(temporary, path)


def install_timer(base, environment):
    # The scheduled entry point is root-owned, independent of a later application checkout.
    installed = Path("/usr/local/lib/mujuthaek")
    installed.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(__file__, installed / "certificates.py")
    (installed / "certificates.py").chmod(0o700)
    unit = f"mujuthaek-certbot-{environment}"
    service = f"""[Unit]
Description=Renew and activate Mujuthaek TLS certificate ({environment})
Wants=network-online.target
After=network-online.target docker.service
Requires=docker.service
[Service]
Type=oneshot
UMask=0077
ExecStart=/usr/bin/python3 /usr/local/lib/mujuthaek/certificates.py renew {environment} --base-dir {base}
TimeoutStartSec=1800
"""
    timer = f"""[Unit]
Description=Check Mujuthaek TLS renewal four times daily ({environment})
[Timer]
OnCalendar=*-*-* 00,06,12,18:10:00
RandomizedDelaySec=1800
Persistent=true
Unit={unit}.service
[Install]
WantedBy=timers.target
"""
    Path(f"/etc/systemd/system/{unit}.service").write_text(service)
    Path(f"/etc/systemd/system/{unit}.timer").write_text(timer)
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", f"{unit}.timer")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["issue", "renew", "test-renew", "install-timer"])
    parser.add_argument("environment", choices=["prod", "dev"])
    parser.add_argument("--base-dir", type=Path, default=Path("/opt/mujuthaek"))
    parser.add_argument("--identifier")
    parser.add_argument("--email")
    args = parser.parse_args()
    base = args.base_dir.resolve()
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(base)) or base == Path("/"):
        parser.error("Deployment path must be an absolute non-root path without whitespace")
    if os.geteuid() != 0:
        parser.error("Run on the deployment host with sudo")
    import fcntl

    with (base / ".tls.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = base / f"tls-settings.{args.environment}.json"
        if args.action == "issue":
            contact = base / "tls-contact.json"
            if not args.email and contact.exists():
                args.email = json.loads(contact.read_text()).get("email")
            if not args.identifier or not args.email or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", args.email):
                parser.error("issue requires --identifier and --email")
            identifier_args(args.identifier)
            settings = {
                "identifier": args.identifier,
                "email": args.email,
                "cert_name": f"mujuthaek-{args.environment}",
            }
        else:
            settings = json.loads(state.read_text())
        if args.action == "install-timer":
            install_timer(base, args.environment)
            return
        for folder in ["letsencrypt", "letsencrypt-work", "letsencrypt-logs", "tls"]:
            (base / folder).mkdir(exist_ok=True, mode=0o700)
        challenge = base / "acme-webroot/.well-known/acme-challenge"
        challenge.mkdir(parents=True, exist_ok=True)
        for folder in [base / "acme-webroot", challenge.parent, challenge]:
            folder.chmod(0o755)
        run("docker", "pull", CERTBOT_IMAGE)
        if args.action == "issue":
            persist_tls_path(base)
            compose(base, args.environment, "stop", "nginx")
            bootstrap = f"mujuthaek-acme-bootstrap-{args.environment}"
            # Only our named bootstrap can be replaced; application containers/volumes are retained.
            existing = run(
                "docker",
                "inspect",
                "--format",
                '{{index .Config.Labels "mujuthaek.acme"}}',
                bootstrap,
                capture=True,
                check=False,
            )
            if existing.returncode == 0:
                if existing.stdout.strip() != args.environment:
                    raise RuntimeError("Bootstrap name is owned by another container")
                run("docker", "rm", "-f", bootstrap)
            run(
                "docker",
                "run",
                "-d",
                "--name",
                bootstrap,
                "--label",
                f"mujuthaek.acme={args.environment}",
                "-p",
                "80:80",
                "--mount",
                f"type=bind,src={base / 'nginx/acme.conf'},dst=/etc/nginx/conf.d/default.conf,readonly",
                "--mount",
                f"type=bind,src={base / 'acme-webroot'},dst=/var/www/certbot,readonly",
                "nginx:1.29-alpine",
            )
            command = [
                "certonly",
                "--non-interactive",
                "--agree-tos",
                "--email",
                settings["email"],
                "--cert-name",
                settings["cert_name"],
                "--webroot",
                "--webroot-path",
                "/var/www/certbot",
                *identifier_args(settings["identifier"]),
            ]
            certbot(base, *command, "--dry-run")
            certbot(base, *command, "--keep-until-expiring")
            activate(base, settings)
            state.write_text(json.dumps(settings, indent=2) + "\n")
            state.chmod(0o600)
            run("docker", "rm", "-f", bootstrap)
            compose(base, args.environment, "up", "-d", "--no-deps", "nginx")
            install_timer(base, args.environment)
        else:
            certbot(
                base,
                "renew",
                "--non-interactive",
                "--no-random-sleep-on-renew",
                "--cert-name",
                settings["cert_name"],
                *(["--dry-run"] if args.action == "test-renew" else []),
            )
            if args.action == "renew":
                activate(base, settings)
                compose(base, args.environment, "exec", "-T", "nginx", "nginx", "-t")
                compose(base, args.environment, "exec", "-T", "nginx", "nginx", "-s", "reload")


if __name__ == "__main__":
    main()
