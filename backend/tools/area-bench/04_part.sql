drop table if exists area.stores_part cascade;
-- 파티션 테이블은 파티션 키가 들어간 고유 키만 만들 수 있어서 (load_scope, source_key)로
create table area.stores_part (
    id uuid not null default area.uuid_v7(), source_key text not null, load_scope text not null,
    name text not null, large_code text, large_name text, middle_code text, middle_name text,
    small_code text, small_name text, industry_group text not null, address text,
    geom geography(Point, 4326) not null, data_date date not null, updated_at timestamptz not null default now(),
    primary key (load_scope, id), unique (load_scope, source_key)
) partition by list (load_scope);
do $$ declare s text; begin
  for s in select distinct load_scope from area.stores loop
    execute format('create table area.%I partition of area.stores_part for values in (%L)', 'stores_p_' || md5(s), s);
  end loop; end $$;
