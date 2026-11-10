-- 알림 서버가 내보내는 이벤트 아웃박스 (api common.outbox와 같은 칸). payload에는 봉투 전체가 들어가요
-- 발송 결과와 같은 트랜잭션에서 한 줄 적고, OutboxRelay가 RabbitMQ(mujuthaek.events)로 보낸 뒤 published_at을 적어요
-- 지금 보내는 이벤트: push.subscription.expired (죽은 웹 푸시 구독 → api가 그 기기를 지움). 기기 주소가 실려서 보낸 줄은 하루 뒤 지워요
create table outbox (
    event_id       uuid        primary key,
    event_type     text        not null,
    schema_version int         not null,
    payload        jsonb       not null,
    created_at     timestamptz not null default now(),
    published_at   timestamptz,
    attempts       int         not null default 0   -- 보내 본 횟수 (실패 포함)
);
create index outbox_unpublished_idx on outbox (attempts, created_at) where published_at is null;
create index outbox_published_idx on outbox (published_at) where published_at is not null;
