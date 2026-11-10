-- 시군구 경계 CSV(code, name, wkt). collector가 구역의 도형 SHP에서 바꾼 파일이고 좌표는 UTM-K(EPSG:5179)예요.
-- 도형은 여기서 경위도로 바꾸고(area.boundary_from_utmk_wkt), 공통 검사(validate.sql)가 한국 범위를 보도록 도형 안의 한 점을 위도·경도로 넣어요.
insert into stage_norm (line_no, reject_reason, source_key, name, lat_txt, lng_txt, geom)
select r.line_no,
       case when trim(r.code) !~ '^[0-9]{5}$' then 'BAD_CODE'
            when g.geom is null then 'BAD_GEOMETRY' end,
       trim(r.code), trim(r.name),
       st_y(st_pointonsurface(g.geom))::text, st_x(st_pointonsurface(g.geom))::text, g.geom
from stage_raw r
cross join lateral (select area.boundary_from_utmk_wkt(r.wkt) as geom) g;
