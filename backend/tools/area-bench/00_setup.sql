create schema if not exists bench;
drop table if exists bench.cities;
create table bench.cities (name text, scope text, lat float8, lng float8, w float8, sd float8, cum float8);
insert into bench.cities (name, scope, lat, lng, w, sd) values
 ('서울','서울',37.5665,126.9780,0.20,0.08), ('수원','경기',37.2636,127.0286,0.08,0.15),
 ('고양','경기',37.6584,126.8320,0.05,0.12), ('성남','경기',37.3500,127.1500,0.06,0.10),
 ('인천','인천',37.4563,126.7052,0.06,0.08), ('부산','부산',35.1796,129.0756,0.07,0.07),
 ('대구','대구',35.8714,128.6014,0.05,0.07), ('광주','전남광주',35.1595,126.8526,0.03,0.06),
 ('대전','대전',36.3504,127.3845,0.03,0.06), ('울산','울산',35.5384,129.3114,0.02,0.06),
 ('창원','경남',35.2280,128.6811,0.03,0.08), ('청주','충북',36.6424,127.4890,0.02,0.07),
 ('전주','전북',35.8242,127.1480,0.02,0.06), ('천안','충남',36.8151,127.1139,0.02,0.07),
 ('제주','제주',33.4996,126.5312,0.02,0.10), ('포항','경북',36.0190,129.3435,0.01,0.06),
 ('춘천','강원',37.8813,127.7298,0.01,0.06), ('세종','세종',36.4800,127.2890,0.01,0.04),
 ('지방','지방',0,0,0.21,0);
update bench.cities c set cum = s.cum from (select name, sum(w) over (order by name) / sum(w) over () as cum from bench.cities) s where s.name = c.name;

-- 도시 하나를 고르고 정규분포로 흩뿌린 점 (지방은 남한 상자 안에 고르게)
create or replace function bench.rand_pt(seed int, out lat float8, out lng float8, out scope text) language plpgsql volatile as $$
declare r float8 := random(); c record; z1 float8; z2 float8;
begin
  select * into c from bench.cities where cum >= r order by cum limit 1;
  if c.name = '지방' then
    lat := 34.6 + random() * 3.4; lng := 126.4 + random() * 2.9; scope := '지방'; return;
  end if;
  z1 := sqrt(-2 * ln(greatest(random(), 1e-12))) * cos(2 * pi() * random());
  z2 := sqrt(-2 * ln(greatest(random(), 1e-12))) * cos(2 * pi() * random());
  lat := c.lat + z1 * c.sd; lng := c.lng + z2 * c.sd * 1.2; scope := c.scope;
end $$;

-- 공고 단지 3,000곳
drop table if exists bench.sites;
create table bench.sites (id int primary key, geom geography(Point, 4326) not null);
insert into bench.sites select g, st_setsrid(st_makepoint(p.lng, p.lat), 4326)::geography
from generate_series(1, 3000) g, lateral bench.rand_pt(g) p;
create index on bench.sites using gist (geom);
