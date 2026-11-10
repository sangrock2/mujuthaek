-- 정책 판정 틀 (2026-10-22): 창업지원(STARTUP_SUPPORT)·사업공간 모집(SPACE_RECRUITMENT)은 공고가 아니라 notice.notices에 넣지 않고,
-- 판정 담당이 읽는 칸만 둬요. 사업공간 모집은 findOpenForJudgment(BUSINESS_SPACE), 창업지원은 findOpenProgramsForJudgment()로 나가요.
-- 추출 결과(extraction.completed)가 정책 수집 이벤트에서 만든 판정 틀을 실어 와요. 같은 정책은 더 높은 버전만 반영해요.
create table notice.policy_judgments (
    raw_policy_id   uuid        primary key,              -- 수집 DB 정책 ID (raw.policy.collected의 rawPolicyId)
    field           text        not null check (field in ('STARTUP_SUPPORT', 'SPACE_RECRUITMENT')),
    raw_version     int         not null,
    source_event_id uuid        not null,                 -- 마지막으로 반영한 extraction.completed eventId
    title           text        not null,
    apply_start     date,                                 -- 접수 시작일 (모르면 null)
    apply_end       date,                                 -- 접수 마감일 (상시거나 모르면 null)
    region_codes    text[]      not null,                 -- 지원 지역 시군구 5자리(xx000은 시도 전체), 빈 목록은 전국
    frame           jsonb       not null,                 -- 판정 틀 그대로 (startup-support-judgment.v1 / business-space-judgment.v1)
    created_at      timestamptz not null,
    updated_at      timestamptz not null
);

create index policy_judgments_open on notice.policy_judgments (field, apply_end);
