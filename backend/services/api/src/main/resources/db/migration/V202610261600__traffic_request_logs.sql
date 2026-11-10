-- 트래픽: api 서버 요청 기록 (2026-10-26). GA가 볼 수 없는 봇·도구·요청 많은 IP·로그인 실패·관리자 접근을 세요.
-- 회원 ID는 저장하지 않아요. 원본 IP(ip)는 보안 대응용으로 보관 기간(기본 14일)이 지나면 지우고, 통계는 ip_hash(그날만 쓰는 값으로 섞은 해시)로 봐요.
create table traffic.request_logs (
    id           bigint generated always as identity primary key,
    occurred_at  timestamptz not null,
    method       text        not null,
    path         text        not null,                 -- ID·숫자를 {id}로 바꾼 경로
    status       int         not null,
    duration_ms  int         not null,
    client       text        not null check (client in ('HUMAN', 'SEARCH_BOT', 'PREVIEW_BOT', 'TOOL', 'MONITOR', 'UNKNOWN')),
    user_agent   text,                                 -- 앞 200자
    ip_hash      text        not null,
    ip           text,                                 -- 원본 IP. 보관 기간이 지나면 null
    area         text        not null check (area in ('API', 'ADMIN', 'AUTH', 'LOGIN')),
    login_result text        check (login_result in ('SIGNUP', 'LOGIN', 'FAILED'))
);

create index request_logs_time on traffic.request_logs (occurred_at);
create index request_logs_ip_time on traffic.request_logs (ip_hash, occurred_at);
