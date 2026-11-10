-- 관리자 검수 화면의 처리 기록·품질 통계 (2026-10-25). 누가 처리했는지, 고쳐서 승인했는지, 어느 칸을 고쳤는지 남깁니다.
-- decided_by는 api 서버가 보내는 검수자 표시(로그인 계정 ID)이고, 사용자 소득·자산 같은 값은 들어가지 않습니다.
alter table review_queue
    add column decided_by text,
    add column edited     boolean not null default false,
    add column edits      jsonb;

comment on column review_queue.decided_by is '처리한 검수자(api 서버 로그인 계정 ID). 예전 건·대체(SUPERSEDED)는 비어 있음';
comment on column review_queue.edited is '고쳐서 승인했는지(칸별 수정이나 고친 후보 전체를 보냄)';
comment on column review_queue.edits is '칸별 수정 목록 [{path, before, after}]. 고친 후보 전체를 보냈으면 null';

create index review_queue_decided_idx on review_queue (decided_at) where decided_at is not null;
