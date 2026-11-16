"""Reject mutable external images on production and Docker build paths."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_host


class ContainerPins(unittest.TestCase):
    def test_external_base_images_and_runtime_services_require_a_verified_digest(self):
        evidence = json.loads((ROOT / 'backend/infra/security/container-image-digests.json').read_text())['images']
        references = [release_host.AWS_IMAGE]
        for path in [*(ROOT / 'backend/services').glob('*/Dockerfile'), ROOT / 'frontend/Dockerfile']:
            for line in path.read_text(encoding='utf-8').splitlines():
                words = line.split()
                if words[:1] == ['FROM']:
                    references.append(next(word for word in words[1:] if not word.startswith('--')))
                elif words[:1] == ['COPY']:
                    references += [word.removeprefix('--from=') for word in words if word.startswith('--from=') and ':' in word]
        for name in ('compose.prod.yml', 'compose.dev.yml', 'personal/compose.prod.yml'):
            text = (ROOT / 'backend/infra/deploy' / name).read_text(encoding='utf-8')
            references += [value for value in re.findall(r'^\s+image:\s+(\S+)', text, re.M) if '$' not in value]
        self.assertGreater(len(references), 15)
        for value in references:
            with self.subTest(image=value):
                self.assertRegex(value, r'^.+@sha256:[a-f0-9]{64}$')
                tag, digest = value.split('@')
                self.assertEqual(evidence[tag], digest)
