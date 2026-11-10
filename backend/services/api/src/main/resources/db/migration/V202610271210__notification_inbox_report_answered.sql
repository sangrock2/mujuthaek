-- 알림함 종류에 제보 답변(REPORT_ANSWERED)을 더해요. 관리자 답변 원문은 알림함에 넣지 않아요 (처리 결과만).
alter table notification.notifications drop constraint notifications_type_check;
alter table notification.notifications add constraint notifications_type_check
    check (type in ('NEW_NOTICE', 'NEW_SUPPORT', 'DEADLINE_D3', 'DEADLINE_D1', 'CORRECTED', 'FOLLOW_UP', 'REPORT_ANSWERED'));
