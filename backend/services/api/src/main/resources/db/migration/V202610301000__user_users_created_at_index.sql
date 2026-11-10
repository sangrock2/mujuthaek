-- 관리자 회원 목록(최근 가입 순, 한 쪽 30명)이 쪽마다 회원 전체를 읽고 정렬하지 않게 (2026-10-30 부하 시험: 10만 명에서 28.6ms → 0.84ms)
create index users_created_at_idx on account.users (created_at desc, id);
