-- 연락용 이메일 동의와 분리하며 기존 회원은 모두 수신 꺼짐으로 시작해요.
alter table notification.notifications drop constraint notifications_target_type_check;
alter table notification.notifications add constraint notifications_target_type_check
    check (target_type in ('NOTICE','BENEFIT','STARTUP_SUPPORT','SPACE_RECRUITMENT','REPORT'));
create table account.notification_emails (
    user_id uuid primary key references account.users(id) on delete cascade,
    email varchar(254),
    token_hash varchar(64),
    expires_at timestamptz,
    requested_at timestamptz not null,
    request_day date not null,
    request_count integer not null,
    verified_at timestamptz,
    enabled boolean not null default false,
    new_notice boolean not null default false,
    deadline boolean not null default false,
    report_answer boolean not null default false,
    consent_version varchar(40),
    collection_consent_version varchar(40),
    consented_at timestamptz,
    revoked_at timestamptz,
    unsubscribe_nonce varchar(64) not null,
    constraint notification_email_consent check (
        not enabled or (email is not null and verified_at is not null and consented_at is not null and consent_version is not null))
);
