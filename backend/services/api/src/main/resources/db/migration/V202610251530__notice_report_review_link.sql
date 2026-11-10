-- 공고 제보에서 「고치기」로 다시 연 검수 작업 (2026-10-25). 관리자는 그 검수에서 칸을 고쳐 승인하고 제보를 끝냅니다.
alter table notice.notice_reports add column review_job_id uuid;
comment on column notice.notice_reports.review_job_id is '이 제보로 다시 연 추출 검수 작업 ID (extraction review_queue.job_id)';
