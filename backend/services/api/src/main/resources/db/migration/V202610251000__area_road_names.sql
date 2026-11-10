-- 3단계 사전 찾기의 오타 찾기용 도로명 목록 (시군구별 서로 다른 도로명). 도로명주소(address_points) 적재 때 그 시도 범위를 다시 채워요.
-- 전국 640만 줄 사전 전체에 trigram 인덱스를 거는 대신 도로명만 모은 작은 표에 걸어요 (100만 줄 사전 → 1,013줄 336kB).
-- pg_trgm은 PostGIS처럼 public에 둬요. Flyway는 common을 맨 앞에 두고 돌아서, 그냥 만들면 앱 연결(public)에서 % 연산자를 못 찾아요.
create extension if not exists pg_trgm with schema public;

create table area.road_names (
    sigungu_code text not null,             -- 시군구 5자리 (address_points.sigungu_code)
    road_name    text not null,
    primary key (sigungu_code, road_name)
);
create index road_names_trgm_gix on area.road_names using gin (road_name public.gin_trgm_ops);
