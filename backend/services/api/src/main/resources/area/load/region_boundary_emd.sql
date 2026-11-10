-- 법정읍면동 경계 CSV(code, name, wkt). 코드는 8자리(시군구 5 + 읍면동 3)이고 나머지는 시군구(region_boundary_sig.sql)와 같아요.
insert into stage_norm (line_no, reject_reason, source_key, name, lat_txt, lng_txt, geom)
select r.line_no,
       case when trim(r.code) !~ '^[0-9]{8}$' then 'BAD_CODE'
            when g.geom is null then 'BAD_GEOMETRY' end,
       trim(r.code), trim(r.name),
       st_y(st_pointonsurface(g.geom))::text, st_x(st_pointonsurface(g.geom))::text, g.geom
from stage_raw r
cross join lateral (select area.boundary_from_utmk_wkt(r.wkt) as geom) g;
