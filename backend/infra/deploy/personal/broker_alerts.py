"""Evaluate broker health on the production host without consuming messages."""

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import broker_status
import slack_alerts

QUEUES = {
    'mujuthaek.raw.collected': '공고 추출 입력',
    'mujuthaek.raw.policy': '정책 추출 입력',
    'mujuthaek.extraction.completed': '공고 공개 결과',
    'mujuthaek.policy.extracted': '혜택 공개 결과',
    'mujuthaek.area.source-ready': '생활권 자료 적재',
    'mujuthaek.notification': '알림 발송',
    'mujuthaek.api.push-subscription-expired': '만료된 푸시 구독 정리',
}
AGE_LIMIT_SECONDS = 15 * 60
DEPTH_LIMIT = 20


def evaluate(snapshot, previous):
    old_ready = previous.get('ready', {})
    observed, immediate = {}, {}
    ready = {}
    queues = snapshot['queues']
    for queue, label in QUEUES.items():
        status = queues.get(queue)
        if status is not None:
            depth = status['ready']
            ready[queue] = depth
            reason = None
            if depth and not status['consumers']:
                reason = '대기 작업이 있지만 소비자가 없습니다.'
            elif depth and (status['head_age_seconds'] or 0) >= AGE_LIMIT_SECONDS:
                reason = '가장 오래된 작업이 15분 이상 대기 중입니다.'
            elif depth >= DEPTH_LIMIT and queue in old_ready and depth >= old_ready[queue]:
                reason = '대기 20건 이상이 이전 점검보다 줄지 않았습니다.'
            if reason:
                observed[f'queue:{queue}'] = f'{label} · {reason} 대기 {depth}건, 처리 중 {status["unacked"]}건.'
        dead = queues.get(queue + '.dlq')
        if dead and dead['ready']:
            immediate[f'dlq:{queue}'] = f'{label} · 실패 큐에 {dead["ready"]}건이 있습니다.'

    for service, status in snapshot['outboxes'].items():
        if service in broker_status.OUTBOXES and (status['oldest_pending_seconds'] or 0) >= AGE_LIMIT_SECONDS:
            observed[f'outbox:{service}'] = f'{service} · 15분 이상 발행되지 않은 이벤트가 있습니다. 총 미발행 {status["pending"]}건.'

    prior = set(previous.get('observed', []))
    active = {**immediate, **{key: message for key, message in observed.items() if key in prior}}
    return active, list(observed), ready


def write_state(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode='w', encoding='utf-8', delete=False) as output:
        staged = Path(output.name)
        try:
            json.dump(value, output)
            output.close()
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


def run(state_path, webhook):
    try:
        previous = json.loads(state_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        previous = {}
    delivered = set(previous.get('active', []))
    try:
        snapshot = broker_status.collect(datetime.now(timezone.utc))
        active, observed, ready = evaluate(snapshot, previous)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        if previous.get('unavailable') and 'monitor-unavailable' not in delivered:
            slack_alerts.send(webhook, '[무주택자들] RabbitMQ 점검',
                              ['RabbitMQ 또는 DB 상태를 두 차례 연속 조회하지 못했습니다.'])
            delivered.add('monitor-unavailable')
        write_state(state_path, {**previous, 'active': sorted(delivered), 'unavailable': True})
        return False
    fresh = [message for key, message in active.items() if key not in delivered]
    if fresh:
        slack_alerts.send(webhook, '[무주택자들] RabbitMQ 운영 알림', fresh)
    write_state(state_path, {'active': list(active), 'observed': observed, 'ready': ready})
    print('RabbitMQ monitor completed.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-slack', action='store_true')
    arguments = parser.parse_args()
    try:
        webhook = (Path(os.environ['CREDENTIALS_DIRECTORY']) / 'slack-webhook').read_text().strip()
        if arguments.test_slack:
            slack_alerts.send(webhook, '[무주택자들] 운영 알림 연결 확인',
                              ['RabbitMQ 적체 및 운영 알림용 Slack 연결을 확인했습니다.'])
            return 0
        return 0 if run(Path(os.environ['STATE_DIRECTORY']) / 'state.json', webhook) else 1
    except (OSError, ValueError, TypeError, KeyError, slack_alerts.SlackError):
        print('RabbitMQ monitor failed. Check private configuration and provider availability.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
