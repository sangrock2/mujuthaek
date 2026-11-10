drop table if exists bench.notices, bench.loc_scores, bench.loc_metrics, bench.m;
create table bench.notices as
select g as id, g as site_id, '공고 ' || g as title,
       (array['UPCOMING','APPLYING','APPLYING','CLOSED'])[1 + floor(random()*4)::int] as status,
       date '2026-10-22' + floor(random()*60)::int as apply_end, '11440' as region_code
from generate_series(1, 3000) g;
alter table bench.notices add primary key (id);
create index on bench.notices (status, apply_end, id);
create table bench.loc_scores as
select s.id as site_id, c as category, floor(random()*101)::int as score
from bench.sites s, unnest(array['TRANSIT','SCHOOL','PARK','CONVENIENCE','HOSPITAL']) c;
alter table bench.loc_scores add primary key (site_id, category);
create table bench.loc_metrics as
select s.id as site_id, m as metric, round((random()*2000)::numeric, 1) as value
from bench.sites s, unnest(array['station_nearest_m','station_count_1km','bus_stop_nearest_m','bus_stop_count_300m',
  'elementary_nearest_m','middle_count_1km','high_count_1km','park_nearest_m','park_area_1km_m2','hospital_nearest_m',
  'clinic_count_500m','convenience_store_count_300m','mart_nearest_m','store_count_300m']) m;
alter table bench.loc_metrics add primary key (site_id, metric);
analyze bench.notices; analyze bench.loc_scores; analyze bench.loc_metrics;
