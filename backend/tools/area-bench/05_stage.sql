drop table if exists bench.stage_seoul;
create table bench.stage_seoul as
select source_key, load_scope, name, large_code, small_code, industry_group,
       case when r < 0.03 then st_project(geom, 50, radians(90)) else geom end as geom
from (select s.*, random() r from area.stores s where load_scope = '서울') x
where r >= 0.03 + 0.01 or r < 0.03          -- 1% 폐업(0.03~0.04)은 뺌
union all
select 'NEW-' || to_char(clock_timestamp(), 'YYYYMMDDHH24MISS') || '-' || g, '서울', '새가게' || g, 'I2', 'I21201', 'CAFE',
       st_setsrid(st_makepoint(126.978 + (random()-0.5)*0.2, 37.5665 + (random()-0.5)*0.2), 4326)::geography
from generate_series(1, 5500) g;
create index on bench.stage_seoul (source_key);
analyze bench.stage_seoul;
