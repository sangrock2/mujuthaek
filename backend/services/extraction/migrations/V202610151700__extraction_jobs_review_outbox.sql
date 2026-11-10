-- 추출 작업 기록, 검수 대기열, 아웃박스 (B5)
-- 사용자 소득·자산·나이는 이 서비스에 들어오지 않습니다(공고 원문과 추출 결과만 저장).

-- 받은 raw.notice.collected 1건당 처리 1회. 다시 처리하면 새 행이 생깁니다(같은 event_id로 여러 번 가능).
create table extraction_jobs (
    id                 uuid primary key,
    event_id           uuid not null,          -- 받은 이벤트의 eventId
    raw_post_id        uuid,                   -- 형식이 잘못된 이벤트(REJECTED)면 비어 있을 수 있음
    raw_version        int,
    source_code        text,
    field              text,
    status             text not null,          -- COMPLETED·IN_REVIEW·INTAKE_REVIEW·WAITING_SOURCE·FAILED·REJECTED·UNSUPPORTED·APPROVED
    model_used         text,                   -- local·gpt-6-luna·recorded
    cost_usd           numeric(10, 4) not null default 0,  -- 유료 API 추정 비용 (청구 금액 아님)
    attempts           jsonb not null default '[]',        -- 모델 호출 기록 (호출 이름·토큰·오류)
    ai_responses       jsonb not null default '[]',        -- AI 응답 원문 [호출 이름, 응답] (원인 확인·재현용. 공고 내용만 있음)
    candidate          jsonb,                  -- 검증까지 끝난 표준 공고 후보 (extracted-notice v1)
    raw_event          jsonb not null,         -- 다시 처리할 때 쓰는 받은 이벤트 전체
    completed_event_id uuid,                   -- 발행한 extraction.completed의 eventId
    error              text,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
create index extraction_jobs_raw_idx on extraction_jobs (raw_post_id, raw_version);
create index extraction_jobs_status_idx on extraction_jobs (status, created_at);

-- 사람이 확인할 공고. 검수 API(:8092)가 조회·승인·반려합니다.
create table review_queue (
    job_id     uuid primary key references extraction_jobs (id),
    status     text not null default 'PENDING',   -- PENDING·APPROVED·REJECTED
    reasons    jsonb not null default '[]',        -- 사람 확인이 필요한 이슈 (코드 + 위치)
    note       text,                               -- 검수자 메모
    created_at timestamptz not null default now(),
    decided_at timestamptz
);
create index review_queue_status_idx on review_queue (status, created_at);

-- 팀 공통 아웃박스 (libs/python-platform/README.md와 같은 모양). payload에는 봉투 전체가 들어갑니다.
create table outbox (
    event_id       uuid primary key,
    event_type     text not null,
    schema_version int  not null,
    payload        jsonb not null,
    created_at     timestamptz not null default now(),
    published_at   timestamptz,
    attempts       int  not null default 0
);
create index outbox_unpublished_idx on outbox (created_at) where published_at is null;
