-- area 6·7단계: 위치마다 항목 점수(location_scores)와 점수 규칙(score_rules·score_weights·piecewise).
-- 규칙은 버전으로 쌓아요. 구간을 고치면 이 파일을 고치지 않고 새 마이그레이션으로 새 버전(2026.2 …)을 넣고, 쓰는 버전은 설정값이에요.

-- 6·7단계 결과: 위치마다 항목 점수 0~100
create table area.location_scores (
    location_id   uuid        not null references area.notice_locations (location_id) on delete cascade,
    score_kind    text        not null check (score_kind in ('LIFE', 'COMMERCIAL')),
    category      text        not null,
    score         smallint    not null check (score between 0 and 100),
    score_version text        not null,
    calculated_at timestamptz not null default now(),
    primary key (location_id, score_kind, category)
);

-- 점수 규칙: 지표 하나를 0~100으로. 점(xs, ys)을 직선으로 잇고, 양끝 밖은 끝 값.
create table area.score_rules (
    score_version text      not null,
    metric        text      not null,
    xs            numeric[] not null,
    ys            numeric[] not null,
    primary key (score_version, metric),
    check (cardinality(xs) = cardinality(ys) and cardinality(xs) >= 2)
);

-- 항목 점수 = 지표 점수의 가중 합 (가중치 합 1)
create table area.score_weights (
    score_version text    not null,
    score_kind    text    not null,
    category      text    not null,
    metric        text    not null,
    weight        numeric not null check (weight > 0 and weight <= 1),
    primary key (score_version, score_kind, category, metric)
);

-- 직선 잇기 (xs는 오름차순). 자바 쪽 Piecewise와 같은 계산이에요.
create or replace function area.piecewise(x numeric, xs numeric[], ys numeric[]) returns numeric
language plpgsql immutable strict parallel safe as $$
declare i int; n int := cardinality(xs);
begin
  if x <= xs[1] then return ys[1]; end if;
  if x >= xs[n] then return ys[n]; end if;
  for i in 2..n loop
    if x <= xs[i] then
      return ys[i-1] + (ys[i] - ys[i-1]) * (x - xs[i-1]) / (xs[i] - xs[i-1]);
    end if;
  end loop;
  return ys[n];
end $$;

-- 규칙 2026.1 (설계 문서 6단계 초안 숫자 그대로. 병원은 2차 이상 거리 0.6 + 동네 의원 수 0.4)
insert into area.score_rules values
 ('2026.1','station_nearest_m',            '{500,1000,2000,3000}', '{100,70,40,0}'),
 ('2026.1','bus_stop_count_300m',          '{0,5}',                '{0,100}'),
 ('2026.1','elementary_nearest_m',         '{300,600,1000,2000}',  '{100,80,60,0}'),
 ('2026.1','middle_count_1km',             '{0,2}',                '{0,100}'),
 ('2026.1','high_count_1km',               '{0,2}',                '{0,100}'),
 ('2026.1','park_nearest_m',               '{300,500,1000,2000}',  '{100,80,60,0}'),
 ('2026.1','park_area_1km_m2',             '{0,100000}',           '{0,100}'),
 ('2026.1','convenience_store_count_300m', '{0,5}',                '{0,100}'),
 ('2026.1','mart_nearest_m',               '{500,1000,3000}',      '{100,70,0}'),
 ('2026.1','hospital_nearest_m',           '{1000,3000,6000}',     '{100,60,0}'),
 ('2026.1','clinic_count_500m',            '{0,5}',                '{0,100}'),
 ('2026.1','work_distance_m',              '{3000,7000,15000,25000,40000}', '{100,80,60,30,0}');
insert into area.score_weights values
 ('2026.1','LIFE','TRANSIT','station_nearest_m',0.7), ('2026.1','LIFE','TRANSIT','bus_stop_count_300m',0.3),
 ('2026.1','LIFE','SCHOOL','elementary_nearest_m',0.6), ('2026.1','LIFE','SCHOOL','middle_count_1km',0.2), ('2026.1','LIFE','SCHOOL','high_count_1km',0.2),
 ('2026.1','LIFE','PARK','park_nearest_m',0.7), ('2026.1','LIFE','PARK','park_area_1km_m2',0.3),
 ('2026.1','LIFE','CONVENIENCE','convenience_store_count_300m',0.6), ('2026.1','LIFE','CONVENIENCE','mart_nearest_m',0.4),
 ('2026.1','LIFE','HOSPITAL','hospital_nearest_m',0.6), ('2026.1','LIFE','HOSPITAL','clinic_count_500m',0.4);
