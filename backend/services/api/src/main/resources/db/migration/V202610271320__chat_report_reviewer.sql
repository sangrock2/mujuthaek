-- 채팅 신고를 누가 언제 처리했는지 (2026-10-27). 관리자 「처리 기록」에 보여요. 처리한 관리자가 탈퇴해도 줄은 남겨요(회원 ID만)
alter table chat.message_reports add column reviewed_by uuid;
alter table chat.message_reports add column reviewed_at timestamptz;
