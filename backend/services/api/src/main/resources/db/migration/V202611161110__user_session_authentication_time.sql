-- 회전으로 갱신되지 않는 로그인 계보의 소셜 인증 시각이에요.
-- 과거 계보의 실제 인증 시각은 복원할 수 없어, 민감 동작에는 다시 로그인을 요구해요.
alter table account.refresh_tokens add column authenticated_at timestamptz;
update account.refresh_tokens set authenticated_at = timestamptz '1970-01-01 00:00:00+00';
alter table account.refresh_tokens alter column authenticated_at set not null;
-- 이전 앱/운영 삽입 경로도 최근 인증으로 간주하지 않고 안전하게 처리해요.
alter table account.refresh_tokens alter column authenticated_at set default timestamptz '1970-01-01 00:00:00+00';
