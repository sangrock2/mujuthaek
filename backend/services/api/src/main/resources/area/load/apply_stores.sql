-- 쓰는 줄을 area.stores에 반영. 업종 묶음: 소분류 코드가 규칙 접두어로 시작하는 첫 규칙, 없으면 대분류 코드.
-- 자리표시: 1 load_scope, 2 data_date
with grouped as (
  select s.*,
         coalesce((select r.industry_group from area.industry_group_rules r
                   where s.small_code like r.code_prefix || '%'
                   order by r.priority limit 1),
                  s.large_code, 'UNKNOWN') as industry_group
  from stage_norm s
  where s.skip_reason is null and s.reject_reason is null
),
upserted as (
  insert into area.stores as t (source_key, load_scope, name, large_code, large_name, middle_code, middle_name,
                                small_code, small_name, industry_group, address, geom, data_date, updated_at)
  select g.source_key, ?, g.name, g.large_code, g.large_name, g.middle_code, g.middle_name,
         g.small_code, g.small_name, g.industry_group, g.address,
         st_setsrid(st_makepoint(g.lng, g.lat), 4326)::geography, ?, now()
  from grouped g
  on conflict (source_key) do update
    set load_scope = excluded.load_scope, name = excluded.name, large_code = excluded.large_code, large_name = excluded.large_name,
        middle_code = excluded.middle_code, middle_name = excluded.middle_name,
        small_code = excluded.small_code, small_name = excluded.small_name,
        industry_group = excluded.industry_group, address = excluded.address, geom = excluded.geom,
        data_date = excluded.data_date, updated_at = now()
    where (t.load_scope, t.name, t.small_code, t.industry_group, t.address, st_asbinary(t.geom))
          is distinct from
          (excluded.load_scope, excluded.name, excluded.small_code, excluded.industry_group, excluded.address, st_asbinary(excluded.geom))
  returning (xmax = 0) as inserted
)
select count(*) filter (where inserted) as inserted,
       count(*) filter (where not inserted) as updated
from upserted;
