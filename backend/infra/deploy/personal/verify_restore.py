"""Download this deployment's latest API backup from S3 and restore in an isolated disposable DB."""
import json
import subprocess
import time
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
values = dict(line.split("=", 1) for line in (BASE / ".env").read_text().splitlines() if line and not line.startswith("#"))
backup = sorted((BASE / "runtime/backups").glob("api-*.dump"))[-1]
restore = BASE / "runtime/restore-check"
restore.mkdir(exist_ok=True, mode=0o700)
subprocess.run([
    "docker", "run", "--rm", "--env-file", str(BASE / "runtime/backup-aws.env"),
    "--mount", f"type=bind,src={restore},dst=/restore", "amazon/aws-cli:2.36.28",
    "s3", "cp", f"s3://{values['S3_BUCKET']}/backups/{backup.name}", "/restore/check.dump", "--only-show-errors",
], check=True)
name = "mujuthaek-personal-restore-" + uuid.uuid4().hex[:8]
subprocess.run([
    "docker", "run", "--rm", "-d", "--name", name, "--network", "none", "--memory", "512m",
    "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "--mount", f"type=bind,src={restore / 'check.dump'},dst=/check.dump,readonly",
    "postgis/postgis:17-3.5",
], check=True, capture_output=True)
try:
    for _ in range(45):
        ready = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True)
        if ready.returncode == 0:
            # The image first starts a temporary initialization server; wait for its final TCP listener.
            tcp = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"], capture_output=True)
            if tcp.returncode == 0:
                break
        time.sleep(2)
    else:
        raise RuntimeError("Isolated restore database did not become ready")
    subprocess.run(["docker", "exec", name, "pg_restore", "-U", "postgres", "-d", "postgres", "--no-owner", "--exit-on-error", "/check.dump"], check=True)
    result = subprocess.run([
        "docker", "exec", name, "psql", "-U", "postgres", "-d", "postgres", "-tAc",
        "select count(*) from common.flyway_schema_history where success and version is not null",
    ], check=True, capture_output=True, text=True)
    migrations = int(result.stdout.strip())
    if migrations < 68:
        raise RuntimeError("Restored DB migration history is incomplete")
    print(json.dumps({"s3_download": "verified", "restored_api_migrations": migrations, "production_db_modified": False}))
finally:
    # This container/anonymous volume was created above solely for this verification.
    subprocess.run(["docker", "stop", "--time", "10", name], check=True, capture_output=True)
