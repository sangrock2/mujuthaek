"""Final data sync and same-IP cutover after staging validation. Never deletes an instance."""
import json
import time
from migrate_4gb import aws, require_owned, execute, transfer, RUNTIME, OLD, NEW

BASE = "/opt/mujuthaek-source/backend/infra/deploy/personal"
STATIC = "mujuthaek-personal-20261113-ip"


def invalidate_connections():
    for target in ["old", "new"]:
        path = RUNTIME / ("migration-" + target) / "endpoint.json"
        if path.exists():
            path.unlink()


def main():
    client = aws()
    client.verify(require_credits=False)
    if require_owned(client, OLD)["bundleId"] != "large_3_0" or require_owned(client, NEW)["bundleId"] != "medium_3_0":
        raise RuntimeError("Unexpected source/target size")
    ip = client.call("lightsail", "get-static-ip", "--static-ip-name", STATIC)["staticIp"]
    if ip.get("attachedTo") != OLD or ip.get("ipAddress") != "3.34.67.209":
        raise RuntimeError("Static IP is not on expected source; inspect before switching")
    moved = False
    try:
        execute("old", f"cd {BASE} && sudo python3 migration_data.py snapshot final && sudo systemctl stop mujuthaek-certbot-prod.timer mujuthaek-personal-backup.timer")
        transfer(f"sudo tar -C {BASE} -czf - runtime/migration-final", f"sudo tar -xzf - -C {BASE}")
        execute("new", f"cd {BASE} && sudo docker compose --env-file .env --env-file versions.env -f compose.prod.yml stop --timeout 30 nginx api notification && sudo python3 migration_data.py restore final && sudo docker compose --env-file .env --env-file versions.env -f compose.prod.yml up -d --no-build --pull never api notification frontend nginx")
        execute("new", "for attempt in $(seq 1 40); do if curl --fail --silent --max-time 3 http://127.0.0.1:8080/actuator/health > /dev/null; then exit 0; fi; sleep 3; done; exit 1")
        client.call("lightsail", "detach-static-ip", "--static-ip-name", STATIC)
        client.call("lightsail", "attach-static-ip", "--static-ip-name", STATIC, "--instance-name", NEW)
        moved = True
        invalidate_connections()
        for _ in range(15):
            current = client.call("lightsail", "get-static-ip", "--static-ip-name", STATIC)["staticIp"]
            if current.get("attachedTo") == NEW:
                print(json.dumps({"static_ip": current["ipAddress"], "attached_to": NEW, "source": "retained with applications stopped"}))
                return
            time.sleep(2)
        raise RuntimeError("Static IP attachment did not settle")
    except Exception:
        # Restore the original service if preparation or attachment fails.
        current = client.call("lightsail", "get-static-ip", "--static-ip-name", STATIC)["staticIp"]
        if current.get("attachedTo") != OLD:
            if current.get("attachedTo"):
                client.call("lightsail", "detach-static-ip", "--static-ip-name", STATIC)
            client.call("lightsail", "attach-static-ip", "--static-ip-name", STATIC, "--instance-name", OLD)
        invalidate_connections()
        execute("old", f"cd {BASE} && sudo docker compose --env-file .env --env-file versions.env -f compose.prod.yml up -d api notification frontend nginx && sudo systemctl start mujuthaek-certbot-prod.timer mujuthaek-personal-backup.timer")
        raise


if __name__ == "__main__":
    main()
