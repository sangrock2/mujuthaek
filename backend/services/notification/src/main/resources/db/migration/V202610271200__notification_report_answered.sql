-- 알림 종류에 제보 답변(REPORT_ANSWERED)을 더해요. 묶지 않고 바로 보내요 (api가 제보한 회원 한 명에게 요청).
alter table deliveries drop constraint deliveries_type_check;
alter table deliveries add constraint deliveries_type_check
    check (type in ('NEW_NOTICE', 'NEW_SUPPORT', 'DEADLINE_D3', 'DEADLINE_D1', 'CORRECTED', 'FOLLOW_UP', 'REPORT_ANSWERED'));
