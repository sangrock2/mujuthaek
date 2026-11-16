-- 가입 필수 동의(만 14세 이상 확인, 이용약관, 개인정보 수집·이용)를 서버에 남겨요 (2026-11-16 보안 감사 L-2).
--  · 예전에는 동의가 화면 상태로만 있어서, 동의 화면을 건너뛰어도 회원 기능을 모두 쓸 수 있었어요
--  · 화면이 보여 준 약관·처리방침 버전과 동의 시각만 남겨요. 나이·생년월일은 받지 않아요(만 14세 이상이라는 확인이 동의 조건)
--  · 동의하기 전에는 회원 기능(내 정보 아래 대부분, 채팅 쓰기, 제보)을 쓸 수 없어요(SecurityConfig). 이미 가입한 회원도 한 번 동의해야 해요
alter table account.users
    add column terms_version   varchar(20),
    add column privacy_version varchar(20),
    add column terms_agreed_at timestamptz;

alter table account.users
    add constraint users_terms_together check (
        (terms_version is null and privacy_version is null and terms_agreed_at is null)
        or (terms_version is not null and privacy_version is not null and terms_agreed_at is not null));
