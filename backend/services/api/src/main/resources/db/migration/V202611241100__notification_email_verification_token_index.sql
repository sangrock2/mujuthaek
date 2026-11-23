-- 인증 토큰은 이메일 주소가 아닌 계정에 매여 있고 사용하면 해시가 사라집니다.
create unique index notification_email_active_token_uk
    on account.notification_emails (token_hash) where token_hash is not null;
