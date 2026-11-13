-- 지금까지 쌓인 쿼리별 누적 값. run.sh가 테스트 전후로 떠서 차이(=테스트 동안 쓴 시간)를 slow_queries.csv로 남겨요
select queryid, calls, round(total_exec_time::numeric, 2) as total_ms, rows, shared_blks_hit, shared_blks_read,
       left(regexp_replace(query, '\s+', ' ', 'g'), 500) as query
from pg_stat_statements
where dbid = (select oid from pg_database where datname = current_database())
  and queryid is not null;
