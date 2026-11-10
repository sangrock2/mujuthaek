-- 정책 판정 틀에 출처 안내(extraction.completed payload.policyInfo)를 같이 보관해요: 지원 분야 · 요약 · 기관 · 문의처 · 접수 방법 · 신청/안내 주소 · 지원 금액 구절.
-- AI 값이 아니라 출처 API 칸을 옮긴 것이고, 판정에는 쓰지 않아요(화면 안내용). 예전 이벤트로 저장된 줄은 null
alter table notice.policy_judgments add column info jsonb;
