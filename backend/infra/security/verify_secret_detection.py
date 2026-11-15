"""Prove reviewed historical fixture exceptions cannot hide a newly added secret."""
import argparse
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        shutil.copyfile(root / '.gitleaksignore', fixture / '.gitleaksignore')
        # Newly generated, never provisioned with any service; no real credential is used.
        (fixture / 'canary.txt').write_text('api_key = "' + secrets.token_urlsafe(40) + '"\n', encoding='utf-8')
        result = subprocess.run([str(args.binary.resolve()), 'dir', '--redact=100', '--no-banner', str(fixture)],
                                cwd=fixture, capture_output=True, timeout=60)
        if result.returncode != 1:
            raise RuntimeError('Secret scanner failed to detect the synthetic canary')
    print('New synthetic secret detected despite historical fixture exceptions.')


if __name__ == '__main__':
    main()
