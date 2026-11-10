-- api가 내보내는 이벤트 아웃박스 (libs/python-platform outbox와 같은 칸). payload에는 봉투 전체가 들어가요
-- 저장과 같은 트랜잭션에서 한 줄 적고, OutboxRelay가 RabbitMQ(mujuthaek.events)로 보낸 뒤 published_at을 적어요
-- 이메일 주소·인증 코드가 실릴 수 있어서, 보낸 줄은 하루 뒤 지워요 (OutboxCleanup)
create table common.outbox (
    event_id       uuid        primary key,
    event_type     text        not null,
    schema_version int         not null,
    payload        jsonb       not null,
    created_at     timestamptz not null default now(),
    published_at   timestamptz,
    attempts       int         not null default 0   -- 보내 본 횟수 (실패 포함)
);
create index outbox_unpublished_idx on common.outbox (attempts, created_at) where published_at is null;  -- 덜 시도한 것부터 꺼내요 (막힌 이벤트가 새 이벤트를 막지 않게)
create index outbox_published_idx on common.outbox (published_at) where published_at is not null;  -- 보낸 줄 지우기
