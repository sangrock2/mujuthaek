-- 리뷰 2026-10-22: 합쳐진 공고 찾기(merged_into)에 색인
create index notices_merged_into on notice.notices (merged_into) where merged_into is not null;
