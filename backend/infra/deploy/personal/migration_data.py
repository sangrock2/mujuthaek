"""Transfer/verify all four personal DBs and empty RabbitMQ queues during 4GB migration."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATABASES = ("api", "notification", "collector", "extraction")


def compose(*args, capture=False):
    return subprocess.run(["docker", "compose", "--env-file", ".env", "--env-file", "versions.env", "-f", "compose.prod.yml", *args],
                          cwd=BASE, check=True, capture_output=capture, text=capture)


def sql(db, query):
    return compose("exec", "-T", "postgres", "psql", "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1", "-tAc", query, capture=True).stdout.strip()


def counts():
    result = {}
    for db in DATABASES:
        tables = sql(db, "select schemaname,tablename from pg_tables where schemaname not like 'pg_%' and schemaname <> 'information_schema' order by 1,2")
        selects = []
        for table in tables.splitlines():
            schema, name = table.split("|")
            if not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", v) for v in [schema, name]):
                raise RuntimeError("Unexpected identifier; stop migration")
            selects.append(f'''select '{schema}.{name}',count(*) from "{schema}"."{name}"''')
        rows = sql(db, " union all ".join(selects)) if selects else ""
        result[db] = dict((name, int(number)) for name, number in (row.split("|") for row in rows.splitlines()))
    return result


def require_empty_queue(allow_no_queues=False):
    text = compose("exec", "-T", "rabbitmq", "rabbitmqctl", "list_queues", "name", "messages", "--quiet", capture=True).stdout
    queues = []
    for row in text.splitlines():
        parts = row.split("\t")
        if len(parts) == 2 and parts[1].isdigit():
            queues.append((parts[0], int(parts[1])))
    if (not queues and not allow_no_queues) or any(messages for _, messages in queues):
        raise RuntimeError("Queues are not verified empty; source must be retained")


def snapshot(phase):
    output = BASE / "runtime" / ("migration-" + phase)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if phase == "final":
        compose("stop", "--timeout", "30", "nginx", "api", "notification")
    try:
        require_empty_queue()
        for db in DATABASES:
            with (output / f"{db}.dump").open("wb") as archive:
                subprocess.run(["docker", "compose", "--env-file", ".env", "--env-file", "versions.env", "-f", "compose.prod.yml",
                                "exec", "-T", "postgres", "pg_dump", "-U", "postgres", "-Fc", db], cwd=BASE, stdout=archive, check=True)
        filename = f"/tmp/mujuthaek-migration-{phase}.json"
        compose("exec", "-T", "rabbitmq", "rabbitmqctl", "export_definitions", filename)
        subprocess.run(["docker", "cp", f"mujuthaek-personal-rabbitmq-1:{filename}", str(output / "rabbitmq.json")], check=True)
        (output / "manifest.json").write_text(json.dumps(counts(), sort_keys=True))
        for path in output.iterdir():
            path.chmod(0o600)
    except Exception:
        if phase == "final":
            compose("up", "-d", "api", "notification", "nginx")
        raise
    print(json.dumps({"phase": phase, "databases": list(DATABASES), "queues": "verified empty", "manifest": "saved"}))


def restore(phase):
    source = BASE / "runtime" / ("migration-" + phase)
    require_empty_queue(allow_no_queues=True)
    for db in DATABASES:
        with (source / f"{db}.dump").open("rb") as archive:
            subprocess.run(["docker", "compose", "--env-file", ".env", "--env-file", "versions.env", "-f", "compose.prod.yml",
                            "exec", "-T", "postgres", "pg_restore", "-U", "postgres", "-d", db, "--clean", "--if-exists", "--exit-on-error"],
                           cwd=BASE, stdin=archive, check=True)
    expected = json.loads((source / "manifest.json").read_text())
    actual = counts()
    if actual != expected:
        raise RuntimeError("Database row counts differ from source; do not cut over")
    subprocess.run(["docker", "cp", str(source / "rabbitmq.json"), "mujuthaek-personal-rabbitmq-1:/tmp/mujuthaek-migration.json"], check=True)
    compose("exec", "-T", "rabbitmq", "rabbitmqctl", "import_definitions", "/tmp/mujuthaek-migration.json")
    print(json.dumps({"phase": phase, "database_row_counts": "all four match source", "rabbitmq_definitions": "imported"}))


if __name__ == "__main__":
    if os.name != "posix" or os.geteuid() != 0 or BASE != Path("/opt/mujuthaek-source/backend/infra/deploy/personal"):
        raise SystemExit("Run as root on the verified personal deployment host")
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "restore"])
    parser.add_argument("phase", choices=["stage", "final"])
    args = parser.parse_args()
    (snapshot if args.action == "snapshot" else restore)(args.phase)
