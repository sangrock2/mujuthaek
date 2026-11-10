-- 판정 기준값 (연도별). 기준 중위소득처럼 해마다 바뀌는 값은 코드에 두지 않고 여기에 둬요.
-- 값은 그해 고시·공고를 보고 관리자가 넣어요 (관리자 기준값 화면, PUT /admin/criteria/{kind}).
--   MEDIAN_INCOME       기준 중위소득 월액 (가구원 수별): {"monthlyWon": {"1": …, "2": …}}
--   URBAN_WORKER_INCOME 도시근로자 가구당 월평균소득: {"monthlyWon": {"1": …}}
--   RANK_CRITERIA       순위 요건: {"ranks": [{"rank": 1, "rule": "ANY", "items": [{"key": …, "label": …, …}]}]}
create table eligibility.criteria_sets (
    kind        text        not null check (kind in ('MEDIAN_INCOME', 'URBAN_WORKER_INCOME', 'RANK_CRITERIA')),
    year        integer     not null check (year between 2000 and 2200),
    valid_from  date        not null,                 -- 이 값을 쓰기 시작하는 날
    data        jsonb       not null,
    source      text,                                 -- 근거 (고시 번호·공고 이름)
    updated_by  text,                                 -- 고친 사람 (관리자 화면이 생기면)
    updated_at  timestamptz not null default now(),
    primary key (kind, year)
);
