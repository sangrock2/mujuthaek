-- 탈퇴한 회원 기록 (user.withdrawn). 탈퇴 전에 api가 만든 알림 요청이 재시도 때문에 user.withdrawn보다 늦게 오면,
-- 지운 발송 줄을 다시 만들어 탈퇴한 회원에게 보낼 수 있어요. 이 기록으로 그런 요청의 그 회원을 걸러요
-- 회원 ID와 시각만 둬요. 90일 지나면 지워요 (그보다 늦게 오는 요청은 없다고 봐요: api 아웃박스는 보낸 지 하루 뒤 지워요)
create table withdrawn_users (
    user_id      uuid        primary key,
    withdrawn_at timestamptz not null
);
create index withdrawn_users_at_idx on withdrawn_users (withdrawn_at);
