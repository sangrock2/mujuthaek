-- 쓰는 줄을 area.address_points에 반영. 바뀐 줄만 고치고, 새 줄은 넣어요. 자리표시: 1 load_scope, 2 data_date
with upserted as (
  insert into area.address_points as t (address_id, load_scope, bjd_code, sigungu_code, emd,
                                        road_code, road_name, underground, bldg_main, bldg_sub, zip_code, geom, data_date, updated_at)
  select s.source_key, ?, s.bjd_code, left(s.bjd_code, 5), s.emd,
         s.road_code, s.road_name, s.underground::smallint, s.bldg_main::int, s.bldg_sub::int, s.zip_code,
         st_setsrid(st_makepoint(s.lng, s.lat), 4326)::geography, ?, now()
  from stage_norm s
  where s.skip_reason is null and s.reject_reason is null
  on conflict (address_id) do update
    set load_scope = excluded.load_scope, bjd_code = excluded.bjd_code, sigungu_code = excluded.sigungu_code,
        emd = excluded.emd,
        road_code = excluded.road_code, road_name = excluded.road_name, underground = excluded.underground,
        bldg_main = excluded.bldg_main, bldg_sub = excluded.bldg_sub, zip_code = excluded.zip_code,
        geom = excluded.geom, data_date = excluded.data_date, updated_at = now()
    where (t.load_scope, t.bjd_code, t.emd, t.road_code, t.road_name, t.underground, t.bldg_main, t.bldg_sub, t.zip_code,
           st_asbinary(t.geom))
          is distinct from
          (excluded.load_scope, excluded.bjd_code, excluded.emd, excluded.road_code, excluded.road_name, excluded.underground,
           excluded.bldg_main, excluded.bldg_sub, excluded.zip_code, st_asbinary(excluded.geom))
  returning (xmax = 0) as inserted
)
select count(*) filter (where inserted) as inserted,
       count(*) filter (where not inserted) as updated
from upserted;
