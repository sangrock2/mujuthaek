"""Preserve an activated service boundary across releases and maintenance commands."""
import os
from pathlib import Path


def compose_command(base, env_file='.env', *, manifest='compose.prod.yml', profiles=()):
    base = Path(base)
    command = ['docker', 'compose', '--env-file', str(env_file), '--env-file', 'versions.env']
    activation = base / 'runtime/service-isolation/activation.env'
    isolated = activation.exists() or activation.is_symlink()
    if isolated:
        if activation.is_symlink() or not activation.is_file():
            raise RuntimeError('Invalid service isolation activation')
        info = activation.stat()
        if os.name == 'posix' and (info.st_uid != 0 or info.st_mode & 0o077):
            raise RuntimeError('Service isolation activation must be private and root-owned')
        from service_isolation import env_values
        if env_values(activation.read_text()).get('SERVICE_ISOLATION_READY') != 'verified-v1':
            raise RuntimeError('Service isolation activation is not verified')
        command += ['--env-file', str(activation)]
    for profile in profiles:
        command += ['--profile', profile]
    command += ['-f', str(manifest)]
    if isolated:
        command += ['-f', str(base / 'compose.isolated.yml')]
    return command
