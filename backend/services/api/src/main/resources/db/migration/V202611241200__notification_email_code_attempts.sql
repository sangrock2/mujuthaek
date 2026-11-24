-- null은 기존 링크 방식이거나 인증할 코드가 없는 상태입니다.
alter table account.notification_emails
    add column code_attempts integer check (code_attempts between 0 and 5);
