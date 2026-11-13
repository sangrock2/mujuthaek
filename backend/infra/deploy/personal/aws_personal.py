"""AWS personal deployment: explicit profile/account, bounded Lightsail plan, verified SSH host keys."""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "runtime"
REGION = "ap-northeast-2"
INSTANCE = "mujuthaek-personal-20261113-4gb"
BUNDLE_ID = "medium_3_0"
BUNDLE_RAM = 4
BUNDLE_MAX_PRICE = 24
STATIC_IP_NAME = "mujuthaek-personal-20261113-ip"


class AWS:
    def __init__(self, profile, account):
        if not profile or profile in {"default", "iter-local", "mujuthaek-s3"}:
            raise ValueError("Use the explicitly selected personal profile")
        if len(account) != 12 or not account.isdigit():
            raise ValueError("Expected a 12-digit personal account ID")
        self.profile, self.account = profile, account

    def call(self, *args, region=REGION):
        env = dict(os.environ, AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off")
        # Explicit profile must not be overridden by ambient team credentials/endpoints.
        for name in list(env):
            if name in {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"} or name.startswith("AWS_ENDPOINT_URL"):
                env.pop(name)
        result = subprocess.run(
            ["aws", *args, "--profile", self.profile, "--region", region, "--output", "json", "--no-cli-pager"],
            capture_output=True, text=True, env=env,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout or "{}")

    def verify(self, require_credits=True):
        identity = self.call("sts", "get-caller-identity")
        if identity["Account"] != self.account:
            raise RuntimeError("Account mismatch; no resource changes allowed")
        plan = self.call("freetier", "get-account-plan-state", region="us-east-1")
        if plan.get("accountId") != self.account or plan.get("accountPlanStatus") != "ACTIVE":
            raise RuntimeError("Account plan is not active or does not match")
        credits = plan.get("accountPlanRemainingCredits", {})
        if require_credits and (credits.get("unit") != "USD" or credits.get("amount", 0) < 50):
            raise RuntimeError("Insufficient verified credits for initial deployment")
        return plan

    def bundle(self):
        bundles = self.call("lightsail", "get-bundles")["bundles"]
        bundle = next(b for b in bundles if b["bundleId"] == BUNDLE_ID)
        if not (bundle["isActive"] and bundle["ramSizeInGb"] == BUNDLE_RAM and bundle["price"] <= BUNDLE_MAX_PRICE and "LINUX_UNIX" in bundle["supportedPlatforms"]):
            raise RuntimeError("Plan specifications/price changed; stop before creating resources")
        return bundle

    def create(self):
        self.verify()
        self.bundle()
        instances = self.call("lightsail", "get-instances")["instances"]
        existing = next((i for i in instances if i["name"] == INSTANCE), None)
        if existing:
            if existing["bundleId"] != BUNDLE_ID or not any(t["key"] == "Project" and t.get("value") == "mujuthaek-personal" for t in existing.get("tags", [])):
                raise RuntimeError("Existing resource is not owned by this deployment")
            print("Owned instance already exists; creation skipped")
            return
        result = self.call(
            "lightsail", "create-instances", "--instance-names", INSTANCE,
            "--availability-zone", "ap-northeast-2a", "--blueprint-id", "ubuntu_24_04",
            "--bundle-id", BUNDLE_ID, "--ip-address-type", "dualstack",
            "--user-data", (BASE / "cloud-init.sh").read_text().replace("\r\n", "\n"),
            "--tags", "key=Project,value=mujuthaek-personal", "key=ManagedBy,value=codex-personal-deployment",
        )
        print(json.dumps({"instance": INSTANCE, "monthly_bundle_usd": BUNDLE_MAX_PRICE, "operations": [o["status"] for o in result.get("operations", [])]}))

    def access(self, instance=INSTANCE, runtime=RUNTIME):
        self.verify(require_credits=False)
        details = self.call("lightsail", "get-instance-access-details", "--instance-name", instance, "--protocol", "ssh")["accessDetails"]
        if details["instanceName"] != instance or not details.get("hostKeys"):
            raise RuntimeError("Missing AWS-authenticated SSH host keys; do not trust keyscan")
        runtime.mkdir(exist_ok=True, parents=True)
        key = runtime / "ssh-key"
        if key.exists():
            key.unlink()
        key.write_text(details["privateKey"], encoding="ascii")
        key.chmod(0o600)
        if os.name == "nt":
            username = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
            subprocess.run(["icacls", str(key), "/inheritance:r", "/grant:r", f"{username}:(R)"], capture_output=True, check=True)
        (runtime / "ssh-key-cert.pub").write_text(details["certKey"] + "\n", encoding="ascii")
        (runtime / "known_hosts").write_text("".join(
            f'{details["ipAddress"]} {k["algorithm"]} {k["publicKey"]}\n' for k in details["hostKeys"]
        ), encoding="ascii")
        endpoint = {"host": details["ipAddress"], "user": details["username"], "instance": instance,
                    "expires_at": details.get("expiresAt") or (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(),
                    "profile": self.profile, "account": self.account}
        (runtime / "endpoint.json").write_text(json.dumps(endpoint), encoding="ascii")
        print(json.dumps(endpoint))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "create", "access"])
    parser.add_argument("--profile", required=True)
    parser.add_argument("--account", required=True)
    args = parser.parse_args()
    aws = AWS(args.profile, args.account)
    if args.action == "inspect":
        print(json.dumps({"plan": aws.verify(), "bundle": aws.bundle()}, default=str))
    elif args.action == "create":
        aws.create()
    else:
        aws.access()


if __name__ == "__main__":
    main()
