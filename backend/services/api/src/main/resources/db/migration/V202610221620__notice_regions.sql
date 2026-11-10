-- 여러 지역 공고: notices.region_code(대표 지역 하나)는 여러 시도에 걸치면 비어서(예: 대구·경북) 지역으로 찾을 수 없었어요.
-- 공고가 걸친 지역 5자리를 모두 색인하고, 원문이 「전국」 대상이면 어느 지역 검색에도 나오게 해요.
create table notice.notice_regions (
    notice_id     uuid    not null references notice.notices (id) on delete cascade,
    sigungu_code  text    not null check (sigungu_code ~ '^[0-9]{5}$'), -- 시군구 5자리 (시도까지만 알면 xx000)
    whole         boolean not null default false,                       -- 대상 지역 전체(위치 종류 AREA): 그 아래 시군구 검색에도 나와요
    primary key (notice_id, sigungu_code)
);
create index notice_regions_code_idx on notice.notice_regions (sigungu_code, notice_id);

alter table notice.notices add column nationwide boolean not null default false; -- 원문 위치가 「전국」인 공고

-- 이미 공개된 공고는 대표 지역으로 색인해요 (다음 버전부터 모든 지역으로 바뀌어요)
insert into notice.notice_regions (notice_id, sigungu_code)
select id, region_code from notice.notices where region_code is not null and current_version > 0;
