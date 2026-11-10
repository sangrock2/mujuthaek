-- collector 데이터베이스. 모든 출처의 원본을 고치지 않고 버전으로 쌓아요.

create table sources (
    code       text primary key,          -- 수집기 code (sh, gh, bmc, ih, dcco, dudc, umca, gbdc, gndc)
    name       text not null,
    enabled    boolean not null default true,
    created_at timestamptz not null default now()
);

insert into sources (code, name) values
    ('sh', 'SH 서울주택도시공사'), ('gh', 'GH 경기주택도시공사'), ('bmc', '부산도시공사'),
    ('ih', 'iH 인천도시공사'), ('dcco', '대전도시공사'), ('dudc', '대구도시공사'),
    ('umca', '울산도시공사'), ('gbdc', '경상북도개발공사'), ('gndc', '경상남도개발공사');

-- 게시판별 상태: 목록 1페이지 해시(같으면 그 회차 바로 끝), 목록 0건 연속 횟수(구조 변경 감지)
create table source_boards (
    source_code    text not null references sources (code),
    board_key      text not null,
    last_list_hash text not null default '',
    empty_runs     int  not null default 0,
    last_run_at    timestamptz,
    primary key (source_code, board_key)
);

create table crawl_runs (
    id          uuid primary key,
    source_code text not null references sources (code),
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    status      text not null default 'RUNNING',  -- RUNNING, SUCCESS, BLOCKED, FAILED
    new_count   int  not null default 0,
    error       text                              -- 오류 또는 경고 모음
);

-- 목록에서 본 모든 글. 열지 않은 글(SKIPPED)도 남겨서 다음 회차에 다시 판단하지 않아요.
create table raw_posts (
    id             uuid primary key,
    source_code    text not null references sources (code),
    board_key      text not null,
    post_key       text not null,                 -- 출처 안에서 유일 (게시판이 여러 개면 접두어)
    kind           text not null,                 -- NOTICE, CORRECTION, FOLLOW_UP, EXCLUDED
    title          text not null,
    posted_on      date,
    detail_url     text,
    list_item      jsonb not null,                -- 목록에서 읽은 값 그대로 (PENDING 글을 다음 회차에 다시 열 때 사용)
    status         text not null,                 -- SKIPPED, PENDING, DONE, FAILED
    attempts       int  not null default 0,       -- FAILED 재시도 횟수 (3번까지)
    last_error     text,
    list_status    text,                          -- 목록의 상태 (접수중, 모집종료 …)
    deadline_on    date,
    parent_post_id uuid references raw_posts (id), -- 정정공고·후속 안내가 가리키는 원래 모집공고
    latest_version int  not null default 0,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    unique (source_code, post_key)
);
create index raw_posts_queue_idx on raw_posts (source_code, board_key, status) where status in ('PENDING', 'FAILED');

create table raw_post_versions (
    id           uuid primary key,
    raw_post_id  uuid not null references raw_posts (id),
    version      int  not null,
    content_hash text not null,                   -- 본문 + 첨부 해시. 같으면 새 버전을 만들지 않음
    body_text    text not null,
    meta         jsonb not null default '{}',     -- 상세·목록의 항목 (유형, 지역, 공고상태 …)
    full_text    text not null,                   -- AI 추출에 넘긴 전체 글자 (제목·게시 정보·본문·공고문)
    crawl_run_id uuid references crawl_runs (id),
    collected_at timestamptz not null default now(),
    unique (raw_post_id, version)
);

create table raw_files (
    id           uuid primary key,
    version_id   uuid not null references raw_post_versions (id),
    idx          int  not null,
    name         text not null,
    role         text not null,                   -- NOTICE_DOC, UNIT_LIST
    download_url text not null,                   -- 기관 다운로드 주소 (계속 보관)
    file_hash    text not null,
    size_bytes   bigint not null,
    s3_key       text,                            -- 보관 기한이 지나 삭제되면 null
    stored_until date not null,                   -- 마감(없으면 게시) + 6개월, 예비입주자 모집은 1년
    text_status  text,
    deleted_at   timestamptz
);

create table raw_texts (
    id      uuid primary key,
    file_id uuid not null references raw_files (id),
    text    text not null                         -- 파일이 지워져도 추출한 글자는 계속 보관
);

create table raw_units (
    id           uuid primary key,
    version_id   uuid not null references raw_post_versions (id),
    source_file  text,                            -- 어느 파일(또는 '상세 화면')에서 읽었는지
    page         int,
    complex      text,
    district     text,
    address      text,
    unit         text,
    floor        text,
    house_type   text,
    target_group text,
    rooms        text,
    area_m2      numeric,
    deposit_won  bigint,
    rent_won     bigint,
    supply_count int,
    elevator     text,
    parking      text,
    raw          jsonb not null default '{}',     -- 원래 머리글: 값 (해석이 틀렸을 때 확인용)
    checks       jsonb not null default '[]'      -- 말이 안 돼서 비운 값
);

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
