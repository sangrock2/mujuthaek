-- 처음 수집 개수 제한 (2026-10-27 결정). 배포 뒤 처음 한 번은 묶음마다 최신 N개만 AI 추출로 보내고, 그 이전 글은 쓰지 않아요.
--   묶음: HOUSING_LH(LH 주거 공고) 10 · HOUSING_OTHER(LH 말고 다른 게시판 주거 공고) 10 · SPACE(사업공간 모집) 10 · POLICY(지원 정책: 혜택·창업 지원) 500
--   고르기 전(이 표에 그 묶음 줄이 없음): 새 글은 상세를 열지 않고 HELD로 둬요
--   고를 때(core/intake.py): HELD 중 최신 N개 → PENDING, 나머지 → IGNORED(다시 큐에 넣지 않음). 고른 글 중 가장 오래된 날짜가 기준일(cutoff_on)
--   고른 뒤: 새 글은 바로 PENDING, 기준일보다 오래된 글은 IGNORED
-- raw_posts·raw_policies의 status에 HELD·IGNORED가 더해져요.

create table intake_decisions (
    group_code   text        primary key,       -- HOUSING_LH, HOUSING_OTHER, SPACE, POLICY
    limit_count  integer     not null,
    kept         integer     not null,
    ignored      integer     not null,
    cutoff_on    date,                          -- 고른 글 중 가장 오래된 날짜. 비어 있으면 기준일 없음 (날짜를 모르는 글뿐이거나 이미 데이터가 있던 DB)
    decided_at   timestamptz not null default now()
);

comment on table intake_decisions is '처음 수집 개수 제한을 묶음마다 언제 어떻게 골랐는지. 줄이 없으면 아직 고르기 전이라 새 글을 HELD로 둬요';

-- 정책 목록의 등록일 (출처마다 칸이 달라요: sources/policy의 listed_keys). 처음 고를 때 최신 순서와 기준일에 써요
alter table raw_policies add column listed_on date;

-- 이미 수집해 발행한 데이터가 있는 DB(로컬·개발)는 고른 것으로 봐서 지금처럼 동작해요
insert into intake_decisions (group_code, limit_count, kept, ignored)
select g, 0, 0, 0
from (values ('HOUSING_LH'), ('HOUSING_OTHER'), ('SPACE'), ('POLICY')) as v(g)
where case g
    when 'HOUSING_LH' then exists (select 1 from raw_posts where source_code = 'lh' and status = 'DONE')
    when 'HOUSING_OTHER' then exists (select 1 from raw_posts where source_code <> 'lh' and status = 'DONE')
    when 'SPACE' then exists (select 1 from raw_policies where field = 'SPACE_RECRUITMENT' and status = 'DONE')
    else exists (select 1 from raw_policies where field <> 'SPACE_RECRUITMENT' and status = 'DONE')
end;
