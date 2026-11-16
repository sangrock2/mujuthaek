"""Update CPU/startup controls without rewriting release/schema metadata or restoring data."""
import json
import os
import re
import subprocess
from pathlib import Path

from configure_collection import private_file

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')


def runtime_manifest(source):
    for service, cap in (('collector', '0.10'), ('extraction', '0.15')):
        match = re.search(r'(?ms)^  ' + service + r':\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)', source)
        if not match or '    mem_limit:' not in match[0]:
            raise RuntimeError('Worker service limits were not found')
        section = re.sub(r'(?m)^    cpus:[^\n]*\n', '', match[0])
        section = re.sub(r'(?m)^(    mem_limit:[^\n]*\n)', lambda value: value[0] + f'    cpus: "{cap}"\n', section, count=1)
        source = source[:match.start()] + section + source[match.end():]
    for service in ('api', 'notification'):
        match = re.search(r'(?ms)^  ' + service + r':\n(.*?)(?=^  [a-zA-Z][\w-]*:\n|\Z)', source)
        if not match:
            raise RuntimeError('Application service not found')
        section = re.sub(r'(?m)^      JAVA_TOOL_OPTIONS: ([^\n]+)$', java_options, match[0])
        source = source[:match.start()] + section + source[match.end():]
    return source


def java_options(value):
    """JVM은 CPU 1개처럼 쓰되(버스트 크레딧 보호) 가상 스레드 실행기는 4개로 둬요. 1개면 CPU를 오래 쓰는 요청 하나가 모든 요청을 멈췄어요(보안 감사 M-1)."""
    line = value[0]
    if '-XX:ActiveProcessorCount=' not in line:
        line += ' -XX:ActiveProcessorCount=1'
    if '-Djdk.virtualThreadScheduler.parallelism=' not in line:
        line += ' -Djdk.virtualThreadScheduler.parallelism=4'
    return line


def main():
    import fcntl
    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the personal deployment host')
    values = dict(line.split('=', 1) for line in (BASE / '.env').read_text().splitlines()
                  if '=' in line and not line.startswith('#'))
    if values.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
        raise RuntimeError('Wrong personal deployment')
    with (BASE / 'runtime/releases/lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = BASE / 'compose.prod.yml'
        before = manifest.read_text()
        pending = private_file(runtime_manifest(before))
        try:
            from compose_runtime import compose_command
            command = [*compose_command(BASE, manifest=pending, profiles=('workers',)), 'config', '--format', 'json']
            config = json.loads(subprocess.run(command, cwd=BASE, check=True, capture_output=True, text=True, timeout=60).stdout)
            for service, cap in (('collector', 0.10), ('extraction', 0.15)):
                if float(config['services'][service]['cpus']) != cap:
                    raise RuntimeError('Worker CPU configuration mismatch')
            os.replace(pending, manifest)
        finally:
            pending.unlink(missing_ok=True)
        for service, cap in (('collector', '0.10'), ('extraction', '0.15')):
            info = subprocess.run(['docker', 'inspect', f'mujuthaek-personal-{service}-1'], capture_output=True, text=True, timeout=15)
            if info.returncode:
                continue
            instance = json.loads(info.stdout)[0]
            if instance['Config']['Labels'].get('com.docker.compose.project') != 'mujuthaek-personal':
                raise RuntimeError('Unexpected worker project')
            subprocess.run(['docker', 'update', '--cpus', cap, instance['Id']], check=True, capture_output=True, timeout=20)
        dropin = Path('/etc/systemd/system/mujuthaek-personal-release.service.d/runtime-timeouts.conf')
        dropin.parent.mkdir(parents=True, exist_ok=True)
        dropin.write_text('[Service]\nTimeoutStartSec=35min\n')
        subprocess.run(['systemctl', 'daemon-reload'], check=True, capture_output=True, timeout=30)
    print(json.dumps({'ok': True, 'worker_cpu_limits_applied': True, 'release_timeout_minutes': 35,
                      'release_metadata_changed': False, 'database_restored': False, 'applications_restarted': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Runtime update failed: ' + type(error).__name__ + '; no credential values displayed') from None
