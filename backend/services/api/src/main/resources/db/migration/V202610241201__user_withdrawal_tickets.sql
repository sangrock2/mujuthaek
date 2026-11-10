-- 탈퇴 재인증 티켓 (user 모듈). 탈퇴는 '소셜 다시 로그인 → 연결 끊기 → 회원 삭제'라서, 다시 로그인하러 가는 동안
-- 누가 탈퇴하려는지 기억해요. 원문은 재인증 주소에만 있고 여기엔 SHA-256 해시만 둬요. 일회용, 10분.
create table account.withdrawal_tickets (
    id          uuid primary key,
    user_id     uuid        not null references account.users (id) on delete cascade,
    provider    varchar(20) not null check (provider in ('KAKAO', 'NAVER', 'GOOGLE')),
    ticket_hash varchar(64) not null unique,
    expires_at  timestamptz not null,
    created_at  timestamptz not null default now()
);
create index withdrawal_tickets_user_idx on account.withdrawal_tickets (user_id);
