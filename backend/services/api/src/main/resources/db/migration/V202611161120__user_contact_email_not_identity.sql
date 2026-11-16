-- 미인증 선택 연락처는 계정 식별자가 아니에요. 먼저 등록한 사람이 실제 소유자를 막거나 등록 여부를 열거하지 못하게 해요.
drop index account.users_email_uk;
