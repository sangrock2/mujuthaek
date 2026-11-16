"""Private operational reports; public Actions output contains status only."""
import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ACCOUNT = ''
REGION = 'ap-northeast-2'
BUCKET = ''
PREFIX = 'operations/monitor/'
BUDGET = RECIPIENT = SENDER = TEAM = PROJECT = CREDIT_EXPIRY = ''
USERS = CREDIT_LEVELS = ()
BUDGET_LIMIT = 0
EXPIRY_LEVELS = (30, 7, 1, 0)


def configure(config):
    """Deployment metadata lives in private configuration, never in public source."""
    global ACCOUNT, BUCKET, BUDGET, RECIPIENT, SENDER, TEAM, PROJECT, USERS
    global CREDIT_LEVELS, CREDIT_EXPIRY, BUDGET_LIMIT
    account = str(config['account'])
    levels = tuple(float(value) for value in config['credit_levels'])
    budget_limit = float(config['budget_limit'])
    if len(account) != 12 or not account.isdigit() or not levels:
        raise CheckError('Invalid private monitor configuration.')
    if any(not math.isfinite(value) or value < 0 for value in (*levels, budget_limit)):
        raise CheckError('Invalid private budget thresholds.')
    datetime.fromisoformat(config['credit_expiry'])
    ACCOUNT, BUCKET, BUDGET = account, config['bucket'], config['budget']
    RECIPIENT, SENDER = config['recipient'], config['sender']
    TEAM, PROJECT, USERS = config['vercel_team'], config['vercel_project'], tuple(config['iam_users'])
    CREDIT_LEVELS, CREDIT_EXPIRY, BUDGET_LIMIT = levels, config['credit_expiry'], budget_limit


class CheckError(Exception):
    """Safe fixed message only; never expose CLI/HTTP response bodies."""


def aws(*args, region=REGION, missing_ok=False):
    result = subprocess.run(['aws', *args, '--region', region, '--output', 'json', '--no-cli-pager'],
                            capture_output=True, text=True, timeout=90,
                            env=dict(os.environ, AWS_PAGER='', AWS_CLI_AUTO_PROMPT='off'))
    if result.returncode:
        if missing_ok and ('(NoSuchKey)' in result.stderr or '(404)' in result.stderr):
            return None
        raise CheckError('AWS check failed; inspect permissions and provider availability.')
    return json.loads(result.stdout or '{}')


def usd(value):
    amount = float(value['amount'] if 'amount' in value else value['Amount'])
    unit = value.get('unit', value.get('Unit'))
    if unit != 'USD' or not math.isfinite(amount) or amount < 0:
        raise CheckError('Invalid USD billing response.')
    return amount


def expiry_alert(name, expires, now, alerts):
    days = math.ceil((expires - now).total_seconds() / 86400)
    crossed = [level for level in EXPIRY_LEVELS if days <= level]
    if crossed:
        alerts[f'{name}:expiry:{expires.isoformat()}:{min(crossed)}'] = f'{name}: 만료까지 {days}일. 교체 또는 갱신을 확인하세요.'


def evaluate(report, now):
    alerts = {}
    if 'credits_usd' in report:
        crossed = [level for level in CREDIT_LEVELS if report['credits_usd'] <= level]
        if crossed:
            level = min(crossed)
            alerts[f'credits:{level:g}'] = f'AWS 크레딧이 ${level:g} 이하입니다. 잔액 ${report["credits_usd"]:.2f}.'
    for error in report.get('errors', []):
        alerts[f'error:{error}'] = error
    if 'budget_limit_usd' in report and (report['budget_limit_usd'] != BUDGET_LIMIT or report['budget_includes_credits']):
        alerts['budget-config'] = 'AWS 예산이 승인된 크레딧 차감 전 기준과 다릅니다.'
    if 'vercel' in report:
        token = report['vercel']
        if token.get('expires_at'):
            expiry_alert('Vercel 배포 토큰', datetime.fromisoformat(token['expires_at']), now, alerts)
    expiry_alert('AWS 크레딧(사용자 제공 만료일)', datetime.fromisoformat(CREDIT_EXPIRY).replace(tzinfo=timezone.utc), now, alerts)
    for key in report.get('iam_keys', []):
        if key['status'] != 'Active':
            continue
        age = (now - datetime.fromisoformat(key['created_at'])).days
        if age >= 75:
            level = 90 if age >= 90 else 75
            fingerprint = hashlib.sha256((key['user'] + key['created_at']).encode()).hexdigest()[:16]
            alerts[f'key-age:{fingerprint}:{level}'] = f'{key["user"]}: 생성 후 {age}일. 자동 만료는 없으며 안전한 순차 교체를 권합니다.'
    return alerts


