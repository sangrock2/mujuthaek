-- 리뷰 2026-10-23 (PR #70): 판정 목록의 정책 원문 주소와 상시 모집 여부.
-- detail_url: 수집한 정책 원문 주소(extraction.completed의 detailUrl, 모르면 null). 정책은 공고 상세 API로 찾을 수 없어 화면이 이 주소로 보내요.
-- apply_always: 출처가 상시 모집이라고 분명히 알려 준 정책(applyAlways). 마감일(apply_end)이 없고 상시도 아니면 마감일을 모르는 것이라
--   판정 목록에서 빼요(공고가 UNKNOWN을 빼는 것과 같은 규칙). 이전에 저장된 줄은 false라, 마감일 없는 줄은 새 결과가 올 때까지 빠져요.
-- 검수 대기(IN_REVIEW) 틀은 이제 저장하지 않고(공개 중인 이전 버전 유지, 첫 버전은 승인 전까지 비공개) 이전에 저장된 IN_REVIEW 줄은 조회에서 빼요.
alter table notice.policy_judgments
    add column detail_url text,
    add column apply_always boolean not null default false;
