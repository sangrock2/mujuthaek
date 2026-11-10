-- 웹 푸시 구독 기기 (설계: contracts/schemas/web-push.draft.md 1장). 기기(브라우저)마다 한 줄이고, 줄이 있으면 그 기기 푸시가 켜진 거예요
-- endpoint·p256dh·auth는 알면 그 기기에 알림을 보낼 수 있는 값이라 로그·오류 응답에 넣지 않아요
-- user_id는 user 모듈(account.users) 회원이지만 다른 모듈 테이블이라 FK를 걸지 않아요. 탈퇴는 UserWithdrawn으로 지워요
create table notification.push_subscriptions (
    id          uuid        primary key,                -- UUID v7
    user_id     uuid        not null,
    endpoint    text        not null unique,            -- 브라우저가 만든 이 기기 주소 (푸시 서비스 https 주소)
    p256dh      text        not null,                   -- 내용 암호화 공개키 (base64url)
    auth        text        not null,                   -- 내용 암호화 비밀값 (base64url)
    user_agent  text,                                   -- 기기 목록에 보여 줄 이름 (예: Chrome / Android)
    created_at  timestamptz not null,
    updated_at  timestamptz not null,                   -- 마지막 등록. PWA가 앱을 열 때마다 다시 등록해요 (최근에 쓴 기기)
    constraint push_subscriptions_endpoint_https check (endpoint like 'https://%')
);
create index push_subscriptions_user_idx on notification.push_subscriptions (user_id, updated_at desc);
