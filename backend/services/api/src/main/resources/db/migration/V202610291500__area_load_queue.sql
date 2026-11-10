-- area 적재를 메시지 수신과 떼어요. 수신기는 PENDING 요청만 남기고 바로 ack하고, 작업자(AreaLoadWorker)가 하나씩 꺼내 적재해요.
-- 큰 적재(도로명주소 시도 하나에 100만 줄)가 RabbitMQ consumer_timeout(30분)을 넘겨 채널이 닫히고 수신기가 멈추던 문제를 막아요.
alter table area.load_runs drop constraint load_runs_status_check;
alter table area.load_runs
    add constraint load_runs_status_check
        check (status in ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED'));

alter table area.load_runs
    add column allow_shrink    boolean     not null default false,  -- 행이 절반 넘게 줄어도 적재할지 (요청 그대로)
    add column attempts        integer     not null default 0,      -- 같은 파일을 꺼내 적재한 횟수 (다시 넣은 요청은 이어서 셈)
    add column next_attempt_at timestamptz not null default now();  -- PENDING을 이 시각부터 꺼내요 (연결 오류 뒤 잠깐 쉬기)

comment on column area.load_runs.started_at is 'PENDING이면 요청 받은 시각, RUNNING부터는 적재를 시작한 시각';

-- 이전 방식에서 멈춘 채 남은 RUNNING(api가 멈추거나 꺼짐)은 실패로 닫고, 아직 성공한 적 없는 파일은 한 번씩 다시 기다리게 넣어요.
-- 마이그레이션은 api가 뜰 때 돌아서 이때 도는 적재는 없어요.
with stale as (
    update area.load_runs
       set status = 'FAILED', error = 'api가 멈추거나 꺼져 끝나지 못했어요 (적재 대기열로 바꾸며 정리)', finished_at = now()
     where status = 'RUNNING'
    returning source, load_scope, file_key, file_sha256, data_date
)
insert into area.load_runs (source, load_scope, file_key, file_sha256, data_date, status, attempts)
select distinct on (s.source, s.load_scope, s.file_sha256)
       s.source, s.load_scope, s.file_key, s.file_sha256, s.data_date, 'PENDING', 1
  from stale s
 where not exists (select 1
                     from area.load_runs r
                    where r.status = 'SUCCEEDED'
                      and r.source = s.source and r.load_scope = s.load_scope and r.file_sha256 = s.file_sha256);

-- 같은 파일(원천·범위·지문)은 기다리거나 도는 요청이 하나만 있어요
create unique index load_runs_open_file_uq
    on area.load_runs (source, load_scope, file_sha256)
    where status in ('PENDING', 'RUNNING');

create index load_runs_pending_idx on area.load_runs (next_attempt_at) where status = 'PENDING';
