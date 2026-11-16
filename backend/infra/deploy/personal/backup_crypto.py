"""Streaming authenticated backup encryption. Only the public recipient certificate belongs on the server."""
import argparse
import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def transform(source, destination, certificate, *, private_key=None, openssl=None):
    source, destination, certificate = Path(source), Path(destination), Path(certificate)
    if source.is_symlink() or certificate.is_symlink() or not source.is_file() or not certificate.is_file():
        raise ValueError('Expected regular backup/certificate files')
    binary = openssl or shutil.which('openssl')
    if not binary:
        raise RuntimeError('OpenSSL is required')
    if private_key is not None:
        private_key = Path(private_key)
        if private_key.is_symlink() or not private_key.is_file():
            raise ValueError('Expected a regular recovery key')
        args = ['-decrypt', '-inform', 'DER', '-recip', str(certificate), '-inkey', str(private_key)]
    else:
        args = ['-encrypt', '-aes-256-gcm', '-stream', '-outform', 'DER', '-recip', str(certificate),
                '-keyopt', 'rsa_padding_mode:oaep', '-keyopt', 'rsa_oaep_md:sha256']
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            result = subprocess.run([binary, 'cms', '-binary', *args, '-in', str(source)],
                                    stdout=output, stderr=subprocess.PIPE, timeout=1800)
        if result.returncode:
            raise RuntimeError('Backup cryptographic validation failed; partial output removed')
        with destination.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        return {'sha256': digest, 'bytes': destination.stat().st_size}
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    parser.add_argument('--certificate', required=True)
    parser.add_argument('--private-key', help='Recovery only; never install this key on the server')
    args = parser.parse_args()
    transform(args.source, args.destination, args.certificate, private_key=args.private_key)
