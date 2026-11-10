-- 관리자 기준값 화면 (2026-10-25): 기준값을 고친 기록과 규제지역 표. 기존 criteria_sets는 그대로 쓰고 바꾸기 전 값만 여기에 남겨요.
create table eligibility.criteria_set_history (
    id          bigserial   primary key,
    kind        text        not null,
    year        integer     not null,
    valid_from  date        not null,
    data        jsonb       not null,
    source      text,
    updated_by  text,
    updated_at  timestamptz not null,
    replaced_at timestamptz not null default now(),   -- 이 값이 새 값으로 바뀐 때
    replaced_by text                                  -- 바꾼 관리자 (api 로그인 계정 ID)
);
create index criteria_set_history_kind_idx on eligibility.criteria_set_history (kind, year, replaced_at desc);

comment on table eligibility.criteria_set_history is '관리자가 기준값(criteria_sets)을 바꾸기 전 값. 바꿀 때마다 한 줄';

-- 규제지역 (투기과열지구·조정대상지역·투기지역). 관리자가 국토교통부 지정·해제 공고를 보고 넣어요.
-- 판정에서 쓰는 연결은 판정 담당이 정해요(이 표는 관리 화면용으로 먼저 둠).
create table eligibility.regulated_areas (
    id          uuid        primary key,
    region_code text        not null check (region_code ~ '^[0-9]{5}$'),  -- 시군구 5자리, 시도 전체면 xx000
    kind        text        not null check (kind in ('SPECULATION_OVERHEATED', 'ADJUSTMENT_TARGET', 'SPECULATION')),
    scope_note  text,                                 -- 일부 지역만이면 그 설명 (예: 일부 동 제외)
    valid_from  date        not null,                 -- 지정일
    valid_until date,                                 -- 해제일 (지정 중이면 null)
    source      text,                                 -- 근거 공고
    updated_by  text,
    updated_at  timestamptz not null default now(),
    check (valid_until is null or valid_until >= valid_from)
);
create index regulated_areas_region_idx on eligibility.regulated_areas (region_code, valid_from);
