-- 로그인 연장으로 바꾼 refresh token을 바로 지우지 않고 바꾼 시각만 적어요. 바꾼 뒤 잠깐(30초)은 같은 값이 다시 와도 받아 줘요
-- (새로고침을 빠르게 하거나 탭 여러 개가 함께 연장하면, 늦게 온 요청이 옛 쿠키를 들고 와 로그아웃되던 문제 · 2026-10-29)
-- 지난 값은 만료된 값과 함께 정리 작업이 지워요
alter table account.refresh_tokens add column rotated_at timestamptz;
