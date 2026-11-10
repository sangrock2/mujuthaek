truncate area.facilities;
insert into area.facilities (kind, sub_kind, name, geom, extra, source, source_key, data_date)
select k.kind,
       case k.kind
         when 'SCHOOL' then (array['ELEMENTARY','ELEMENTARY','ELEMENTARY','ELEMENTARY','ELEMENTARY','MIDDLE','MIDDLE','MIDDLE','HIGH','HIGH'])[1 + floor(random()*10)::int]
         when 'HOSPITAL' then case when g <= 1818 then 'SECONDARY' else 'CLINIC' end
         when 'PARK' then '근린공원'
         when 'SUBWAY_STATION' then '노선' || (1 + floor(random()*20)::int)
       end,
       k.kind || '-' || g,
       st_setsrid(st_makepoint(p.lng, p.lat), 4326)::geography,
       case when k.kind = 'PARK' then jsonb_build_object('area_m2', round(exp(8 + random()*3))) else '{}'::jsonb end,
       k.kind, k.kind || '-' || g, date '2026-10-21'
from (values ('SUBWAY_STATION', 1099), ('BUS_STOP', 227065), ('SCHOOL', 11500),
             ('PARK', 18342), ('HOSPITAL', 39962)) k(kind, n),
     lateral generate_series(1, k.n) g,
     lateral bench.rand_pt(g) p;
analyze area.facilities;
