\timing on
create table area.stores_seoul_new (like area.stores_part including defaults);
insert into area.stores_seoul_new (source_key, load_scope, name, large_code, small_code, industry_group, geom, data_date)
select source_key, load_scope, name, large_code, small_code, industry_group, geom, date '2026-09-30' from bench.stage_seoul;
alter table area.stores_seoul_new add primary key (load_scope, id);
alter table area.stores_seoul_new add unique (load_scope, source_key);
create index on area.stores_seoul_new using gist (geom);
create index on area.stores_seoul_new (industry_group);
create index on area.stores_seoul_new using gist (geom) where industry_group='CONVENIENCE_STORE';
create index on area.stores_seoul_new using gist (geom) where industry_group='MART';
alter table area.stores_seoul_new add constraint seoul_chk check (load_scope = '서울');
analyze area.stores_seoul_new;
begin;
alter table area.stores_part detach partition __OLD__;
alter table area.stores_part attach partition area.stores_seoul_new for values in ('서울');
commit;
drop table __OLD__;
