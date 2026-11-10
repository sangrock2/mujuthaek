-- 알림함 대상 종류에 창업지원 사업(STARTUP_SUPPORT)을 더해요 (새 소식·정정·마감 알림, target_id = rawPolicyId).
alter table notification.notifications drop constraint notifications_target_type_check;
alter table notification.notifications add constraint notifications_target_type_check
    check (target_type in ('NOTICE', 'BENEFIT', 'STARTUP_SUPPORT', 'SPACE_RECRUITMENT'));
