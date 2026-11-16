"""Install the explicitly verified public source archive while preserving live secrets and runtime data."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from pathlib import Path, PurePosixPath

ROOT = Path('/opt/mujuthaek-source')
BASE = ROOT / 'backend/infra/deploy/personal'
ARCHIVE = Path('/home/ubuntu/security-main-source.tar.gz')
EXPECTED = '776db5670875ac58078cb3168447c94b37e5a6f759ca579aa0fd3002e64057b8'
COMMIT = 'edadebc5e540fa534386ca2338e9350b2370ea67'


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90).stdout


def main():
    if os.name != 'posix' or os.geteuid() != 0 or ROOT.resolve() != ROOT or not BASE.is_dir():
        raise RuntimeError('Run only on the verified deployment host')
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError('Reviewed source archive digest mismatch')
    with tarfile.open(ARCHIVE) as archive:
        members = archive.getmembers()
        for item in members:
            relative = PurePosixPath(item.name)
            if (relative.is_absolute() or '..' in relative.parts or item.issym() or item.islnk()
                    or not (item.isfile() or item.isdir()) or 'runtime' in relative.parts
                    or any(part.startswith('.env') for part in relative.parts)
                    or not (item.name == 'backend' or item.name.startswith('backend/'))):
                raise RuntimeError('Unexpected archive member')
            target = ROOT / item.name
            if target.is_symlink() or not target.resolve().is_relative_to(ROOT):
                raise RuntimeError('Unexpected deployment link')
        timer = 'mujuthaek-personal-release.timer'
        was_active = subprocess.run(['systemctl', 'is-active', '--quiet', timer]).returncode == 0
        run('systemctl', 'stop', timer)
        backup = None
        mutated = False
        added_files = []
        try:
            for _ in range(60):
                if subprocess.run(['systemctl', 'is-active', '--quiet', 'mujuthaek-personal-release.service']).returncode:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Existing deployment did not finish; source unchanged')
            backup = BASE / ('runtime/source-before-' + COMMIT[:8] + '.tar.gz')
            if backup.exists():
                raise RuntimeError('Existing recovery archive retained; inspect before repeating')
            with backup.open('xb') as stream:
                os.chmod(backup, 0o600)
                with tarfile.open(fileobj=stream, mode='w:gz') as old:
                    for item in members:
                        target = ROOT / item.name
                        if target.is_file():
                            old.add(target, arcname=item.name, recursive=False)
            mutated = True
            for item in members:
                target = ROOT / item.name
                if item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        added_files.append(target)
                    with archive.extractfile(item) as source, target.open('wb') as destination:
                        if item.name.endswith(('.sh', '/gradlew')):
                            destination.write(source.read().replace(b'\r\n', b'\n'))
                        else:
                            shutil.copyfileobj(source, destination)
                    target.chmod(0o755 if item.name.endswith(('.sh', '/gradlew')) else 0o644)
            run('docker', 'exec', 'mujuthaek-personal-nginx-1', 'nginx', '-t')
            run('docker', 'exec', 'mujuthaek-personal-nginx-1', 'nginx', '-s', 'reload')
            (BASE / 'runtime/source-commit').write_text(COMMIT + '\n')
            print(json.dumps({'source_commit': COMMIT, 'installed_files': len(members),
                              'secrets_and_runtime_preserved': True, 'app_restarts': 0}))
        except BaseException:
            if mutated:
                with tarfile.open(backup) as previous:
                    for item in previous:
                        target = ROOT / item.name
                        if not item.isfile() or target.is_symlink() or not target.resolve().is_relative_to(ROOT):
                            raise RuntimeError('Unexpected rollback member')
                        with previous.extractfile(item) as source, target.open('wb') as destination:
                            shutil.copyfileobj(source, destination)
                        target.chmod(item.mode & 0o777)
                for target in added_files:
                    if target.is_symlink() or not target.resolve().is_relative_to(ROOT):
                        raise RuntimeError('Unexpected new source link')
                    target.unlink(missing_ok=True)
                run('docker', 'exec', 'mujuthaek-personal-nginx-1', 'nginx', '-t')
                run('docker', 'exec', 'mujuthaek-personal-nginx-1', 'nginx', '-s', 'reload')
            raise
        finally:
            if was_active:
                run('systemctl', 'start', timer)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{64}', args.sha256) or not re.fullmatch('[a-f0-9]{40}', args.commit):
        raise SystemExit('Expected a verified SHA256 and full source commit')
    if args.archive.is_symlink() or args.archive.resolve().parent != Path('/home/ubuntu'):
        raise SystemExit('Expected a regular uploaded source archive under /home/ubuntu')
    ARCHIVE, EXPECTED, COMMIT = args.archive, args.sha256, args.commit
    main()
