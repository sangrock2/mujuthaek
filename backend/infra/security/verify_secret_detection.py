"""Prove reviewed historical fixture exceptions cannot hide a newly added secret."""
import argparse
import hashlib
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
        # A fixed digest of a public label keeps the synthetic value reproducible
        # and avoids random strings that match the scanner's built-in stopwords.
        synthetic_value = hashlib.sha256(b'mujuthaek-secret-detection-canary-v1').hexdigest()
        (fixture / 'canary.txt').write_text(f'api_key = "{synthetic_value}"\n', encoding='utf-8')
        finding_exit_code = 23
        result = subprocess.run(
            [str(args.binary.resolve()), 'dir', '--redact=100', '--no-banner',
             f'--exit-code={finding_exit_code}', str(fixture)],
            cwd=fixture, capture_output=True, timeout=60,
        )
        if result.returncode == 0:
            raise RuntimeError('Secret scanner failed to detect the synthetic canary')
        if result.returncode != finding_exit_code:
            raise RuntimeError(f'Secret scanner execution failed (exit code {result.returncode})')
    print('New synthetic secret detected despite historical fixture exceptions.')


if __name__ == '__main__':
    main()
