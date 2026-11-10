-- 실제 데이터 모드: 공고 단지가 아직 없으니(3단계 전) 실제 버스정류장 3,000곳을 단지 위치로 써요.
-- 정류장은 사람이 사는 곳에 몰려 있어서 공고 단지 분포와 비슷해요. 같은 결과가 나오게 시드를 고정해요.
create schema if not exists bench;
drop table if exists bench.sites;
select setseed(0.42);
create table bench.sites as
select row_number() over ()::int as id, geom
from (select geom from area.facilities where kind = 'BUS_STOP' order by random() limit 3000) s;
alter table bench.sites add primary key (id);
create index on bench.sites using gist (geom);
analyze bench.sites;
