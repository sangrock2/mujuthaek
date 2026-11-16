"""Verify narrowly identified CI metadata gaps against Maven Central's published SHA256."""
import hashlib
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = (
    ('org.junit', 'junit-bom', '5.10.2', 'module'),
    ('org.junit', 'junit-bom', '5.11.4', 'module'),
    ('com.google.guava', 'guava-parent', '32.1.3-jre', 'pom'),
)


def main():
    for group, name, version, extension in ARTIFACTS:
        filename = f'{name}-{version}.{extension}'
        url = f'https://repo.maven.apache.org/maven2/{group.replace(".", "/")}/{name}/{version}/{filename}'
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read(4 * 1024 * 1024 + 1)
        digest = hashlib.sha256(content).hexdigest()
        origin = 'Verified against Maven Central SHA256'
        try:
            with urllib.request.urlopen(url + '.sha256', timeout=30) as response:
                expected = response.read(512).decode('ascii').split()[0]
            verified = bool(re.fullmatch('[a-f0-9]{64}', expected) and digest == expected)
        except urllib.error.HTTPError as error:
            if error.code != 404 or (group, name, version, extension) != ARTIFACTS[2]:
                raise
            # This older parent POM publishes SHA1 only. Cross-check both official TLS endpoints;
            # the committed enforcement checksum is still SHA256, with no trusted-artifact exception.
            with urllib.request.urlopen(url + '.sha1', timeout=30) as response:
                legacy = response.read(512).decode('ascii').split()[0]
            with urllib.request.urlopen(url.replace('repo.maven.apache.org', 'repo1.maven.org'), timeout=30) as response:
                independent = response.read(4 * 1024 * 1024 + 1)
            verified = (bool(re.fullmatch('[a-f0-9]{40}', legacy))
                        and hashlib.sha1(content).hexdigest() == legacy and independent == content)
            origin = 'SHA256 pinned from both Maven Central TLS endpoints; legacy published SHA1 cross-checked'
        if len(content) > 4 * 1024 * 1024 or not verified:
            raise RuntimeError('Published SHA256 mismatch; verification metadata unchanged')
        for service in ('api', 'notification'):
            path = ROOT / f'backend/services/{service}/gradle/verification-metadata.xml'
            text = path.read_text(encoding='utf-8')
            component = f'      <component group="{group}" name="{name}" version="{version}">'
            artifact = (f'         <artifact name="{filename}">\n'
                        f'            <sha256 value="{digest}" origin="{origin}"/>\n'
                        '         </artifact>\n')
            if component in text:
                start = text.index(component)
                end = text.index('      </component>', start)
                block = text[start:end]
                if f'<artifact name="{filename}">' in block:
                    if digest not in block:
                        raise RuntimeError('Existing expected checksum differs; refused replacement')
                    continue
                text = text[:end] + artifact + text[end:]
            else:
                text = text.replace('   </components>', component + '\n' + artifact + '      </component>\n   </components>')
            path.write_text(text, encoding='utf-8')
        print(filename + ': ' + origin)


if __name__ == '__main__':
    main()
