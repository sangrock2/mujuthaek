-- 같은 로그인에서 회전한 토큰을 함께 폐기해 로그아웃 뒤 옛 쿠키로 살아나지 않게 해요.
alter table account.refresh_tokens add column family_id uuid;
update account.refresh_tokens set family_id = id;
alter table account.refresh_tokens alter column family_id set default gen_random_uuid();
alter table account.refresh_tokens alter column family_id set not null;
create index refresh_tokens_family_idx on account.refresh_tokens (user_id, family_id);

-- 이전 버전에는 계보 정보가 없어요. 이미 회전한 옛 토큰의 유예만 끝내고,
-- 현재 사용 중인 미회전 토큰은 유지해 다음 회전부터 같은 계보를 이어가요.
update account.refresh_tokens
set expires_at = least(expires_at, current_timestamp)
where rotated_at is not null;
