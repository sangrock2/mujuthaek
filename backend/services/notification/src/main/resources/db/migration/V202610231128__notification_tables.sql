-- 발송 (설계: contracts/schemas/notification-tables.draft.md)
-- 알림 서버는 api가 보낸 대로 보내기만 해요. 받을 사람·받을 주소·문구·회원 설정은 api가 정해서 notification.requested에 담아요
-- 회원 이메일·알림 설정·알림함은 api에 있어요. 여기는 보낼 일과 결과만 둬요
-- user_id는 api 회원 ID라 다른 DB여서 FK를 걸지 않아요

-- 채널별 발송 1건 (회원 1명 × 채널 1개 × 알림 1건). 워커가 scheduled_at이 지난 PENDING을 for update skip locked로 가져가요
-- 새 공고·새 정책 이메일(digest)은 하루 두 번(08:00·18:00, Asia/Seoul)으로 scheduled_at을 맞추고, 같은 회원·같은 주소·같은 시각 건을 1통으로 묶어요
-- 조용한 시간(quiet)이면 22:00~08:00 건을 다음 08:00으로 미뤄요. 재시도도 scheduled_at을 뒤로 미뤄요
-- address(이메일 주소)는 보내는 동안만 두고, 끝나면(SENT·FAILED) 지워요. 오류·로그에도 주소는 넣지 않아요
create table deliveries (
    id                  uuid        primary key,
    user_id             uuid        not null,
    channel             text        not null check (channel in ('EMAIL', 'PUSH')),
    address             text,                                -- 보낼 곳 (이메일 주소, 푸시 구독). 끝나면 null
    type                text        not null check (type in ('NEW_NOTICE', 'NEW_SUPPORT', 'DEADLINE_D3', 'DEADLINE_D1', 'CORRECTED', 'FOLLOW_UP')),
    dedup_key           text        not null,                -- {user_id}:{요청의 dedupKey}. 같은 요청이 다시 와도 두 번 보내지 않아요
    title               text        not null,                -- api가 만든 문구
    body                text        not null,
    link_path           text        not null,                -- PWA 상세 화면 경로 (/notices/{id} …)
    digest              boolean     not null default false,  -- 묶음 메일로 보낼 건
    quiet               boolean     not null default false,  -- 회원이 조용한 시간을 켰나 (요청 때 값)
    status              text        not null default 'PENDING' check (status in ('PENDING', 'SENT', 'FAILED')),
    scheduled_at        timestamptz not null,
    attempts            int         not null default 0,
    last_error          text,
    provider_message_id text,                                -- SES MessageId (반송 알림과 맞춰요). 묶음 메일은 같은 값
    sent_at             timestamptz,
    created_at          timestamptz not null default now(),
    unique (dedup_key, channel)
);
create index deliveries_pending_idx on deliveries (scheduled_at) where status = 'PENDING';
create index deliveries_user_idx on deliveries (user_id);           -- 탈퇴 회원 지우기
create index deliveries_created_idx on deliveries (created_at);     -- 90일 지난 기록 지우기
