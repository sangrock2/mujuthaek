-- 주거·이주 혜택 정제 결과와 검수 (2026-10-25, 관리자 혜택 검수·정책 제보).
-- benefit_results: 발행한 policy.extracted payload를 정책·버전마다 쌓습니다(검수 승인·반려로 다시 발행하면 한 줄 더).
-- benefit_reviews: 확인 필요(needsReview) 결과와 제보로 다시 연 결과의 검수. 같은 정책의 대기 건은 하나만 둡니다.
create table benefit_results (
    id             uuid        primary key,
    raw_policy_id  uuid        not null,
    raw_version    integer     not null,
    source_code    text        not null,
    policy_id      text        not null,
    title          text        not null,
    event_id       uuid        not null unique,  -- 발행한 policy.extracted eventId
    payload        jsonb       not null,
    source_payload jsonb,                        -- 받은 raw.policy.collected payload(검수 화면의 원문). 다시 발행한 줄은 null
    origin         text        not null check (origin in ('EXTRACTED', 'APPROVED', 'REJECTED')),
    created_at     timestamptz not null default now()
);
create index benefit_results_policy_idx on benefit_results (raw_policy_id, created_at desc);

create table benefit_reviews (
    id                  uuid        primary key,
    result_id           uuid        not null references benefit_results (id),
    raw_policy_id       uuid        not null,
    raw_version         integer     not null,
    reasons             jsonb       not null,  -- quality.reviewReasons, 제보로 다시 열면 ["REPORTED"] 추가
    status              text        not null default 'PENDING' check (status in ('PENDING', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    note                text,
    opened_by           text,                  -- 제보로 다시 연 관리자 (자동으로 연 건은 null)
    created_at          timestamptz not null default now(),
    decided_at          timestamptz,
    decided_by          text,
    edits               jsonb,                 -- 칸별 수정 [{path, before, after}]
    published_result_id uuid        references benefit_results (id)
);
create index benefit_reviews_status_idx on benefit_reviews (status, created_at);
create unique index benefit_reviews_one_pending on benefit_reviews (raw_policy_id) where status = 'PENDING';

comment on table benefit_results is '발행한 혜택 정제 결과(policy.extracted payload). 정책마다 가장 새 줄이 현재 값';
comment on table benefit_reviews is '혜택 정제 결과 검수. 승인하면 고친 결과를, 반려하면 relevant=false 결과를 다시 발행';
