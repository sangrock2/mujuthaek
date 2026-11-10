-- 관리자가 「나중 것 숨김」으로 숨긴 중복 정책 사업(notice.policy_duplicate_candidates status HIDDEN)에 둔 관심을 남은 사업으로 옮겨요
-- (2026-11-10 재검토: 숨긴 사업의 관심은 목록에 빈 줄로 남고 남은 사업의 마감·정정 알림을 받지 못했음). 앞으로는 숨길 때 PolicyHidden 이벤트로 옮겨요.
-- 같은 회원이 둘 다 관심에 뒀으면 숨긴 쪽 줄만 지워요(기본 키가 겹치지 않게)
delete from account.favorites f
 using notice.policy_duplicate_candidates c
 where c.status = 'HIDDEN'
   and f.target_type in ('STARTUP_SUPPORT', 'SPACE_RECRUITMENT')
   and f.target_id = c.raw_policy_id
   and exists (select 1 from account.favorites g
                where g.user_id = f.user_id and g.target_type = f.target_type and g.target_id = c.candidate_of);

update account.favorites f
   set target_id = c.candidate_of
  from notice.policy_duplicate_candidates c
 where c.status = 'HIDDEN'
   and f.target_type in ('STARTUP_SUPPORT', 'SPACE_RECRUITMENT')
   and f.target_id = c.raw_policy_id;
