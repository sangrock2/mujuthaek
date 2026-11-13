-- 데이터 양. 개선 전후에 공고·혜택 수가 크게 달라지면 비교가 틀어져서 같이 남겨요
select schemaname || '.' || relname as "table", n_live_tup as rows,
       pg_size_pretty(pg_total_relation_size(relid)) as size
from pg_stat_user_tables
order by n_live_tup desc
limit 40;
