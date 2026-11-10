-- extraction 데이터베이스: 이미 처리한 이벤트 명단 (팀 이벤트 흐름 문서 7절, 2026-10-15).
-- 메시지가 오면 먼저 event_id를 넣어 보고, 들어가면 처음 보는 이벤트라 처리하고, 이미 있으면 건너뜁니다.
-- 처리 결과 저장과 같은 트랜잭션에서 넣으므로, 처리 중 실패하면 이 기록도 함께 취소되어 다시 받았을 때 정상 처리됩니다.
-- 형식은 api의 common.processed_events와 같습니다.
create table processed_events (
    event_id     uuid primary key,
    event_type   text        not null,                -- 예: raw.notice.collected, raw.policy.collected
    processed_at timestamptz not null default now()
);
