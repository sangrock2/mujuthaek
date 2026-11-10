-- 시·도(2자리)와 시·군·구(5자리) 코드표. 원본은 행정안전부 법정동코드 전체자료예요.
-- 화면의 사는 곳·지역 필터·관심 지역과 공고·혜택의 regionCode가 이 코드를 써요.
create table common.regions (
    code         text        primary key check (code ~ '^[0-9]{2}([0-9]{3})?$'),
    level        text        not null check (level in ('SIDO', 'SIGUNGU')),
    parent_code  text        references common.regions (code),   -- 시군구의 시도 (시도는 null)
    name         text        not null,                            -- 시도: 서울특별시 / 시군구: 마포구, 수원시 장안구
    full_name    text        not null,                            -- 서울특별시 마포구
    short_name   text,                                            -- 시도만: 서울, 경기, 전남 …
    valid        boolean     not null default true,               -- 폐지된 코드면 false
    valid_to     date,                                            -- 폐지일 (아는 경우)
    replaced_by  text        references common.regions (code),   -- 바뀐 코드 (예: 강원 42 → 51)
    base_date    date        not null,                            -- 원본 기준일
    updated_at   timestamptz not null default now(),
    check ((level = 'SIDO') = (parent_code is null))
);

create index regions_parent_idx on common.regions (parent_code) where valid;
