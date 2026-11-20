-- 공고 공개 트랜잭션에서 위치 작업을 저장합니다. 공고별 최신 작업 한 줄만 유지합니다.
create table area.notice_location_jobs (
    notice_id       uuid primary key,
    notice_version  int not null check (notice_version > 0),
    locations       jsonb not null check (jsonb_typeof(locations) = 'array'),
    run_at          timestamptz not null default now(),
    claim_token     uuid,
    failures        int not null default 0 check (failures between 0 and 5),
    finished_at     timestamptz,
    last_error      text
);

create index notice_location_jobs_due_idx on area.notice_location_jobs (run_at, notice_id)
    where finished_at is null and failures < 5;
