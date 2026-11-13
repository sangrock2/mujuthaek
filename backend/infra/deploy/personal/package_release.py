"""Package source for a new personal host, excluding local credentials and generated data."""
import argparse
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EXCLUDED = {".git", ".venv", ".gradle", ".next", "node_modules", "__pycache__", "build", "test-results", "runtime", "playwright-report"}
PREFIXES = ("frontend/", "backend/services/", "backend/libs/", "backend/contracts/", "backend/infra/deploy/personal/")
EXTRA = {"backend/.dockerignore", "backend/infra/deploy/certificates.py", "backend/infra/deploy/nginx/acme.conf"}


def allowed(name):
    path = Path(name)
    return (
        not path.is_absolute() and ".." not in path.parts
        and (name.startswith(PREFIXES) or name in EXTRA)
        and not EXCLUDED.intersection(path.parts)
        and not any(part.startswith(".env") for part in path.parts)
        and path.suffix.lower() not in {".pem", ".key", ".p12", ".jks", ".log"}
        and not path.name.startswith(("tls-contact", "tls-settings", "credentials"))
    )


def package(destination):
    names = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8").split("\0")
    total = 0
    with tarfile.open(destination, "w:gz") as archive:
        for name in sorted(set(filter(None, names))):
            source = ROOT / name
            if allowed(name) and source.is_file() and not source.is_symlink():
                info = archive.gettarinfo(str(source), arcname=name)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o755 if name.endswith((".sh", "/gradlew")) else 0o644
                # Git may materialize shell scripts as CRLF on Windows.
                if name.endswith((".sh", "/gradlew")):
                    import io
                    body = source.read_bytes().replace(b"\r\n", b"\n")
                    info.size = len(body)
                    archive.addfile(info, io.BytesIO(body))
                else:
                    with source.open("rb") as body:
                        archive.addfile(info, body)
                total += 1
    print(f"Packaged {total} source files ({destination.stat().st_size} bytes), no environment files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    package(parser.parse_args().destination)
