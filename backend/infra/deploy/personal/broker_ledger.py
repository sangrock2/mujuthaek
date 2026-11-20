"""Read the housing notice pipeline and build a broker-loss reconciliation plan."""

import argparse
import json
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

POSTGRES = 'mujuthaek-personal-postgres-1'
# Persisted namespace used by extraction.store._judgment_keys.
JUDGMENT_NAMESPACE = UUID('5b0c8f9e-2f0a-4f41-9d7e-3f1c2a6b9d10')


def read(database, sql):
    command = ['docker', 'exec', '-i', '-e',
               'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=8000',
               POSTGRES, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database, '-At']
    result = subprocess.run(command, input=sql.encode(), capture_output=True, check=False, timeout=15)
    if result.returncode:
        raise RuntimeError(f'Read-only {database} query failed')
    return json.loads(result.stdout)


def ids(values):
    return ','.join(f"'{UUID(str(value))}'::uuid" for value in values) or 'null::uuid'


def aggregate(select):
    return f"select coalesce(json_agg(x order by x.at, x.stage, to_jsonb(x)::text),'[]'::json) from ({select}) x;"


def policy_receipt_keys(row):
    keys = [str(uuid5(JUDGMENT_NAMESPACE, str(UUID(row['event_id']))))]
    if row.get('reprocess') or type(row.get('raw_version')) is not int:
        return keys
    try:
        policy = UUID(row.get('raw_policy_id') or '')
    except ValueError:
        return keys
    keys.append(str(uuid5(JUDGMENT_NAMESPACE, f"{policy}/v{row['raw_version']}")))
    return keys


def trace(fetch, lookup_id, kind):
    key = ids([lookup_id])
    if kind == 'notice':
        targets = fetch('api', f"select coalesce(json_agg(raw_post_id order by raw_post_id),'[]'::json) "
                              f"from (select raw_post_id from notice.notice_posts where notice_id={key} limit 21) p;")
        if not targets:
            return {'notice_id': str(lookup_id), 'found': False}
        if len(targets) > 20:
            raise ValueError('More than 20 source posts. Run with --raw-post instead.')
    else:
        targets = [str(lookup_id)]
    selected = ids(targets)
    collector = fetch('collector', aggregate(f"""
        select 'collected' stage, v.collected_at at, v.raw_post_id, v.version raw_version,
               null::uuid event_id, 'COLLECTED' status, v.crawl_run_id reference
        from raw_post_versions v where v.raw_post_id in ({selected})
        union all
        select 'collector_outbox', coalesce(o.published_at,o.created_at), p.id,
               case when o.payload->'payload'->>'version' ~ '^[0-9]{{1,9}}$'
                    then (o.payload->'payload'->>'version')::int end, o.event_id,
               case when o.published_at is null then 'PENDING' else 'PUBLISHED' end, null
        from raw_posts p join outbox o on o.payload->'payload'->>'rawPostId'=p.id::text
        where p.id in ({selected}) and o.event_type='raw.notice.collected'
        order by at desc limit 201
    """))
    extraction = fetch('extraction', aggregate(f"""
        select 'extraction_attempt' stage, j.created_at at, j.raw_post_id, j.raw_version,
               j.event_id, j.status, j.id reference
        from extraction_jobs j where j.raw_post_id in ({selected})
        union all
        select 'review_open', r.created_at, j.raw_post_id, j.raw_version, j.event_id, 'PENDING', r.job_id
        from extraction_jobs j join review_queue r on r.job_id=j.id where j.raw_post_id in ({selected})
        union all
        select 'review_decision', r.decided_at, j.raw_post_id, j.raw_version, j.event_id, r.status, r.job_id
        from extraction_jobs j join review_queue r on r.job_id=j.id
        where j.raw_post_id in ({selected}) and r.decided_at is not null
        union all
        select 'extraction_outbox', coalesce(o.published_at,o.created_at), j.raw_post_id, j.raw_version,
               o.event_id, case when o.published_at is null then 'PENDING' else 'PUBLISHED' end, j.id
        from extraction_jobs j join outbox o on o.event_id=j.completed_event_id where j.raw_post_id in ({selected})
        order by at desc limit 201
    """))
    api = fetch('api', aggregate(f"""
        select 'api_received' stage, r.received_at at, r.raw_post_id, r.raw_version,
               r.event_id, r.outcome status, r.notice_id reference
        from notice.extraction_results r where r.raw_post_id in ({selected})
        union all
        select 'notice_published', v.created_at, v.raw_post_id, v.raw_version,
               v.source_event_id, v.review_status, v.notice_id
        from notice.notice_versions v where v.raw_post_id in ({selected})
        order by at desc limit 201
    """))
    stages = sorted([*collector[-200:], *extraction[-200:], *api[-200:]], key=lambda row: row['at'])
    return {'raw_post_ids': targets, 'found': bool(stages), 'truncated': any(len(s) > 200 for s in (collector, extraction, api)),
            'stages': stages}


