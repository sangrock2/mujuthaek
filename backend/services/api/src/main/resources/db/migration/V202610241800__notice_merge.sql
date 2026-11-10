-- 같은 공고 자동 합치기: 같은 공고가 여러 출처(기관 게시판·LH API)에 올라오면 공고 하나로 합쳐요.
-- 먼저 공개된 공고를 남겨 사용자가 보던 공고 ID·버전이 이어지고, 합쳐진 공고 ID로 물어도 남은 공고가 나와요.

-- 공고일 (같은 공고 후보 찾기용, 상세의 notice.announcedOn. 보류했으면 비워요)
alter table notice.notices add column announced_on date;
update notice.notices n set announced_on = (v.payload -> 'notice' -> 'notice' ->> 'announcedOn')::date
from notice.notice_versions v
where v.notice_id = n.id and v.version = n.current_version
  and v.payload -> 'notice' -> 'notice' ->> 'announcedOn' ~ '^\d{4}-\d{2}-\d{2}$';

-- 합쳐진 공고는 남은 공고를 가리키고 목록·재계산에서 빠져요
alter table notice.notices add column merged_into uuid references notice.notices (id);
create index notices_identity_idx on notice.notices (field, announced_on) where merged_into is null;

-- 기준 출처: 합쳐진 공고의 내용은 기준 출처(원래 공고 글) 하나만 바꿔요(출처끼리 번갈아 덮어쓰지 않게).
-- 순서: 공고문 PDF가 있는 쪽 → 먼저 게시된 쪽 → 먼저 들어온 쪽 → 원본 글 ID 순서
alter table notice.notices add column base_root_post_id uuid;
update notice.notices set base_root_post_id = raw_post_id;

-- 같은 공고 후보 (notice_id가 나중에 공개된 공고, candidate_of가 먼저 있던 공고)
create table notice.notice_duplicate_candidates (
    notice_id     uuid        not null references notice.notices (id),
    candidate_of  uuid        not null references notice.notices (id),
    reason        text        not null,                   -- 같다고 본 근거 코드
    status        text        not null check (status in ('PENDING', 'MERGED', 'REJECTED', 'UNMERGED')),
    created_at    timestamptz not null,
    decided_at    timestamptz,
    primary key (notice_id, candidate_of)
);
create index notice_duplicate_candidates_pending_idx on notice.notice_duplicate_candidates (created_at)
    where status = 'PENDING';

-- 출처(원래 공고 글)마다 마지막으로 반영한 결과. 기준 출처를 바꾸거나 합치기를 되돌릴 때 이 결과를 다시 적용해요(수신 기록에 payload가 있음)
create table notice.notice_source_heads (
    root_post_id       uuid        primary key,
    notice_id          uuid        not null references notice.notices (id), -- 지금 속한 공고
    original_notice_id uuid        not null references notice.notices (id), -- 처음 공개된 공고 (되돌리기용)
    latest_event_id    uuid        not null,                                 -- 마지막으로 반영한 extraction.completed
    has_pdf            boolean     not null,                                 -- 결과에 공고문 PDF가 있는지
    posted_on          date,                                                 -- 원래 공고 글 게시일
    first_seen_at      timestamptz not null,
    updated_at         timestamptz not null
);
create index notice_source_heads_notice_idx on notice.notice_source_heads (notice_id);

insert into notice.notice_source_heads
    (root_post_id, notice_id, original_notice_id, latest_event_id, has_pdf, posted_on, first_seen_at, updated_at)
select p.raw_post_id, p.notice_id, p.notice_id, v.source_event_id,
       exists (select 1 from jsonb_array_elements(v.payload -> 'notice' -> 'documents') d where d ->> 'kind' = 'PDF'),
       p.posted_on, p.created_at, p.updated_at
from notice.notice_posts p
join lateral (
    select source_event_id, payload from notice.notice_versions
    where raw_post_id = p.raw_post_id order by version desc limit 1
) v on true
where p.kind = 'NOTICE';

-- 원본 글·후속 안내가 처음 속한 공고 (합치기 되돌리기용)
alter table notice.notice_posts add column original_notice_id uuid references notice.notices (id);
update notice.notice_posts set original_notice_id = notice_id;
alter table notice.notice_posts alter column original_notice_id set not null;

alter table notice.notice_follow_ups add column original_notice_id uuid references notice.notices (id);
update notice.notice_follow_ups set original_notice_id = notice_id;
alter table notice.notice_follow_ups alter column original_notice_id set not null;
