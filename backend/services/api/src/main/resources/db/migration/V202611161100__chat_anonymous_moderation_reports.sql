-- 회원의 ID·자유 문구는 지우되, 가린 글의 검토 작업은 회원 탈퇴와 별도로 보존해요.
alter table chat.message_reports alter column reporter_id drop not null;

-- 이전 동작으로 신고만 지워져 검토 큐에서 빠진 숨김 글도 다시 확인할 수 있게 해요.
insert into chat.message_reports
    (id, message_id, reporter_id, reason, detail, review_status, created_at)
select gen_random_uuid(), m.id, null, 'ETC', null, 'PENDING', now()
from chat.messages m
where m.status = 'HIDDEN_REPORTED'
  and not exists (select 1 from chat.message_reports r
                  where r.message_id = m.id and r.review_status = 'PENDING');
