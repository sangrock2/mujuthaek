-- 창업지원 사업 제보 (2026-10-25). 공고 제보 표에 창업지원 사업(notice.policy_judgments)도 받게 넓혀요.
-- 제보 대상은 공고(notice_id)나 사업(raw_policy_id) 중 정확히 하나예요. 관리자 제보 화면은 한 목록으로 봐요.
alter table notice.notice_reports alter column notice_id drop not null;
alter table notice.notice_reports add column raw_policy_id uuid references notice.policy_judgments (raw_policy_id);
alter table notice.notice_reports add constraint notice_reports_one_target check ((notice_id is null) <> (raw_policy_id is null));

comment on column notice.notice_reports.raw_policy_id is '제보한 창업지원 사업 (notice.policy_judgments.raw_policy_id). 공고 제보면 null';

create index notice_reports_program_group_idx on notice.notice_reports (raw_policy_id, field) where status <> 'DONE' and raw_policy_id is not null;
-- 같은 회원이 같은 사업의 같은 칸을 처리 전에 또 제보하지 않게 (공고는 notice_reports_open_once)
create unique index notice_reports_program_open_once on notice.notice_reports (reporter_id, raw_policy_id, field)
    where status <> 'DONE' and raw_policy_id is not null;
