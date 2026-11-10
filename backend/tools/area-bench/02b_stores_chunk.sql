insert into area.stores (source_key, load_scope, name, large_code, small_code, industry_group, geom, data_date)
select 'S' || g, p.scope, '가게' || g, m.large, m.small, m.grp,
       st_setsrid(st_makepoint(p.lng, p.lat), 4326)::geography, date '2026-06-30'
from generate_series(:from, :to) g,
     lateral bench.rand_pt(g) p,
     lateral (select random() + 0 * g as r offset 0) rr,
     lateral (select * from bench.mix where cum >= rr.r order by cum limit 1) m;
