-- 혜택(정책) 저장 (2026-10-26). 정책 추출 결과(policy.extracted) 한 건 = benefits 1줄 + 지원 내용 0~N줄 + 자격 조건 0~N줄.
-- 설계: contracts/schemas/policy-extracted.draft.md 4장 그대로 + category(화면 분야, 저장할 때 계산).
create table benefit.benefits (
    id                uuid primary key,                       -- UUID v7
    raw_policy_id     uuid        not null unique,            -- 수집 DB 정책 ID (이벤트 키)
    source_code       text        not null,
    provider          text        not null,
    source_policy_id  text        not null,
    source_version    int         not null,                   -- 마지막으로 반영한 수집 버전
    field             text        not null,                   -- BENEFIT, STARTUP_SUPPORT
    category          text        not null check (category in ('HOUSING', 'ASSET', 'TRANSPORT')),
    -- 통일 기본 칸 (이벤트 source 그대로)
    title             text        not null,
    agency            text,
    region_scope      text        not null,                   -- NATIONWIDE, SIDO, SIGUNGU, UNKNOWN
    region_names      text[]      not null default '{}',
    region_codes      text[]      not null default '{}',      -- 시도 2자리 / 시군구 5자리
    categories        text[]      not null default '{}',
    detail_url        text,
    apply_url         text,
    -- AI·규칙 추출
    summary           text,
    apply_start       date,
    apply_end         date,
    apply_always      boolean     not null default false,
    business_start    date,
    business_end      date,
    schedule_text     text,
    how_to_apply      text,
    documents         text[]      not null default '{}',
    contact           text,
    -- 상태·신뢰도
    status            text        not null check (status in ('UPCOMING', 'OPEN', 'CLOSED', 'HIDDEN')),
    relevant          boolean     not null,
    confidence        numeric(3,2),
    needs_review      boolean     not null default false,
    review_reasons    text[]      not null default '{}',
    has_document      boolean     not null,
    extracted_at      timestamptz not null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (source_code, source_policy_id)
);

create index benefits_open_idx on benefit.benefits (field, status, apply_end);
create index benefits_region_idx on benefit.benefits using gin (region_codes);

create table benefit.benefit_supports (
    id          uuid primary key,
    benefit_id  uuid not null references benefit.benefits (id) on delete cascade,
    ordinal     int  not null,
    kind        text not null,
    amount_max  int,                                          -- 만 원
    amount_per  text,                                         -- ONCE, MONTH, YEAR
    months      int,
    rate_pct    int,
    raw_text    text not null,
    evidence    text not null
);

create index benefit_supports_benefit_idx on benefit.benefit_supports (benefit_id);

create table benefit.benefit_conditions (
    id          uuid primary key,
    benefit_id  uuid not null references benefit.benefits (id) on delete cascade,
    ordinal     int  not null,
    type        text not null,                                -- benefit-condition-types 3장
    value       jsonb,                                        -- known=false면 null
    grp         int  not null,                                -- 같은 번호 "또는", 다른 번호 "그리고"
    known       boolean not null,
    raw_text    text not null,
    evidence    text not null,
    confidence  numeric(3,2) not null,
    origin      text not null                                 -- RULE, AI
);

create index benefit_conditions_benefit_idx on benefit.benefit_conditions (benefit_id);
create index benefit_conditions_type_idx on benefit.benefit_conditions (type);
