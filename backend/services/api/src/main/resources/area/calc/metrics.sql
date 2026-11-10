-- 4단계 세권 지표: 대상 위치(임시 테이블 target_locations의 location_id) 전체를 한 쿼리로 계산해 location_metrics에 반영해요.
-- 시설 조건은 부분 인덱스(V202610241851__area_metric_indexes.sql)의 where와 글자까지 같아야 인덱스가 써져요.
-- 지하철역은 노선마다 줄이 따로라 "1km 안 역 수"는 역 이름으로 묶어 세요(환승역 하나 = 1).
-- 가장 가까운 거리: <->(KNN)는 구면 거리로 순서를 정하고 st_distance는 타원체 거리라, 거리가 비슷한 두 곳이면 <->의 1등이
-- 실제로 가장 가깝지 않을 수 있어요(실제 자료 3,000곳 중 9곳, 최대 164m). 그래서 <->로 5개를 뽑고 그중 st_distance가 가장 작은 값을 써요.
delete from area.location_metrics m using target_locations t where m.location_id = t.location_id;
insert into area.location_metrics (location_id, metric, value)
select w.location_id, x.metric, x.value
from (
  select l.location_id,
    (select min(st_distance(c.geom, l.geom)) from (select f.geom from area.facilities f where f.kind = 'SUBWAY_STATION' order by f.geom <-> l.geom limit 5) c) as station_nearest_m,
    (select count(distinct f.name) from area.facilities f where f.kind = 'SUBWAY_STATION' and st_dwithin(f.geom, l.geom, 1000)) as station_count_1km,
    (select min(st_distance(c.geom, l.geom)) from (select f.geom from area.facilities f where f.kind = 'BUS_STOP' order by f.geom <-> l.geom limit 5) c) as bus_stop_nearest_m,
    (select count(*) from area.facilities f where f.kind = 'BUS_STOP' and st_dwithin(f.geom, l.geom, 300)) as bus_stop_count_300m,
    (select min(st_distance(c.geom, l.geom)) from (select f.geom from area.facilities f where f.kind = 'SCHOOL' and f.sub_kind = 'ELEMENTARY' order by f.geom <-> l.geom limit 5) c) as elementary_nearest_m,
    (select count(*) from area.facilities f where f.kind = 'SCHOOL' and f.sub_kind = 'MIDDLE' and st_dwithin(f.geom, l.geom, 1000)) as middle_count_1km,
    (select count(*) from area.facilities f where f.kind = 'SCHOOL' and f.sub_kind = 'HIGH' and st_dwithin(f.geom, l.geom, 1000)) as high_count_1km,
    (select min(st_distance(c.geom, l.geom)) from (select f.geom from area.facilities f where f.kind = 'PARK' order by f.geom <-> l.geom limit 5) c) as park_nearest_m,
    (select coalesce(sum((f.extra->>'area_m2')::numeric), 0) from area.facilities f where f.kind = 'PARK' and st_dwithin(f.geom, l.geom, 1000)) as park_area_1km_m2,
    (select min(st_distance(c.geom, l.geom)) from (select f.geom from area.facilities f where f.kind = 'HOSPITAL' and f.sub_kind = 'SECONDARY' order by f.geom <-> l.geom limit 5) c) as hospital_nearest_m,
    (select count(*) from area.facilities f where f.kind = 'HOSPITAL' and f.sub_kind = 'CLINIC' and st_dwithin(f.geom, l.geom, 500)) as clinic_count_500m,
    (select count(*) from area.stores s where s.industry_group = 'CONVENIENCE_STORE' and st_dwithin(s.geom, l.geom, 300)) as convenience_store_count_300m,
    (select min(st_distance(c.geom, l.geom)) from (select s.geom from area.stores s where s.industry_group = 'MART' order by s.geom <-> l.geom limit 5) c) as mart_nearest_m,
    (select count(*) from area.stores s where st_dwithin(s.geom, l.geom, 300)) as store_count_300m
  from area.notice_locations l join target_locations t using (location_id)
  where l.status in ('OK', 'APPROX')
) w
cross join lateral (values
  ('station_nearest_m', w.station_nearest_m), ('station_count_1km', w.station_count_1km),
  ('bus_stop_nearest_m', w.bus_stop_nearest_m), ('bus_stop_count_300m', w.bus_stop_count_300m),
  ('elementary_nearest_m', w.elementary_nearest_m), ('middle_count_1km', w.middle_count_1km), ('high_count_1km', w.high_count_1km),
  ('park_nearest_m', w.park_nearest_m), ('park_area_1km_m2', w.park_area_1km_m2),
  ('hospital_nearest_m', w.hospital_nearest_m), ('clinic_count_500m', w.clinic_count_500m),
  ('convenience_store_count_300m', w.convenience_store_count_300m), ('mart_nearest_m', w.mart_nearest_m),
  ('store_count_300m', w.store_count_300m)
) as x(metric, value)
where x.value is not null;   -- 시설이 아예 없으면(가장 가까운 것 없음) 그 지표는 빼고, 점수에서 0점 처리
