-- 마이그레이션 파일 이름: V<연월일시분>__notification_<설명>.sql. 기존 파일은 고치지 말고 새로 만들어요
-- 처리한 이벤트. 같은 eventId가 다시 오면(재전송·중복 발행) 건너뛰어서 알림을 두 번 보내지 않아요
create table processed_events (
    event_id     uuid primary key,
    event_type   text        not null,
    processed_at timestamptz not null default now()
);
