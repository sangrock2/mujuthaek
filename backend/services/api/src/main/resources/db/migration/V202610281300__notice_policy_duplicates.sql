-- 정책 사업(창업 지원·입주 모집) 중복 의심 (2026-10-28 사용자 결정 A안).
-- 출처에 같은 사업이 두 번 올라오는 일이 있어요(실측: 온통청년 「청년창업 거주지원시설(창업하여家) 입주자 1차 모집」이 34분 간격으로 두 번).
-- 자동으로 지우지 않고(내용이 조금씩 달라요) 관리자 「제보·신고」의 「중복 의심」에 올려 「둘 다 둠」 또는 「나중 것 숨김」을 골라요.

-- 숨긴 사업은 열린 목록·판정·알림에서 빠져요
alter table notice.policy_judgments add column hidden_at timestamptz;
alter table notice.policy_judgments add column hidden_by text;

-- 중복 후보: raw_policy_id가 나중에 들어온 사업, candidate_of가 먼저 있던 사업
create table notice.policy_duplicate_candidates (
    raw_policy_id  uuid        not null references notice.policy_judgments (raw_policy_id),
    candidate_of   uuid        not null references notice.policy_judgments (raw_policy_id),
    reason         text        not null,               -- 같다고 본 근거 코드 (SAME_TITLE_REGION)
    status         text        not null default 'PENDING' check (status in ('PENDING', 'KEPT_BOTH', 'HIDDEN')),
    created_at     timestamptz not null default now(),
    decided_at     timestamptz,
    decided_by     text,
    primary key (raw_policy_id, candidate_of),
    check (raw_policy_id <> candidate_of)
);
create index policy_duplicate_candidates_pending_idx on notice.policy_duplicate_candidates (created_at)
    where status = 'PENDING';

-- 이미 들어와 있는 중복: 같은 분야 · 같은 제목(띄어쓰기·기호 무시) · 같은 지역이면 나중에 들어온 쪽을 후보로
-- (규칙은 PolicyDuplicateRepository.SAME_POLICY와 같아요)
insert into notice.policy_duplicate_candidates (raw_policy_id, candidate_of, reason, created_at)
select later.raw_policy_id, earlier.raw_policy_id, 'SAME_TITLE_REGION', later.created_at
from notice.policy_judgments later
join notice.policy_judgments earlier
  on later.field = earlier.field
 and regexp_replace(lower(later.title), '[[:space:][:punct:]·ㆍ「」『』]', '', 'g')
   = regexp_replace(lower(earlier.title), '[[:space:][:punct:]·ㆍ「」『』]', '', 'g')
 and array(select unnest(later.region_codes) order by 1) = array(select unnest(earlier.region_codes) order by 1)
 and (later.created_at, later.raw_policy_id) > (earlier.created_at, earlier.raw_policy_id)
on conflict do nothing;
