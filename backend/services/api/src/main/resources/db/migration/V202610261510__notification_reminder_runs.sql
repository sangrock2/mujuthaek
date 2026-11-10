-- 하루 한 번 도는 알림 작업(마감 D-3·D-1)의 실행 기록. 날짜·작업마다 한 줄이라, api 서버가 여러 대여도 먼저 이 줄을 넣은 서버만 그날 작업을 해요.
-- 줄 넣기와 알림 요청(아웃박스)이 한 트랜잭션이라, 중간에 실패하면 줄도 사라져 다음 확인 때 다시 해요
create table notification.reminder_runs (
    run_date    date        not null,                   -- 한국 날짜
    kind        text        not null check (kind in ('DEADLINE')),
    requested   int         not null default 0,         -- 적은 알림 요청 수
    ran_at      timestamptz not null,
    primary key (run_date, kind)
);
