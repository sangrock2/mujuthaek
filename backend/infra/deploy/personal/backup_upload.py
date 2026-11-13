"""Upload a database backup without exposing app passwords to the AWS CLI container."""
import os
import subprocess
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
values = dict(line.split("=", 1) for line in (base / ".env").read_text().splitlines() if line and not line.startswith("#"))
env_path = base / "runtime/backup-aws.env"
env_path.parent.mkdir(exist_ok=True, mode=0o700)
descriptor = os.open(env_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(descriptor, "w") as output:
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"):
        output.write(f"{name}={values[name]}\n")
backup = Path(sys.argv[1]).resolve()
if backup.parent != (base / "runtime/backups").resolve() or backup.suffix != ".dump":
    raise ValueError("Only deployment DB backup files can be uploaded")
subprocess.run([
    "docker", "run", "--rm", "--env-file", str(env_path),
    "--mount", f"type=bind,src={backup},dst=/backup.dump,readonly",
    "amazon/aws-cli:2.36.28", "s3", "cp", "/backup.dump",
    f"s3://{values['S3_BUCKET']}/backups/{backup.name}", "--only-show-errors", "--sse", "AES256",
], check=True)
