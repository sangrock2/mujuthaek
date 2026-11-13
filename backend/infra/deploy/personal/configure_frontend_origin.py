"""Connect the personal backend's frontend/CORS/OAuth origin without changing secrets."""
import json
import os
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
ORIGIN = "https://mujuthaek.vercel.app"


def compose(env_file, *args, capture=False):
    return subprocess.run(["docker", "compose", "--env-file", str(env_file), "--env-file", "versions.env", "-f", "compose.prod.yml", *args],
                          cwd=BASE, check=True, capture_output=capture, text=capture)


def reload_nginx(env_file):
    compose(env_file, "exec", "-T", "nginx", "nginx", "-t")
    compose(env_file, "exec", "-T", "nginx", "nginx", "-s", "reload")


def main():
    if os.name != "posix" or os.geteuid() != 0 or BASE != Path("/opt/mujuthaek-source/backend/infra/deploy/personal"):
        raise SystemExit("Run as root on the verified personal deployment host")
    original = BASE / ".env"
    content = original.read_text()
    names = {"FRONTEND_URL", "OAUTH_REDIRECT_BASE_URL"}
    lines = [line for line in content.splitlines() if line.split("=", 1)[0] not in names]
    lines.extend(f"{name}={ORIGIN}" for name in sorted(names))
    pending = BASE / ".env.vercel-pending"
    descriptor = os.open(pending, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write("\n".join(lines) + "\n")
    compose(pending, "config", "--quiet")
    backup = BASE / ".env.before-vercel"
    if not backup.exists():
        descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(content)
    os.replace(pending, original)
    try:
        compose(original, "up", "-d", "--no-build", "--pull", "never", "api", "notification")
        for _ in range(40):
            result = subprocess.run(["curl", "--fail", "--silent", "--max-time", "3", "http://127.0.0.1:8080/actuator/health"], capture_output=True, text=True)
            if result.returncode == 0 and json.loads(result.stdout).get("status") == "UP":
                break
            time.sleep(3)
        else:
            raise RuntimeError("API did not become ready; restore previous origin")
        reload_nginx(original)
        print(json.dumps({"frontend_url": ORIGIN, "oauth_callback_base": ORIGIN, "backend_origin": "https://3.34.67.209"}))
    except Exception:
        original.write_text(content)
        original.chmod(0o600)
        compose(original, "up", "-d", "--no-build", "--pull", "never", "api", "notification")
        reload_nginx(original)
        raise


if __name__ == "__main__":
    main()
