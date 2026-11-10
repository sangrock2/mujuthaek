-- 주거·복지 정책(혜택) 제보 (2026-10-25). 공고 제보 표에 혜택 정책도 받게 넓혀요.
-- 혜택 정책은 api 안에 표가 아직 없어(benefit 모듈) 추출 서비스의 정제 결과로 있는지 확인하고, 제목은 제보 때 받아 둬요.
-- 제보 대상은 공고(notice_id)·창업지원 사업(raw_policy_id)·혜택 정책(benefit_policy_id) 중 정확히 하나예요.
alter table notice.notice_reports add column benefit_policy_id uuid;
alter table notice.notice_reports add column target_title text;
alter table notice.notice_reports drop constraint notice_reports_one_target;
alter table notice.notice_reports add constraint notice_reports_one_target
    check (num_nonnulls(notice_id, raw_policy_id, benefit_policy_id) = 1);

comment on column notice.notice_reports.benefit_policy_id is '제보한 혜택 정책 (policy.extracted의 rawPolicyId). 다른 대상이면 null';
comment on column notice.notice_reports.target_title is '혜택 정책 제목 (제보 때 추출 서비스에서 받아 둠). 공고·사업은 그 표의 제목을 써서 null';

create index notice_reports_benefit_group_idx on notice.notice_reports (benefit_policy_id, field) where status <> 'DONE' and benefit_policy_id is not null;
-- 같은 회원이 같은 정책의 같은 칸을 처리 전에 또 제보하지 않게
create unique index notice_reports_benefit_open_once on notice.notice_reports (reporter_id, benefit_policy_id, field)
    where status <> 'DONE' and benefit_policy_id is not null;
