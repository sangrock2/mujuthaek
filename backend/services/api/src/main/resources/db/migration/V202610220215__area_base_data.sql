-- area 기초 데이터: 생활권 시설(facilities), 상가(stores), 적재 기록(load_runs), 업종 묶음 규칙.
-- 설계: "무주택자들 생활권·상권(area) 설계" 1·2단계.
-- 좌표는 모두 WGS84 경위도 geography(Point, 4326)로 저장해요. 반경 계산 결과가 미터로 나와요.
-- PostGIS는 DB를 만들 때 관리자 계정으로 미리 설치해요(infra/db/init/01-databases.sh). area 스키마는 Flyway가 만들어요.

-- PostgreSQL 17에는 uuidv7()이 없어서(18부터 있음), 대량 적재(INSERT … SELECT)용으로 SQL 함수를 둬요.
-- 앞 48비트가 밀리초 시각, 버전 7, 변형 10.
create or replace function area.uuid_v7() returns uuid
language sql volatile parallel safe as
$$
  select encode(
    set_bit(
      set_bit(
        overlay(uuid_send(gen_random_uuid())
                placing substring(int8send((extract(epoch from clock_timestamp()) * 1000)::bigint) from 3)
                from 1 for 6),
        52, 1),
      53, 1),
    'hex')::uuid
$$;

-- 원천 파일 하나를 적재한 기록. 같은 파일(지문 같음)을 다시 받으면 건너뛰어요.
create table area.load_runs (
    id             uuid        primary key default area.uuid_v7(),
    source         text        not null,                 -- SUBWAY_STATION, BUS_STOP, SCHOOL, PARK, HOSPITAL, STORES
    load_scope     text        not null default 'ALL',   -- 상가정보는 시도 (강원, 경기 …), 나머지는 ALL
    file_key       text        not null,                 -- S3 키 (area/{source}/{기준일}/{영문 파일 이름})
    file_sha256    text        not null,
    data_date      date        not null,                 -- 원천 기준일
    status         text        not null check (status in ('RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED')),
    rows_in        integer     not null default 0,       -- 파일에서 읽은 데이터 줄
    rows_skipped   integer     not null default 0,       -- 규칙상 안 쓰는 줄 (폐교, 다른 종별 등)
    rows_rejected  integer     not null default 0,       -- 잘못된 줄 (좌표 없음, 범위 밖, 키 중복 등)
    rows_fixed     integer     not null default 0,       -- 고쳐서 넣은 줄 (위도·경도 뒤바뀜)
    rows_inserted  integer     not null default 0,
    rows_updated   integer     not null default 0,
    rows_unchanged integer     not null default 0,
    rows_deleted   integer     not null default 0,       -- 이번 파일에 없어 지운 줄 (폐업·폐교 등)
    reject_reasons jsonb       not null default '{}'::jsonb,
    error          text,
    started_at     timestamptz not null default now(),
    finished_at    timestamptz
);

create index load_runs_source_started_idx on area.load_runs (source, started_at desc);
create unique index load_runs_succeeded_file_uq on area.load_runs (source, load_scope, file_sha256) where status = 'SUCCEEDED';

-- 생활권 시설. kind별로 원천이 하나라 (source, source_key)가 곧 원천 안의 고유 키예요.
create table area.facilities (
    id          uuid        primary key default area.uuid_v7(),
    kind        text        not null check (kind in ('SUBWAY_STATION', 'BUS_STOP', 'SCHOOL', 'PARK', 'HOSPITAL')),
    sub_kind    text,                                    -- 노선명, ELEMENTARY/MIDDLE/HIGH, 공원구분, SECONDARY/CLINIC
    name        text        not null,
    address     text,
    geom        geography(Point, 4326) not null,
    extra       jsonb       not null default '{}'::jsonb, -- 원천별 추가 값 (공원 면적 area_m2, 병원 종별 등)
    source      text        not null,
    source_key  text        not null,
    data_date   date        not null,
    updated_at  timestamptz not null default now(),
    constraint facilities_source_key_uq unique (source, source_key)
);

create index facilities_geom_gix on area.facilities using gist (geom);
create index facilities_kind_idx on area.facilities (kind, sub_kind);

-- 상가(상권)정보 점포. 생활권 편의(편의점·슈퍼마켓)와 상권 점수에 써요.
create table area.stores (
    id              uuid        primary key default area.uuid_v7(),
    source_key      text        not null unique,         -- 상가업소번호
    load_scope      text        not null,                -- 시도 파일 묶음 (예: 강원). 지울 때 이 범위 안에서만 지워요
    name            text        not null,
    large_code      text,
    large_name      text,
    middle_code     text,
    middle_name     text,
    small_code      text,
    small_name      text,
    industry_group  text        not null,                -- area.industry_group_rules로 정한 묶음
    address         text,
    geom            geography(Point, 4326) not null,
    data_date       date        not null,
    updated_at      timestamptz not null default now()
);

create index stores_geom_gix on area.stores using gist (geom);
create index stores_group_idx on area.stores (industry_group);
create index stores_small_code_idx on area.stores (small_code);
create index stores_scope_idx on area.stores (load_scope);

-- 업종 묶음 규칙. 소분류 코드가 code_prefix로 시작하는 규칙 중 priority가 가장 작은 것을 써요.
-- 맞는 규칙이 없으면 대분류 코드(G2, I2 …)가 묶음이에요. 코드표가 바뀌면 이 표만 고쳐요.
create table area.industry_group_rules (
    priority        integer primary key,
    code_prefix     text    not null,
    industry_group  text    not null,
    note            text
);

insert into area.industry_group_rules (priority, code_prefix, industry_group, note) values
    (10, 'G20405', 'CONVENIENCE_STORE', '편의점'),
    (20, 'G20404', 'MART',              '슈퍼마켓 (코드표에 대형마트가 따로 없음)'),
    (30, 'I21201', 'CAFE',              '카페 (스터디카페 R10202는 대분류 R1로 떨어짐)'),
    (40, 'I211',   'BAR',               '주점업'),
    (50, 'I201',   'FOOD',              '한식'),
    (51, 'I202',   'FOOD',              '중식'),
    (52, 'I203',   'FOOD',              '일식'),
    (53, 'I204',   'FOOD',              '서양식'),
    (54, 'I205',   'FOOD',              '동남아시아'),
    (55, 'I206',   'FOOD',              '기타 외국식'),
    (56, 'I207',   'FOOD',              '구내식당·뷔페'),
    (57, 'I210',   'FOOD',              '기타 간이 음식');
