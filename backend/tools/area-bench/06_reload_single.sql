\timing on
begin;
with up as (
  insert into area.stores as t (source_key, load_scope, name, large_code, small_code, industry_group, geom, data_date)
  select source_key, load_scope, name, large_code, small_code, industry_group, geom, date '2026-09-30' from bench.stage_seoul
  on conflict (source_key) do update set name = excluded.name, small_code = excluded.small_code,
       industry_group = excluded.industry_group, geom = excluded.geom, data_date = excluded.data_date, updated_at = now()
  where (t.name, t.small_code, t.industry_group, st_asbinary(t.geom)) is distinct from
        (excluded.name, excluded.small_code, excluded.industry_group, st_asbinary(excluded.geom))
  returning (xmax = 0) as ins)
select count(*) filter (where ins) as inserted, count(*) filter (where not ins) as updated from up;
delete from area.stores t where t.load_scope = '서울'
  and not exists (select 1 from bench.stage_seoul s where s.source_key = t.source_key);
update area.stores set data_date = date '2026-09-30' where load_scope = '서울' and data_date <> date '2026-09-30';
rollback;  -- 시간만 재고 되돌려요 (실제 데이터를 바꾸지 않게)
