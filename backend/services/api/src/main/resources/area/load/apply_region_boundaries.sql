-- 쓰는 줄을 area.region_boundaries에 반영. 이름이나 도형이 바뀐 줄만 고치고, 새 줄은 넣어요. 자리표시: 1 level, 2 data_date
with upserted as (
  insert into area.region_boundaries as t (level, code, name, geom, data_date, updated_at)
  select ?, s.source_key, s.name, s.geom::geography, ?, now()
  from stage_norm s
  where s.skip_reason is null and s.reject_reason is null
  on conflict (level, code) do update
    set name = excluded.name, geom = excluded.geom, data_date = excluded.data_date, updated_at = now()
    where (t.name, st_asbinary(t.geom)) is distinct from (excluded.name, st_asbinary(excluded.geom))
  returning (xmax = 0) as inserted
)
select count(*) filter (where inserted) as inserted,
       count(*) filter (where not inserted) as updated
from upserted;
