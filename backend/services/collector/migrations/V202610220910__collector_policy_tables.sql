-- 정책·혜택 API 전용 테이블. 게시판 수집(raw_posts …)과 나눠요.
-- 4개 API(보조금24, 복지로 중앙·지자체, 온통청년)의 칸을 통일한 값과 응답 원본을 함께 남겨요.
-- 원본(list_raw, api_raw)은 통일할 때 버리거나 잘못 옮긴 칸이 있어도 다시 처리할 수 있게 그대로 둬요.

-- 정책 한 건. 목록에서 본 순간 한 번 저장하고, 상태만 바꿔요. 거름에 걸리지 않은 정책(SKIPPED)도 남겨요.
create table raw_policies (
    id                 uuid primary key,
    source_code        text not null references sources (code),
    policy_id          text not null,                  -- 출처 안에서 유일 (보조금24 서비스ID, 복지로 servId, 온통청년 plcyNo)
    title              text not null,
    summary            text,                           -- 한두 줄 요약 (서비스목적요약, servDgst, plcyExplnCn)
    agency             text,
    region_scope       text not null default 'UNKNOWN', -- NATIONWIDE, SIDO, SIGUNGU, UNKNOWN (힌트. 최종 지역은 AI 추출 단계가 정해요)
    region_names       text[] not null default '{}',
    region_codes       text[] not null default '{}',   -- 시군구 코드 5자리 (온통청년만 줘요)
    field              text not null default 'BENEFIT', -- BENEFIT, STARTUP_SUPPORT
    categories         text[] not null default '{}',   -- 출처가 붙인 분야
    detail_url         text,
    apply_url          text,
    source_modified_at text,                           -- 출처 수정일 (형식이 출처마다 달라서 그대로)
    marker             text not null default '',       -- 바뀌었는지 보는 값: 수정일, 없으면 목록 항목 해시
    list_raw           jsonb not null,                 -- 목록 응답 한 건 그대로
    status             text not null,                  -- SKIPPED, PENDING, DONE, FAILED
    attempts           int  not null default 0,
    last_error         text,
    latest_version     int  not null default 0,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    unique (source_code, policy_id)
);
create index raw_policies_queue_idx on raw_policies (source_code, status) where status in ('PENDING', 'FAILED');

-- 내용이 바뀔 때마다 한 줄. 글로 오는 칸은 원문 그대로 두고, 날짜·금액으로 바꾸는 건 AI 추출 단계가 해요.
create table raw_policy_versions (
    id              uuid primary key,
    raw_policy_id   uuid not null references raw_policies (id),
    version         int  not null,
    content_hash    text not null,                 -- API 항목 + 첨부 해시. 같으면 새 버전을 만들지 않음
    target          text,                          -- 지원 대상
    criteria        text,                          -- 선정 기준
    benefit         text,                          -- 지원 내용
    how_to_apply    text,                          -- 신청 방법
    apply_period    text,                          -- 신청 기간·기한
    documents       text,                          -- 제출 서류
    age_min         int,                           -- API가 나이를 숫자로 줄 때만
    age_max         int,
    api_raw         jsonb not null,                -- 목록 + 상세 + 지원조건 응답 원본
    document_status text not null,                 -- OK, NONE, NO_SOURCE, BLOCKED, FAILED (첨부 글자)
    origin_status   text not null,                 -- OK, NONE, NO_SOURCE, BLOCKED, FAILED, NOT_OPENED (원문 화면 본문)
    origin_checked  jsonb not null default '[]',   -- 연 원문 주소
    origin_text_url text,                          -- 본문을 쓴 원문 주소
    body_text       text not null,                 -- 버전 비교에 쓴 API 항목 글자
    full_text       text not null,                 -- AI 추출에 넘긴 전체 글자
    crawl_run_id    uuid references crawl_runs (id),
    collected_at    timestamptz not null default now(),
    unique (raw_policy_id, version)
);

create table raw_policy_files (
    id           uuid primary key,
    version_id   uuid not null references raw_policy_versions (id),
    idx          int  not null,
    name         text not null,
    role         text not null,                   -- POLICY_DOC(글자 뽑음), FORM(서식), ATTACHMENT(그 밖)
    found_on     text not null,                   -- API, ORIGIN_PAGE
    download_url text not null,                   -- 기관 다운로드 주소 (계속 보관)
    file_hash    text not null,
    size_bytes   bigint not null,
    s3_key       text,                            -- 보관 기한이 지나 삭제되면 null
    stored_until date not null,                   -- 수집일 + 12개월
    text_status  text,                            -- 글자 뽑기 결과 (성공 방식 또는 실패 이유)
    deleted_at   timestamptz
);

create table raw_policy_texts (
    id      uuid primary key,
    file_id uuid not null references raw_policy_files (id),
    text    text not null                         -- 파일이 지워져도 추출한 글자는 계속 보관
);
