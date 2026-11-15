"""Compare an isolated historical tree and the current tree without changing either service."""
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / 'backend/services/api'
BASELINE = '6d278c285a8adb3b95782288242a239b14c3d990'
TEST_CLASS = 'kr.mujuthaek.api.user.security.HistoricalLogoutRegressionTest'
CASE = 'oldTokenMustNotResumeALoggedOutSession'


def test(directory, test_class, *cases):
    args = ['bash', './gradlew', '--no-daemon', 'test']
    for case in cases:
        args.extend(['--tests', test_class + '.' + case])
    return subprocess.run(args, cwd=directory, capture_output=True, text=True, timeout=1200)


def report(directory, test_class):
    return directory / f'build/test-results/test/TEST-{test_class}.xml'


def main():
    output = SERVICE / 'build/reports/security'
    output.mkdir(parents=True, exist_ok=True)
    fixture = Path(__file__).resolve().parent / 'fixtures/HistoricalLogoutRegressionTest.java'
    relative = Path('src/test/java/kr/mujuthaek/api/user/security/HistoricalLogoutRegressionTest.java')
    with tempfile.TemporaryDirectory(prefix='security-baseline-') as temporary:
        baseline = Path(temporary)
        archive = baseline / 'source.tar'
        subprocess.run(['git', 'archive', '--format=tar', BASELINE, '-o', str(archive)], cwd=ROOT, check=True, timeout=60)
        with tarfile.open(archive) as source:
            source.extractall(baseline, filter='data')
        old_service = baseline / 'backend/services/api'
        shutil.copyfile(fixture, old_service / relative)
        before = test(old_service, TEST_CLASS, CASE)
        (output / 'baseline.log').write_text(before.stdout + before.stderr, encoding='utf-8')
        old_report = report(old_service, TEST_CLASS)
        if not before.returncode or not old_report.exists():
            raise RuntimeError('Historical logout regression was not reproduced')
        cases = [case for case in ET.parse(old_report).getroot().findall('testcase') if case.attrib['name'].startswith(CASE)]
        failures = [failure for case in cases for failure in case.findall('failure')]
        if len(failures) != 1 or 'Status expected:<401> but was:<200>' not in failures[0].attrib.get('message', ''):
            raise RuntimeError('Historical failure is not the expected security assertion')
        shutil.copyfile(old_report, output / 'baseline.xml')
    target = SERVICE / relative
    if target.exists():
        raise RuntimeError('Refusing to replace a current test file')
    try:
        shutil.copyfile(fixture, target)
        after = test(SERVICE, TEST_CLASS, CASE)
        (output / 'patched.log').write_text(after.stdout + after.stderr, encoding='utf-8')
        if after.returncode:
            raise RuntimeError('Patched historical HTTP scenario failed')
        shutil.copyfile(report(SERVICE, TEST_CLASS), output / 'patched.xml')
    finally:
        target.unlink(missing_ok=True)
    (output / 'logout-proof.json').write_text(json.dumps({'baseline_commit': BASELINE,
        'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'baseline_expected_401_actual_200': True, 'patched_same_scenario_passed': True}, indent=2), encoding='utf-8')
    print('Historical logout flaw reproduced in isolated tree; current same-scenario verification passed.')


if __name__ == '__main__':
    main()
