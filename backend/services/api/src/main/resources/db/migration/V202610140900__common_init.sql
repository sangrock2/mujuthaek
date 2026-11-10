-- 마이그레이션 파일 이름: V<연월일시분>__<모듈>_<설명>.sql (여러 명이 동시에 만들어도 안 겹치게)
create table if not exists common.processed_events (
    event_id     uuid primary key,
    event_type   text        not null,
    processed_at timestamptz not null default now()
);
