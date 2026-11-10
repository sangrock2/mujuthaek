-- 알림을 실제로 봤는지·눌렀는지 (관리자 알림 화면의 지표). 회원 본인의 알림함 줄에만 남고, 탈퇴·90일 정리 때 함께 지워져요
alter table notification.notifications
    add column shown_at   timestamptz,   -- 웹 푸시가 기기에 떴어요 (서비스 워커가 알려 줌). 처음 한 번만
    add column clicked_at timestamptz;   -- 푸시나 알림 목록에서 눌러 그 화면으로 갔어요. 처음 한 번만

create index notifications_type_created_idx on notification.notifications (created_at, type);
