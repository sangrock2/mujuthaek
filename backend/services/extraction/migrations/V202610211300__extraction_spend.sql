-- 유료 모델 비용 장부 (2026-10-21): 호출을 보내기 전에 최악 비용(reserved_usd)을 적고, 응답이 오면 실제 비용(cost_usd)으로 바꿉니다.
-- 하루·월 전체 상한(EXTRACTION_DAILY_BUDGET_USD·EXTRACTION_MONTHLY_BUDGET_USD)을 이 장부로 셉니다(한국 시간 기준 날·달).
-- 처리 중 프로세스가 죽어 응답을 못 받은 호출은 cost_usd가 비어 최악 비용으로 남습니다(청구됐을 수 있으므로).
-- job_id: 처리 결과를 저장하면 그 작업 ID를 적습니다. 비어 있으면 저장 전에 중단된 처리의 비용입니다(다음 처리의 원본 버전 예산에서 뺌).
create table extraction_spend (
    id           uuid primary key,
    run_id       uuid not null,
    event_id     uuid,
    raw_post_id  uuid,
    raw_version  int,
    job_id       uuid,
    model        text not null,
    reserved_usd numeric(12, 6) not null,
    cost_usd     numeric(12, 6),
    created_at   timestamptz not null default now(),
    settled_at   timestamptz
);
create index extraction_spend_created_idx on extraction_spend (created_at);
create index extraction_spend_version_idx on extraction_spend (raw_post_id, raw_version);
create index extraction_spend_run_idx on extraction_spend (run_id);

-- 처리 시작 기록 (2026-10-21): 저장 전에 프로세스가 죽으면(메모리 부족·PDF 라이브러리 충돌·컨테이너 종료) 같은 메시지가 끝없이 다시 옵니다.
-- 시작 횟수와 저장된 작업 수를 비교해, 같은 이벤트가 연달아 중단되면 더 처리하지 않고 기록만 남깁니다.
create table extraction_starts (
    event_id   uuid        not null,
    started_at timestamptz not null default now()
);
create index extraction_starts_event_idx on extraction_starts (event_id);