def fresh_alerts(alerts, previous):
    # Only retain currently active conditions: refill/rotation/recovery re-arms alerts.
    return {key: value for key, value in alerts.items() if key not in previous.get('active', [])}


def vercel_get(path, token):
    request = urllib.request.Request('https://api.vercel.com' + path,
                                     headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise CheckError('Vercel token authentication or permission failed; replace/check VERCEL_TOKEN.') from None
        raise CheckError('Vercel provider request failed; check service availability or metadata access.') from None
    except (OSError, ValueError):
        raise CheckError('Vercel provider connection or response failed.') from None


def vercel_status(token):
    if not token:
        raise CheckError('VERCEL_TOKEN is missing in the monitor workflow.')
    project = vercel_get(f'/v9/projects/{PROJECT}?teamId={TEAM}', token)
    if project.get('id') != PROJECT:
        raise CheckError('Vercel project access could not be verified.')
    metadata = vercel_get('/v5/user/tokens/current', token)['token']
    if metadata.get('revokedAt') or metadata.get('leakedAt'):
        raise CheckError('Vercel deployment token is revoked or flagged as leaked; replace it.')
    dates = [metadata.get('expiresAt')]
    dates += [scope.get('expiresAt') for scope in metadata.get('scopes', [])
              if scope.get('type') == 'user' or scope.get('teamId') == TEAM]
    dates = [float(value) for value in dates if value is not None]
    expires = datetime.fromtimestamp(min(dates) / 1000, tz=timezone.utc).isoformat() if dates else None
    # Explicit allowlist: no bearer, ID, token name, prefix, suffix, or response dump.
    return {'project_access': True, 'expires_at': expires,
            'expiry_status': 'known' if expires else 'no_expiry_reported'}


def collect(now):
    report = {'checked_at': now.isoformat(), 'errors': [], 'credit_expiry_owner_supplied': CREDIT_EXPIRY}
    checks = {
        'AWS credits check unavailable': lambda: collect_credits(report),
        'AWS budget check unavailable': lambda: collect_budget(report),
        'IAM credential metadata check unavailable': lambda: collect_keys(report),
        'Vercel deployment credential check unavailable': lambda: report.update(vercel=vercel_status(os.environ.get('VERCEL_TOKEN'))),
    }
    for label, check in checks.items():
        try:
            check()
        except (CheckError, KeyError, TypeError, ValueError, subprocess.TimeoutExpired, OSError):
            report['errors'].append(label)
    return report


def collect_credits(report):
    plan = aws('freetier', 'get-account-plan-state', region='us-east-1')
    if plan.get('accountId') != ACCOUNT or plan.get('accountPlanStatus') != 'ACTIVE':
        raise CheckError('Unexpected account plan.')
    report.update(credits_usd=usd(plan['accountPlanRemainingCredits']), plan=plan['accountPlanType'])


def collect_budget(report):
    budget = aws('budgets', 'describe-budget', '--account-id', ACCOUNT, '--budget-name', BUDGET, region='us-east-1')['Budget']
    report.update(budget_limit_usd=usd(budget['BudgetLimit']),
                  budget_includes_credits=budget['CostTypes']['IncludeCredit'],
                  monthly_gross_usd=usd(budget['CalculatedSpend']['ActualSpend']))
    forecast = budget['CalculatedSpend'].get('ForecastedSpend')
    if forecast:
        report['monthly_forecast_usd'] = usd(forecast)
    if not budget_subscriptions(aws):
        raise CheckError('Owner budget subscriptions have changed.')


def budget_subscriptions(call):
    expected = {('ACTUAL', 50), ('ACTUAL', 80), ('ACTUAL', 100), ('FORECASTED', 100)}
    notifications = call('budgets', 'describe-notifications-for-budget', '--account-id', ACCOUNT,
                         '--budget-name', BUDGET, region='us-east-1')['Notifications']
    for notification in notifications:
        if notification.get('ComparisonOperator') != 'GREATER_THAN' or notification.get('ThresholdType', 'PERCENTAGE') != 'PERCENTAGE':
            continue
        value = {key: val for key, val in notification.items() if key != 'NotificationState'}
        subscribers = call('budgets', 'describe-subscribers-for-notification', '--account-id', ACCOUNT,
                            '--budget-name', BUDGET, '--notification', json.dumps(value), region='us-east-1')['Subscribers']
        if {'SubscriptionType': 'EMAIL', 'Address': RECIPIENT} in subscribers:
            expected.discard((notification['NotificationType'], notification['Threshold']))
    return not expected


def collect_keys(report):
    keys = []
    for user in USERS:
        for key in aws('iam', 'list-access-keys', '--user-name', user)['AccessKeyMetadata']:
            keys.append({'user': user, 'status': key['Status'], 'created_at': key['CreateDate']})
    report['iam_keys'] = keys


def read_state(directory):
    path = directory / 'state.json'
    result = aws('s3api', 'get-object', '--bucket', BUCKET, '--key', PREFIX + 'state.json', str(path), missing_ok=True)
    if result is None:
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('version') != 1 or not isinstance(value.get('active'), list):
        raise CheckError('Invalid private monitor state; do not reset alert deduplication silently.')
    return value


def put_json(directory, filename, data):
    path = directory / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    aws('s3api', 'put-object', '--bucket', BUCKET, '--key', PREFIX + filename,
        '--body', str(path), '--server-side-encryption', 'AES256', '--content-type', 'application/json')


def send_report(directory, report, alerts):
    lines = ['무주택자들 운영 점검', report['checked_at'], '', *alerts.values(), '',
             'AWS 비용·크레딧은 집계 지연이 있을 수 있습니다. 예산은 크레딧 차감 전 기준이며 자동 중지 한도가 아닙니다.',
             '크레딧 만료일은 사용자 제공 정보입니다. Billing → Credits에서 개별 만료일도 확인해 주세요.',
             'Vercel 토큰 교체: Vercel Account → Tokens에서 새 토큰 생성 → GitHub Actions secret VERCEL_TOKEN 교체.',
             'IAM 키는 만료일이 없으며, 권고 시 새 키 적용·발송/백업/배포 검증 후 기존 키를 비활성화합니다.',
             '', json.dumps(report, ensure_ascii=False, indent=2)]
    message = {'Subject': {'Data': '[무주택자들] 운영 점검 알림', 'Charset': 'UTF-8'},
               'Body': {'Text': {'Data': '\n'.join(lines), 'Charset': 'UTF-8'}}}
    path = directory / 'email.json'
    path.write_text(json.dumps(message, ensure_ascii=False), encoding='utf-8')
    aws('ses', 'send-email', '--from', SENDER, '--to', RECIPIENT, '--message', 'file://' + path.as_posix())


def run(send_snapshot=False):
    now = datetime.now(timezone.utc)
    if aws('sts', 'get-caller-identity')['Account'] != ACCOUNT:
        raise CheckError('Account mismatch.')
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        previous = read_state(directory)
        report = collect(now)
        alerts = evaluate(report, now)
        new = fresh_alerts(alerts, previous)
        put_json(directory, 'latest.json', report)
        if new or send_snapshot or not previous.get('initialized'):
            send_report(directory, report, new)
        # Commit delivery state only after successful SES send; failures retry next run.
        put_json(directory, 'state.json', {'version': 1, 'initialized': True, 'checked_at': now.isoformat(), 'active': list(alerts)})
        return not report['errors']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send-report', action='store_true')
    parser.add_argument('--verify-only', action='store_true',
                        help='Verify provider authentication without sending mail or writing state')
    args = parser.parse_args()
    try:
        configure(json.loads(os.environ['OPERATIONS_CONFIG']))
        if args.verify_only:
            if args.send_report:
                raise CheckError('Verification cannot send a report.')
            if aws('sts', 'get-caller-identity')['Account'] != ACCOUNT:
                raise CheckError('Account mismatch.')
            vercel_status(os.environ.get('VERCEL_TOKEN'))
            print('AWS OIDC and protected Vercel credential verified; no mail or monitor state changes.')
            return 0
        ok = run(args.send_report)
    except Exception:
        # Public repository: never print provider payloads, balances, token metadata or stack traces.
        print('Operations monitor failed. Check the private report and owner notifications.')
        return 1
    print('Operations monitor completed.' if ok else 'Operations monitor needs attention; owner notified privately.')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
