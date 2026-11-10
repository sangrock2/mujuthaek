-- 회원·소셜 계정·refresh token (user 모듈, 스키마 account)
-- 사용자 소득·자산·나이는 저장하지 않아요 (CLAUDE.md). 소셜 계정에서는 닉네임만 받아요

create table account.users (
    id            uuid primary key,                                   -- UUID v7
    nickname      varchar(50),
    role          varchar(20) not null default 'USER' check (role in ('USER', 'ADMIN')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    last_login_at timestamptz
);

-- 한 회원이 여러 소셜 계정을 이을 수 있게 따로 둬요 (카카오 먼저, 네이버·구글은 나중에)
create table account.social_accounts (
    id               uuid primary key,
    user_id          uuid        not null references account.users (id) on delete cascade,
    provider         varchar(20) not null check (provider in ('KAKAO', 'NAVER', 'GOOGLE')),
    provider_user_id varchar(100) not null,                           -- 카카오 회원번호 등
    created_at       timestamptz not null default now(),
    constraint social_accounts_provider_user_uk unique (provider, provider_user_id)
);
create index social_accounts_user_idx on account.social_accounts (user_id);

-- 로그인 유지용 refresh token (JWT access token은 저장하지 않아요). 원문은 쿠키에만 있고 여기엔 SHA-256 해시만 둬요.
-- 로그아웃·재발급(회전)·탈퇴 때 지워서 바로 무효로 만들 수 있어요
create table account.refresh_tokens (
    id         uuid primary key,
    user_id    uuid        not null references account.users (id) on delete cascade,
    token_hash varchar(64) not null unique,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);
create index refresh_tokens_user_idx on account.refresh_tokens (user_id);
create index refresh_tokens_expires_idx on account.refresh_tokens (expires_at);
