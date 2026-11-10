-- 공개 버전을 고치지 않는 기록으로 남기고, 받은 결과는 이벤트마다 기록해요.
-- notice_sources(원본 버전마다 한 줄)는 같은 원본 버전을 다시 받으면 payload를 덮어써서, 같은 원본 버전이 검수 대기로 다시 오면
-- 공개 중인 상세 내용이 검수 전 내용으로 바뀌었어요. 공개 내용은 notice_versions에서만 읽어요.
drop table notice.notice_sources;

-- 공개 버전 (한 번 저장하면 내용을 고치지 않아요. 승인만 review_status로 올려요)
create table notice.notice_versions (
    notice_id            uuid        not null references notice.notices (id),
    version              int         not null,
    raw_post_id          uuid        not null,                -- 이 버전을 만든 원본 글
    raw_version          int         not null,
    source_event_id      uuid        not null,                -- 이 버전을 만든 extraction.completed
    review_status        text        not null check (review_status in ('AUTO_PASSED', 'PARTIALLY_PASSED', 'APPROVED')),
    payload              jsonb       not null,                -- extraction.completed의 payload 전체 (상세 화면)
    conditions           jsonb       not null,                -- 판정용 자격 조건 (이전 v1의 빠진 scope를 채운 값)
    held_items           jsonb       not null default '[]',   -- 부분 게시로 보류한 항목
    application_windows  jsonb       not null default '[]',   -- 순위·대상별 접수 기간
    content_hash         text        not null,                -- 내용이 같은 결과는 새 버전을 만들지 않아요
    changed_fields       jsonb       not null default '[]',   -- 이전 버전과 달라진 섹션
    created_at           timestamptz not null,
    primary key (notice_id, version)
);
create index notice_versions_raw_post_idx on notice.notice_versions (raw_post_id, raw_version desc);

-- 공고의 원본 글 (원래 공고 + 반영된 정정 공고). 원본 글 하나는 공고 하나에만 속해요.
create table notice.notice_posts (
    raw_post_id         uuid        primary key,
    notice_id           uuid        not null references notice.notices (id),
    kind                text        not null check (kind in ('NOTICE', 'CORRECTION')),
    supersedes_post_id  uuid,                                 -- 정정 공고가 가리키는 원래 글
    posted_on           date,                                 -- 게시일 (늦게 온 더 이른 정정이 최신 정정을 덮지 않게)
    created_at          timestamptz not null,
    updated_at          timestamptz not null
);
create index notice_posts_notice_idx on notice.notice_posts (notice_id);

-- 받은 추출 결과 기록 (공개·검수 대기·오래된 버전 판단, 원래 공고를 기다리는 정정 다시 반영)
create table notice.extraction_results (
    event_id            uuid        primary key,
    raw_post_id         uuid        not null,
    raw_version         int         not null,
    review_status       text        not null,
    outcome             text        not null,                 -- IngestionOutcome
    reason              text,
    notice_id           uuid,
    supersedes_post_id  uuid,
    payload             jsonb       not null,
    received_at         timestamptz not null
);
create index extraction_results_raw_idx on notice.extraction_results (raw_post_id, raw_version);
create index extraction_results_waiting_idx on notice.extraction_results (supersedes_post_id)
    where outcome = 'HELD' and reason = 'PARENT_NOT_PUBLISHED';

-- 후속 안내 (서류 제출·당첨자 발표 같은 후속 공지). 공고 버전은 바꾸지 않고 원래 공고에 따로 붙여요.
create table notice.notice_follow_ups (
    raw_post_id      uuid        primary key,
    notice_id        uuid        not null references notice.notices (id),
    raw_version      int         not null,
    source_event_id  uuid        not null,
    review_status    text        not null,                    -- 승인본을 같은 원본 버전의 자동 결과로 덮지 않게
    title            text        not null,
    detail_url       text,
    posted_on        date,
    schedules        jsonb       not null default '[]',
    content_hash     text        not null,
    created_at       timestamptz not null,
    updated_at       timestamptz not null
);
create index notice_follow_ups_notice_idx on notice.notice_follow_ups (notice_id, posted_on);
