-- 검수 목록용 칸: 제목·원문 제목·신청 마감일을 저장할 때 한 번만 꺼내 둬요(생성 칸, 후보·원문이 바뀌면 PostgreSQL이 다시 채워요).
-- 검수 대기열·급한 검수·처리 기록이 건마다 큰 JSON(candidate·raw_event)을 풀지 않게 (2026-10-30 부하 시험: 대기열 첫 페이지 평균 213ms, 추출 DB 시간의 대부분)
-- 칸을 더하면 표를 한 번 다시 써요(작업 수만큼). 운영은 수천 건이라 짧아요.

-- 후보의 신청(APPLICATION) 일정 중 가장 이른 끝 날짜(YYYY-MM-DD). store.reviews의 applyEndsOn과 같은 규칙이에요
create function extraction_apply_ends_on(candidate jsonb) returns text
language sql immutable parallel safe
as $$
  select min(left(s->'endsAt'->>'value', 10))
  from jsonb_array_elements(
    case when jsonb_typeof(candidate->'schedules') = 'array' then candidate->'schedules' else '[]'::jsonb end) s
  where s->'kinds' ? 'APPLICATION' and s->'endsAt'->>'value' ~ '^\d{4}-\d{2}-\d{2}'
$$;

alter table extraction_jobs
  add column list_title text generated always as (candidate->'notice'->>'title') stored,
  add column list_source_title text generated always as (raw_event->'payload'->>'title') stored,
  add column list_apply_ends_on text generated always as (extraction_apply_ends_on(candidate)) stored;

-- 대기열은 상태 안에서 (들어온 시각, 작업 ID) 순으로 이어 받아요. 정렬과 커서 비교에 같은 순서의 인덱스를 써요
create index review_queue_status_order_idx on review_queue (status, created_at, job_id);
drop index review_queue_status_idx;
