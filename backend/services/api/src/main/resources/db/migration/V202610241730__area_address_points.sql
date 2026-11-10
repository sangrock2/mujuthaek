-- 도로명주소 → 좌표 사전 (3단계 주소 → 좌표). 원천: 주소기반산업지원서비스 "도로명주소 출입구 정보" 전체분.
-- 주소 하나에 한 줄(대표 출입구). 전국 약 642만 줄이라 공간을 아끼려고 원천 고유 키(도로명주소관리번호 26자리)를
-- 기본 키로 써요(UUID v7 규칙의 예외: 원천 키가 있고 다른 테이블이 이 줄을 참조하지 않는 사전 테이블).
create table area.address_points (
    address_id    text        primary key,              -- 도로명주소관리번호 (시군구5 + 읍면동3 + 도로명번호7 + 지하1 + 본번5 + 부번5)
    load_scope    text        not null,                 -- 시도 코드 두 자리 (11, 12, 26 …). 지우기는 이 범위 안에서만
    bjd_code      text        not null,                 -- 법정동코드 10자리
    sigungu_code  text        not null,                 -- 법정동코드 앞 5자리
    emd           text,                                 -- 법정읍면동 이름 (지번 주소 찾기·확인용). 시도·시군구 이름은 법정동코드로 알 수 있어 두지 않아요
    road_code     text        not null,                 -- 도로명코드 12자리
    road_name     text        not null,
    underground   smallint    not null,                 -- 0 지상, 1 지하
    bldg_main     integer     not null,
    bldg_sub      integer     not null,
    zip_code      text,
    geom          geography(Point, 4326) not null,      -- 원천은 UTM-K(EPSG:5179), 적재 때 바꿔 넣어요
    data_date     date        not null,                 -- 이 줄이 마지막으로 바뀐 적재의 기준일 (원천 기준일은 area.load_runs.data_date)
    updated_at    timestamptz not null default now()
);

-- 공고 주소를 이름·번호로 찾을 때 (시군구 + 도로명 + 번호)
create index address_points_name_idx on area.address_points (sigungu_code, road_name, underground, bldg_main, bldg_sub);
-- 도로명코드 인덱스는 두지 않아요. 공고 주소에는 도로명코드가 없어 이름·번호로만 찾아요(100만 줄에 67MB 아낌).
create index address_points_scope_idx on area.address_points (load_scope);

comment on column area.address_points.data_date is '이 줄이 마지막으로 바뀐 적재의 원천 기준일 (원천 파일 기준일은 area.load_runs.data_date)';
