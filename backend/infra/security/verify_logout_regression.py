"""Reproduce the historical logout flaw in disposable CI, then verify the fix."""
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / 'backend/services/api'
SOURCE = Path('backend/services/api/src/main/java/kr/mujuthaek/api/user/service/AuthTokenService.java')
BASELINE = '6d278c285a8adb3b95782288242a239b14c3d990'
TEST_CLASS = 'kr.mujuthaek.api.user.security.SecurityIntegrationTest'
CASE = 'logoutRevokesGraceTokenAndSiblingButKeepsAnotherLogin'


def test(*cases):
    args = ['bash', './gradlew', '--no-daemon', 'test']
    for case in cases:
        args.extend(['--tests', TEST_CLASS + '.' + case])
    return subprocess.run(args, cwd=SERVICE, capture_output=True, text=True, timeout=1200)


def main():
    output = SERVICE / 'build/reports/security'
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / SOURCE
    current = source.read_bytes()
    report = SERVICE / f'build/test-results/test/TEST-{TEST_CLASS}.xml'
    try:
        historical = subprocess.run(['git', 'show', f'{BASELINE}:{SOURCE.as_posix()}'], cwd=ROOT,
                                    capture_output=True, check=True, timeout=30).stdout
        source.write_bytes(historical)
        if report.exists():
            report.unlink()
        before = test(CASE)
        (output / 'baseline.log').write_text(before.stdout + before.stderr, encoding='utf-8')
        if not before.returncode or not report.exists():
            raise RuntimeError('Historical regression must fail for the specific logout assertion')
        cases = [case for case in ET.parse(report).getroot().findall('testcase') if case.attrib['name'].startswith(CASE)]
        failures = [failure for case in cases for failure in case.findall('failure')]
        if len(failures) != 1 or 'Status expected:<401> but was:<200>' not in failures[0].attrib.get('message', ''):
            raise RuntimeError('Historical test failed for a different reason; this is not security reproduction evidence')
        shutil.copyfile(report, output / 'baseline.xml')
    finally:
        source.write_bytes(current)
    after = test(CASE, 'racingLogoutAndRefreshCannotLeaveARefreshSessionAlive')
    (output / 'patched.log').write_text(after.stdout + after.stderr, encoding='utf-8')
    if after.returncode:
        raise RuntimeError('Patched logout or concurrency regression failed')
    shutil.copyfile(report, output / 'patched.xml')
    (output / 'logout-proof.json').write_text(json.dumps({'baseline_commit': BASELINE,
        'baseline_reproduced': True, 'baseline_expected_401_actual_200': True,
        'patched_logout_and_race_tests_passed': True}, indent=2), encoding='utf-8')
    print('Historical logout flaw reproduced; patched logout and concurrency checks passed.')


if __name__ == '__main__':
    main()
