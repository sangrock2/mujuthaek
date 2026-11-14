create table publication_holds (
    event_id uuid primary key,
    event_type text not null,
    envelope jsonb not null,
    reason text not null,
    job_id uuid references extraction_jobs(id),
    created_at timestamptz not null default now(),
    released_at timestamptz
);
create index publication_holds_pending on publication_holds (created_at, event_id) where released_at is null;
comment on table publication_holds is '초기 표본 확인 또는 자동 검증 통과 전 보류한 공개 이벤트. 승인 후 같은 이벤트를 아웃박스에 한 번만 전달한다.';
