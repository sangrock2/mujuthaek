-- 분야별 비용 집계와 월 상한 80% 경고 (2026-10-23, cost_alert.py)
-- field: 비용을 쓴 수집 이벤트의 분야(HOUSING·BUSINESS_SPACE·STARTUP_SUPPORT·SPACE_RECRUITMENT). 이 칸이 생기기 전 줄은 비어 있고,
-- 집계할 때 작업 기록(extraction_jobs.field)으로 채웁니다(정책 판정 틀처럼 작업 기록이 없으면 UNKNOWN)
alter table extraction_spend add column field text;

-- 보낸 경고 기록: 종류·기간(한국 시간 'YYYY-MM')마다 한 줄. 워커를 다시 시작하거나 여럿이 돌아도 같은 달에 두 번 보내지 않습니다
create table extraction_alerts (
    kind       text        not null,
    period     text        not null,
    created_at timestamptz not null default now(),
    primary key (kind, period)
);
