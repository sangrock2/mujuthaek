-- 알림함 (설계: contracts/schemas/notification-events.draft.md 5장 "요청 만들기 순서" 3). 알림 요청을 만들 때 받는 사람마다 한 줄이에요
-- 알림 설정(종류별 켬·끔)이나 기기·이메일이 없어도 남아요. 설정은 푸시·이메일로 보낼지만 정해요
-- user_id는 user 모듈 회원이지만 다른 모듈 테이블이라 FK를 걸지 않아요. 탈퇴는 UserWithdrawn으로 지우고, 90일 지난 줄은 매일 지워요
create table notification.notifications (
    id          uuid        primary key,                -- UUID v7 (만든 순서라 목록 정렬·커서에 써요)
    user_id     uuid        not null,
    type        text        not null check (type in ('NEW_NOTICE', 'NEW_SUPPORT', 'DEADLINE_D3', 'DEADLINE_D1', 'CORRECTED', 'FOLLOW_UP')),
    target_type text        not null check (target_type in ('NOTICE', 'BENEFIT', 'SPACE_RECRUITMENT')),
    target_id   uuid        not null,
    title       text        not null,
    body        text        not null,
    link_path   text        not null,                   -- PWA 화면 경로 (/notices/{id} …)
    dedup_key   text        not null,                   -- 알림 요청의 dedupKey. 같은 알림이 다시 만들어져도 한 줄
    read_at     timestamptz,                            -- 읽은 시각. null이면 안 읽음
    created_at  timestamptz not null,
    unique (user_id, dedup_key)
);
create index notifications_user_idx on notification.notifications (user_id, id desc);
create index notifications_unread_idx on notification.notifications (user_id) where read_at is null;
create index notifications_created_idx on notification.notifications (created_at);   -- 90일 지난 줄 지우기
