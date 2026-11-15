-- 세션 검사를 매 요청 수행하고, 사용한 해시는 재사용 탐지용으로 원래 만료일까지 보관해요.
-- 현재 세션 조회와 계정별 발급 제한이 과거 회전 행 전체를 읽지 않게 해요.
create index refresh_tokens_active_session_idx
on account.refresh_tokens (user_id, family_id) where rotated_at is null;
create index refresh_tokens_issued_idx on account.refresh_tokens (user_id, created_at);
