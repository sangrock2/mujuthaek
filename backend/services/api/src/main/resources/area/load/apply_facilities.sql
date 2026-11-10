-- 쓰는 줄을 area.facilities에 반영. 바뀐 줄만 고치고, 새 줄은 넣어요.
-- 자리표시: 1 kind, 2 source, 3 data_date
with upserted as (
  insert into area.facilities as f (kind, sub_kind, name, address, geom, extra, source, source_key, data_date, updated_at)
  select ?, s.sub_kind, s.name, s.address,
         st_setsrid(st_makepoint(s.lng, s.lat), 4326)::geography,
         coalesce(s.extra, '{}'::jsonb), ?, s.source_key, ?, now()
  from stage_norm s
  where s.skip_reason is null and s.reject_reason is null
  on conflict (source, source_key) do update
    set kind = excluded.kind, sub_kind = excluded.sub_kind, name = excluded.name,
        address = excluded.address, geom = excluded.geom, extra = excluded.extra,
        data_date = excluded.data_date, updated_at = now()
    where (f.kind, f.sub_kind, f.name, f.address, st_asbinary(f.geom), f.extra)
          is distinct from
          (excluded.kind, excluded.sub_kind, excluded.name, excluded.address, st_asbinary(excluded.geom), excluded.extra)
  returning (xmax = 0) as inserted
)
select count(*) filter (where inserted) as inserted,
       count(*) filter (where not inserted) as updated
from upserted;
