-- 검수 대기 중에 같은 공고의 더 새 버전(또는 그 공고를 고친 정정공고)이 발행되면 이전 대기 건을 '대체됨'(SUPERSEDED)으로 정리합니다 (2026-10-23, 검토 의견).
-- review_queue.status: PENDING·APPROVED·REJECTED·SUPERSEDED (글자 칸이라 값 제한은 없음). 대체 시각은 decided_at, 메모(note)에 사유를 남깁니다.
-- 누가·어느 버전이 대체했는지: 새 버전을 발행한 작업(superseded_by_job_id)과 그 원본·버전.
alter table review_queue
    add column superseded_by_job_id      uuid references extraction_jobs (id),
    add column superseded_by_raw_post_id uuid,
    add column superseded_by_version     int;

comment on column review_queue.status is 'PENDING·APPROVED·REJECTED·SUPERSEDED(같은 공고의 새 버전·정정공고가 발행되어 대체됨)';
comment on column review_queue.superseded_by_job_id is '대체한 작업(새 버전·정정공고를 발행한 extraction_jobs.id)';
comment on column review_queue.superseded_by_raw_post_id is '대체한 공고의 rawPostId (같은 공고면 자기 원본, 정정공고면 정정공고의 원본)';
comment on column review_queue.superseded_by_version is '대체한 공고의 원본 버전';

-- 이 변경 전에 쌓인 건: 같은 원본의 더 새 버전이 이미 발행된 대기 건을 가장 새 발행 버전으로 대체 처리합니다(어차피 승인은 막혀 있던 건).
-- 정정공고로 인한 대체는 앞으로 발행될 때부터만 합니다.
update review_queue r
   set status = 'SUPERSEDED',
       decided_at = now(),
       note = coalesce(r.note || ' / ', '') || 'v' || newer.raw_version || ' 발행으로 대체됨(마이그레이션 정리)',
       superseded_by_job_id = newer.id,
       superseded_by_raw_post_id = newer.raw_post_id,
       superseded_by_version = newer.raw_version
  from extraction_jobs j
  cross join lateral (
        select n.id, n.raw_post_id, n.raw_version
          from extraction_jobs n
         where n.raw_post_id = j.raw_post_id and n.raw_version > j.raw_version and n.completed_event_id is not null
         order by n.raw_version desc, n.created_at desc
         limit 1
  ) newer
 where r.job_id = j.id and r.status = 'PENDING';
