-- 일반 제보 (2026-10-29). 공고·혜택·사업에 묶이지 않은 제보(빠진 공고·정책 알려주기, 화면 오류 알리기, 기타)도 같은 표에 받아요.
-- 대상(notice_id·raw_policy_id·benefit_policy_id)이 모두 비어 있으면 일반 제보예요. 관리자 처리·답변 흐름은 그대로 써요.
-- 일반 제보는 같은 칸끼리 묶지 않아요(내용이 매번 달라요). 묶음은 NoticeReportRepository·NoticeReportService가 대상이 있을 때만 만들어요.
alter table notice.notice_reports drop constraint notice_reports_one_target;
alter table notice.notice_reports add constraint notice_reports_one_target
    check (num_nonnulls(notice_id, raw_policy_id, benefit_policy_id) <= 1);

-- 일반 제보 답변처럼 가리킬 대상이 없는 알림 (알림함에만 남고, 누르면 내 정보의 제보 탭으로 가요)
alter table notification.notifications alter column target_type drop not null;
alter table notification.notifications alter column target_id drop not null;
