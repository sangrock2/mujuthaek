-- 공고 검색의 시도 필터(NoticeQueries: left(r.sigungu_code, 2) in (:sido))가 notice_regions_code_idx (sigungu_code, notice_id)를
-- 못 써서 표 전체를 훑던 것. 같은 식으로 인덱스를 만들어 쿼리는 그대로 두고 인덱스로 찾아요 (2026-10-31 로컬 더미 공고 1만 부하 시험)
create index notice_regions_sido_idx on notice.notice_regions (left(sigungu_code, 2), notice_id);