def plan(fetch, hours, limit, end=None):
    end = (end or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    lanes = (
        ('notice_input', 'collector', 'extraction', 'raw.notice.collected', 'processed_events'),
        ('notice_result', 'extraction', 'api', 'extraction.completed', 'common.processed_events'),
        ('policy_input', 'collector', 'extraction', 'raw.policy.collected', 'processed_events'),
        ('benefit_result', 'extraction', 'api', 'policy.extracted', 'common.processed_events'),
    )
    results = {}
    for lane, producer, consumer, event_type, receipt_table in lanes:
        fields = 'event_id, published_at'
        if lane == 'policy_input':
            fields += """,
                payload->'payload'->>'rawPolicyId' raw_policy_id,
                payload->'payload'->'version' raw_version,
                payload->'payload'->'reprocess' reprocess"""
        rows = fetch(producer, f"""
            select coalesce(json_agg(x order by x.published_at, x.event_id),'[]'::json) from (
                select {fields} from outbox
                where event_type='{event_type}' and published_at >= '{start.isoformat()}'::timestamptz
                  and published_at < '{end.isoformat()}'::timestamptz
                order by published_at, event_id limit {int(limit) + 1}
            ) x;
        """)
        batch = rows[:limit]
        policy_mapping = {row['event_id']: policy_receipt_keys(row) for row in batch} if lane == 'policy_input' else {}
        selected = ids(dict.fromkeys(key for keys in policy_mapping.values() for key in keys) if policy_mapping
                       else (row['event_id'] for row in batch))
        acked = set(fetch(consumer, f"select coalesce(json_agg(event_id),'[]'::json) from "
                                    f"{receipt_table} where event_id in ({selected});"))
        attempts = set()
        if lane == 'notice_input':
            attempts.update(fetch(consumer, f"select coalesce(json_agg(distinct event_id),'[]'::json) "
                                           f"from extraction_jobs where event_id in ({selected});"))
        elif lane == 'notice_result':
            acked.update(fetch(consumer, f"select coalesce(json_agg(event_id),'[]'::json) from "
                                        f"notice.extraction_results where event_id in ({selected});"))
        elif policy_mapping:
            acked = {event for event, keys in policy_mapping.items() if acked.intersection(keys)}
        missing = [row['event_id'] for row in batch if row['event_id'] not in acked | attempts]
        evidence_key = 'needs_manual_policy_review' if lane == 'policy_input' else 'without_consumer_evidence'
        results[lane] = {'scanned': min(len(rows), limit), 'truncated': len(rows) > limit,
                         'consumer_record': len(acked), 'attempt_without_receipt': len(attempts - acked),
                         evidence_key: missing}
    return {'window_hours': hours, 'window_start': start.isoformat(), 'window_end': end.isoformat(), 'lanes': results}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('Specify an ISO 8601 timestamp with a timezone.') from error
    if result.utcoffset() is None:
        raise argparse.ArgumentTypeError('The timestamp must include a timezone.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    tracing = commands.add_parser('trace')
    key = tracing.add_mutually_exclusive_group(required=True)
    key.add_argument('--notice', type=UUID)
    key.add_argument('--raw-post', type=UUID)
    planning = commands.add_parser('plan')
    planning.add_argument('--hours', type=int, choices=range(1, 169), default=24, metavar='1-168')
    planning.add_argument('--limit', type=int, choices=range(1, 1001), default=500, metavar='1-1000')
    planning.add_argument('--end', type=timestamp, help='Fixed exclusive end of the recovery window')
    args = parser.parse_args()
    if args.command == 'trace':
        result = trace(read, args.notice or args.raw_post, 'notice' if args.notice else 'raw_post')
    else:
        result = plan(read, args.hours, args.limit, args.end)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
