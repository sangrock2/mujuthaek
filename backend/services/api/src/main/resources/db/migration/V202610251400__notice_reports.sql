-- 공고 제보 (2026-10-25). 사용자가 공고 상세의 값이 원문·실제와 다르다고 알려 주면 관리자 제보 화면에서 처리합니다.
-- 혜택·창업지원(benefit)·생활권(area) 제보는 여기 두지 않습니다(각 모듈 담당). 답장 발송은 notification이 NoticeReportAnswered 이벤트로 받습니다.
-- 사용자 소득·자산·나이는 받지 않습니다. 회원이 탈퇴하면 그 회원의 제보는 지웁니다(UserWithdrawn, 요구사항 3-16).
create table notice.notice_reports (
    id             uuid        primary key,
    notice_id      uuid        not null references notice.notices (id),
    reporter_id    uuid        not null,                 -- 제보한 회원 (api 로그인 계정 ID)
    field          text        not null,                 -- 화면의 칸 이름 (보증금, 신청 마감 …)
    current_value  text,                                 -- 제보 당시 화면에 보인 값
    reported_value text,                                 -- 사용자가 맞다고 한 값
    note           text,                                 -- 사용자가 쓴 설명
    screen         text,                                 -- 제보한 화면 (공고 상세 · 내 집 …)
    status         text        not null default 'NEW' check (status in ('NEW', 'DOING', 'DONE')),
    result         text        check (result in ('FIXED', 'KEPT')),  -- DONE일 때: 고침 · 그대로 둠
    reply          text,                                 -- 제보한 사람에게 보낼 답
    handled_by     text,                                 -- 처리한 관리자 (로그인 계정 ID)
    created_at     timestamptz not null default now(),
    started_at     timestamptz,
    handled_at     timestamptz,
    check ((status = 'DONE') = (result is not null))
);

create index notice_reports_status_idx on notice.notice_reports (status, created_at desc);
create index notice_reports_group_idx on notice.notice_reports (notice_id, field) where status <> 'DONE';
create index notice_reports_reporter_idx on notice.notice_reports (reporter_id, created_at);
-- 같은 회원이 같은 공고의 같은 칸을 처리 전에 또 제보하지 않게
create unique index notice_reports_open_once on notice.notice_reports (reporter_id, notice_id, field) where status <> 'DONE';
