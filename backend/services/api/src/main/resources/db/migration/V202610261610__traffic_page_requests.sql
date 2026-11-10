-- 트래픽: 프론트 서버가 넘기는 화면 요청도 기록 (2026-10-26). 화면만 긁어 가는 봇은 api를 부르지 않아 api 요청 기록에 안 잡혀요.
-- 화면 요청은 프론트 서버가 응답하기 전에 넘겨서 응답 코드·처리 시간을 몰라요(null).
alter table traffic.request_logs alter column status drop not null;
alter table traffic.request_logs alter column duration_ms drop not null;
alter table traffic.request_logs drop constraint request_logs_area_check;
alter table traffic.request_logs add constraint request_logs_area_check
    check (area in ('API', 'ADMIN', 'AUTH', 'LOGIN', 'PAGE'));
