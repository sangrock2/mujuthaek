-- 혜택 검수 목록용 칸: 신청 마감일·서비스 대상 여부를 저장할 때 한 번만 꺼내 둬요(생성 칸, payload가 바뀌면 PostgreSQL이 다시 채워요).
-- 혜택 검수 대기열이 건마다 큰 결과 JSON(payload)을 풀지 않게 (2026-10-30 부하 시험: 첫 페이지 평균 30ms, 공고 검수 목록을 같은 방법으로 고친 뒤 남은 추출 DB 시간 1위)

alter table benefit_results
  add column list_apply_end text generated always as (payload->'schedule'->>'applyEnd') stored,
  -- relevant가 true·false가 아니면 null(형 변환 실패로 결과 저장이 막히지 않게)
  add column list_relevant boolean generated always as (
    case when payload->>'relevant' in ('true', 'false') then (payload->>'relevant')::boolean end) stored;

-- 대기열은 상태 안에서 (들어온 시각, 검수 ID) 순으로 이어 받아요. 정렬과 커서 비교에 같은 순서의 인덱스를 써요
create index benefit_reviews_status_order_idx on benefit_reviews (status, created_at, id);
drop index benefit_reviews_status_idx;
