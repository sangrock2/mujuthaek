-- 공고 채팅: 메시지·좋아요·신고. 채팅방은 공고 하나(notice.notices.id)라 방 테이블은 따로 없어요.
-- 다른 모듈 스키마(notice·account)에는 FK를 걸지 않아요. 공고·회원 확인은 서비스 조회로 해요.
-- 회원이 탈퇴하면 그 회원의 메시지·좋아요·신고 줄을 지워요 (요구사항 3-16, 다른 모듈과 같은 방식).

create table chat.messages (
    id               uuid         primary key,                        -- UUID v7 (만든 순서). 목록 커서·SSE 이벤트 ID
    notice_id        uuid         not null,                           -- 채팅방 = 공고 ID (합쳐진 공고면 남은 공고 ID)
    user_id          uuid         not null,                           -- 작성자 (탈퇴하면 메시지 줄을 지워요)
    author_nickname  varchar(50),                                     -- 보낼 때의 닉네임 (닉네임이 없으면 null)
    parent_id        uuid,                                            -- 답장 대상 (한 단계만). 원문이 탈퇴로 지워져도 답장은 남아서 FK를 걸지 않아요
    content          varchar(500) not null,                           -- 작성자가 지워도 신고 검토용으로 남겨요 (응답에서는 숨김)
    like_count       integer      not null default 0,
    report_count     integer      not null default 0,                 -- 검토 전 신고 수 (관리자가 되돌리면 0)
    status           varchar(20)  not null
                     check (status in ('VISIBLE', 'DELETED', 'HIDDEN_REPORTED', 'HIDDEN_ADMIN')),
    created_at       timestamptz  not null,
    deleted_at       timestamptz
);
create index messages_room_idx on chat.messages (notice_id, id desc);
create index messages_user_recent_idx on chat.messages (user_id, created_at);  -- 1분 5개 제한

-- 좋아요: 1인 1회는 PK가 보장해요
create table chat.message_likes (
    message_id  uuid        not null references chat.messages (id) on delete cascade,
    user_id     uuid        not null,
    created_at  timestamptz not null,
    primary key (message_id, user_id)
);
create index message_likes_user_idx on chat.message_likes (user_id);

-- 신고: 같은 사람이 같은 메시지를 두 번 신고하지 못해요
create table chat.message_reports (
    id             uuid         primary key,                          -- UUID v7
    message_id     uuid         not null references chat.messages (id) on delete cascade,
    reporter_id    uuid         not null,                             -- 신고한 회원 (탈퇴하면 신고 줄을 지워요)
    reason         varchar(20)  not null check (reason in ('AD', 'ABUSE', 'PRIVACY', 'FALSE_INFO', 'ETC')),
    detail         varchar(200),                                      -- 기타 사유
    review_status  varchar(20)  not null check (review_status in ('PENDING', 'KEPT_HIDDEN', 'RESTORED')),
    created_at     timestamptz  not null,
    unique (message_id, reporter_id)
);
create index message_reports_review_idx on chat.message_reports (review_status, id desc);
create index message_reports_reporter_idx on chat.message_reports (reporter_id);
