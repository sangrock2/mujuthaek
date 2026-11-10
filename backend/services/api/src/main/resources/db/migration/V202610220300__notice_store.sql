-- 공고 저장. extraction.completed를 받아 원본 버전(notice_sources)으로 쌓고, 공고(notices)는 현재 버전을 가리켜요.
-- 상세 화면은 현재 버전의 내용(payload의 notice)을 그대로 쓰고, 목록·검색에 쓰는 값만 notices에 칸으로 빼요.

-- 공고 하나. 원래 모집공고(NOTICE)의 rawPostId로 만들어지고, 정정공고는 같은 공고의 새 버전이 돼요.
create table notice.notices (
    id                  uuid        primary key,
    raw_post_id         uuid        not null unique,      -- 이 공고를 처음 만든 원본(모집공고)
    field               text        not null check (field in ('HOUSING', 'BUSINESS_SPACE')),
    title               text        not null,
    provider            text,                             -- 공급 기관 (LH, SH, GH …)
    notice_type         text,                             -- HAPPY_HOUSING, NATIONAL_RENTAL … (모르면 null)
    supply_type_text    text,                             -- 원문 공급 유형 (매입임대 …)
    region_code         text        check (region_code ~ '^[0-9]{5}$'),
    apply_start         date,
    apply_end           date,
    posted_on           date,
    summary_text        text,
    detail_url          text,                             -- 기관 원문 주소
    current_version     integer     not null default 0,   -- 공개된 버전 (0이면 아직 공개 전)
    current_raw_post_id uuid,
    current_raw_version integer,
    reviewed            boolean     not null default false, -- 현재 버전이 검수자 승인본인지
    hidden              boolean     not null default false, -- 관리자가 숨김
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index notices_list_idx on notice.notices (field, apply_end) where current_version > 0 and not hidden;
create index notices_region_idx on notice.notices (region_code) where current_version > 0 and not hidden;
create index notices_posted_idx on notice.notices (posted_on desc, id desc) where current_version > 0 and not hidden;

-- 받은 원본 버전 하나 (extraction.completed 한 건). 같은 원본 버전을 다시 받으면(검수 승인 등) 덮어써요.
create table notice.notice_sources (
    raw_post_id    uuid        not null,
    raw_version    integer     not null,
    notice_id      uuid        not null references notice.notices (id),
    kind           text        not null check (kind in ('NOTICE', 'CORRECTION', 'FOLLOW_UP')),
    review_status  text        not null check (review_status in ('AUTO_PASSED', 'PARTIALLY_PASSED', 'IN_REVIEW', 'APPROVED')),
    version        integer,                               -- 공고 버전 번호 (공개된 원본만, 1부터)
    event_id       uuid        not null,
    payload        jsonb       not null,                  -- extraction.completed의 payload 전체
    received_at    timestamptz not null default now(),
    primary key (raw_post_id, raw_version)
);

create index notice_sources_notice_idx on notice.notice_sources (notice_id, version);
