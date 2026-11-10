-- 계정 연락용 이메일 (user 모듈, 2026-10-28). 알림 발송용이 아니라 약관·개인정보처리방침 변경, 이용 제한, 계정 안내처럼 꼭 알려야 할 때만 써요
--  · 선택 항목이라 동의를 받고 넣어요: 어떤 동의 문구(버전)에 언제 동의했는지 같이 남겨요. 주소를 지우면(동의 철회) 셋 다 비워요
--  · 인증 코드는 받지 않아요. 같은 주소를 여러 회원이 써도 돼요(unique 아님)
--  · 탈퇴하면 users 행과 함께 지워져요. 주소는 로그에 남기지 않아요
alter table account.users
    add column email                 varchar(254),   -- 연락용 이메일 (RFC 5321 최대 길이)
    add column email_consent_version varchar(20),    -- 동의한 문구 버전 (예: email-v1)
    add column email_consented_at    timestamptz,
    add constraint users_email_consent check (
        (email is null and email_consent_version is null and email_consented_at is null)
        or (email is not null and email_consent_version is not null and email_consented_at is not null));
