-- 이미 발행한 결과를 검수로 다시 열기 (2026-10-25, 관리자 화면: 사용자 제보로 공고 값을 고칠 때).
-- review_queue는 작업마다 한 줄이라, 다시 열 때 앞선 처리 기록을 여기로 옮겨 두고 그 줄을 대기(PENDING)로 되돌립니다.
create table review_history (
    id          bigserial primary key,
    job_id      uuid        not null references extraction_jobs (id),
    status      text        not null,
    reasons     jsonb       not null,
    note        text,
    created_at  timestamptz not null,
    decided_at  timestamptz,
    decided_by  text,
    edited      boolean     not null,
    edits       jsonb,
    archived_at timestamptz not null default now(),
    reopened_by text,                 -- 다시 연 관리자 (api 로그인 계정 ID)
    reopen_note text                  -- 다시 연 까닭 (예: 공고 제보)
);
create index review_history_job_idx on review_history (job_id, archived_at);

comment on table review_history is '검수를 다시 열기 전의 처리 기록(승인·반려). 다시 열 때마다 한 줄';
