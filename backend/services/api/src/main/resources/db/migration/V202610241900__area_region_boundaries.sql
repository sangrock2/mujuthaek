-- 좌표 찾기(3단계)의 경계 검사용 시군구·법정읍면동 경계.
-- 원천: 구역의 도형(SHP, UTM-K EPSG:5179) → collector가 CSV(code, name, wkt)로 바꿔 올림 → 적재할 때 경위도로 바꿔요.

create table area.region_boundaries (
    level      text        not null check (level in ('SIG', 'EMD')),
    code       text        not null,                 -- SIG 5자리, EMD 8자리 (법정동코드 10자리의 앞 8자리와 비교)
    name       text        not null,
    geom       geography(MultiPolygon, 4326) not null,
    data_date  date        not null,
    updated_at timestamptz not null default now(),
    primary key (level, code),
    check (code ~ case level when 'SIG' then '^[0-9]{5}$' else '^[0-9]{8}$' end)
);
create index region_boundaries_gix on area.region_boundaries using gist (geom);
comment on column area.region_boundaries.data_date is '이 줄이 마지막으로 바뀐 적재의 원천 기준일 (원천 파일 기준일은 area.load_runs.data_date)';

-- UTM-K WKT → 경위도 MultiPolygon. 잘못된 도형은 고치고(make_valid), 고쳐서 생긴 선·점은 버려요(면만).
-- 읽을 수 없는 WKT·면이 남지 않는 도형은 null — 적재기가 그 줄만 BAD_GEOMETRY로 거절해요(파일 전체를 실패시키지 않게).
create or replace function area.boundary_from_utmk_wkt(wkt text) returns geometry
language plpgsql immutable parallel safe as $$
declare g geometry;
begin
  g := st_multi(st_collectionextract(st_makevalid(st_transform(st_geomfromtext(wkt, 5179), 4326)), 3));
  if g is null or st_isempty(g) then
    return null;
  end if;
  return g;
exception when others then
  return null;
end $$;
