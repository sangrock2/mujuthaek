-- 생활권 제보 (2026-10-25). 공고 상세의 생활권 값(역까지 거리 등)이 실제와 다르다고 회원이 알려 주면 관리자 제보 화면에서 처리해요.
-- 공고 제보(notice.notice_reports)와 같은 흐름이고, 답장은 AreaReportAnswered 이벤트로 알림 쪽에 넘겨요. 회원이 탈퇴하면 지워요.
create table area.area_reports (
    id                 uuid        primary key,
    notice_id          uuid        not null,             -- 공고 ID (area.notice_locations에 위치가 있는 공고만)
    notice_location_id text,                             -- 공고 상세 locations[].id (단지가 여럿이면)
    reporter_id        uuid        not null,             -- 제보한 회원 (api 로그인 계정 ID)
    field              text        not null,             -- 화면의 항목 이름 (역까지 거리, 가까운 학교 …)
    current_value      text,
    reported_value     text,
    note               text,
    screen             text,
    status             text        not null default 'NEW' check (status in ('NEW', 'DOING', 'DONE')),
    result             text        check (result in ('FIXED', 'KEPT')),
    reply              text,
    handled_by         text,
    created_at         timestamptz not null default now(),
    started_at         timestamptz,
    handled_at         timestamptz,
    check ((status = 'DONE') = (result is not null))
);

create index area_reports_status_idx on area.area_reports (status, created_at desc);
create index area_reports_group_idx on area.area_reports (notice_id, field) where status <> 'DONE';
create index area_reports_reporter_idx on area.area_reports (reporter_id, created_at);
create unique index area_reports_open_once on area.area_reports (reporter_id, notice_id, field) where status <> 'DONE';
