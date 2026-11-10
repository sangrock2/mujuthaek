-- 4단계 세권 계산용 종류별 부분 공간 인덱스.
-- 조건은 계산 SQL(resources/area/calc/metrics.sql)의 where와 글자까지 같아야 써져요. 한쪽을 고치면 다른 쪽도 같이 고쳐요.
create index facilities_subway_gix  on area.facilities using gist (geom) where kind = 'SUBWAY_STATION';
create index facilities_bus_gix     on area.facilities using gist (geom) where kind = 'BUS_STOP';
create index facilities_school_gix  on area.facilities using gist (geom) where kind = 'SCHOOL';
create index facilities_park_gix    on area.facilities using gist (geom) where kind = 'PARK';
create index facilities_hosp2_gix   on area.facilities using gist (geom) where kind = 'HOSPITAL' and sub_kind = 'SECONDARY';
create index facilities_clinic_gix  on area.facilities using gist (geom) where kind = 'HOSPITAL' and sub_kind = 'CLINIC';
create index stores_conv_gix        on area.stores using gist (geom) where industry_group = 'CONVENIENCE_STORE';
create index stores_mart_gix        on area.stores using gist (geom) where industry_group = 'MART';
