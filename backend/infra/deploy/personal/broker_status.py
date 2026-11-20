"""Read queue depth, extraction progress and outbox lag from the deployment host."""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BROKER = 'mujuthaek-personal-rabbitmq-1'
POSTGRES = 'mujuthaek-personal-postgres-1'
OUTBOXES = {'api': 'common.outbox', 'collector': 'outbox', 'extraction': 'outbox', 'notification': 'outbox'}
EXTRACTION_SQL = """
select json_build_object(
  'notice_events_processed_15m', (select count(*) from processed_events
      where event_type = 'raw.notice.collected' and processed_at >= now() - interval '15 minutes'),
  'policy_events_enqueued_15m', (select count(*) from outbox
      where created_at >= now() - interval '15 minutes' and
        (event_type = 'policy.extracted' or (event_type = 'extraction.completed'
          and payload->'payload'->>'field' in ('STARTUP_SUPPORT', 'SPACE_RECRUITMENT')))),
  'failed_24h', (select coalesce(json_object_agg(reason, count), '{}'::json) from (
      select case
        when error ilike '%credit_balance_exhausted%' then 'provider_credit_exhausted'
        when error like '%비용 상한%' then 'app_budget_limit'
        when error ilike '%timeout%' then 'timeout'
        else 'other' end as reason, count(*)
      from extraction_jobs where status='FAILED' and updated_at >= now() - interval '24 hours'
      group by 1) f),
  'active_claims', (select count(*) from extraction_claims where expires_at > now())
)
"""


def output(*args):
    return subprocess.run(args, check=True, capture_output=True, encoding='utf-8', timeout=15).stdout


def sql(database, statement):
    return json.loads(output(
        'docker', 'exec', '-e', 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5000',
        POSTGRES, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database, '-Atc', statement,
    ))


def queues(rows, now):
    result = {}
    for row in rows:
        name = row['name']
        if not name.startswith('mujuthaek.'):
            continue
        age = None
        head = row.get('head_message_timestamp')
        if type(head) is int and 0 < head <= now.timestamp():
            age = int(now.timestamp() - head)
        ready = row['messages_ready']
        result[name] = {
            'type': row['type'], 'ready': ready, 'unacked': row['messages_unacknowledged'],
            'consumers': row['consumers'], 'head_age_seconds': age if ready else None,
        }
    return result


def collect(now):
    rows = json.loads(output(
        'docker', 'exec', BROKER, 'rabbitmqctl', '-q', 'list_queues', '-p', '/',
        'name', 'type', 'messages_ready', 'messages_unacknowledged', 'consumers', 'head_message_timestamp',
        '--formatter', 'json',
    ))
    snapshot = {
        'checked_at': now.isoformat(),
        'queues': queues(rows, now),
        'extraction': sql('extraction', EXTRACTION_SQL),
        'outboxes': {},
    }
    for database, table in OUTBOXES.items():
        snapshot['outboxes'][database] = sql(database, f"""
            select json_build_object('pending', count(*), 'max_attempts', coalesce(max(attempts), 0),
              'oldest_pending_seconds', extract(epoch from now() - min(created_at))::bigint)
            from {table} where published_at is null
        """)
    return snapshot


def compare(current, previous):
    interval = (datetime.fromisoformat(current['checked_at']) - datetime.fromisoformat(previous['checked_at']))
    seconds = interval.total_seconds()
    if seconds <= 0:
        raise ValueError('The previous sample must be older than the current sample')
    before = previous['queues']
    for name, status in current['queues'].items():
        if name in before:
            change = sum(status[key] - before[name][key] for key in ('ready', 'unacked'))
            status['outstanding_delta_per_minute'] = round(change * 60 / seconds, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, help='Compare a prior JSON sample from this host')
    args = parser.parse_args()
    try:
        snapshot = collect(datetime.now(timezone.utc))
        if args.previous:
            compare(snapshot, json.loads(args.previous.read_text(encoding='utf-8-sig')))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise SystemExit('Broker status unavailable. Check host access, RabbitMQ and database connectivity.') from None
    print(json.dumps(snapshot, indent=2))


if __name__ == '__main__':
    main()
