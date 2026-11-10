-- 연락용 이메일 중복 금지 (2026-10-28 정책 변경). 한 주소는 한 회원만 써요
--  · 대소문자만 다른 주소(Hong@ex.com · hong@ex.com)도 같은 주소로 봐요 (lower)
--  · 비어 있는 회원은 상관없어요. 탈퇴하면 행이 지워져서 그 주소를 다른 회원이 쓸 수 있어요
create unique index users_email_uk on account.users (lower(email)) where email is not null;
