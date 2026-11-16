-- 최상위 관리자가 내린 이용 정지는 최상위 관리자만 바꾸거나 풀어요 (2026-11-16 보안 감사 L-10).
--  · 예전에는 「이용 정지」 권한만 있는 일반 관리자가 최상위 관리자가 내린 정지를 풀거나 기간을 줄일 수 있었어요
--  · 정지를 내릴 때 내린 사람이 최상위였는지 남겨요. 이미 있는 정지는 내린 사람의 지금 단계로 채워요
alter table account.suspensions add column suspended_by_super boolean not null default false;

update account.suspensions s
   set suspended_by_super = true
  from account.users u
 where u.id = s.suspended_by
   and u.role = 'SUPER_ADMIN';
