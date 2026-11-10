-- 도로명주소 출입구 정보 (머리줄 없는 | 구분 19칸, CP949). 칸 이름은 c1~c19.
-- 좌표(c18 X, c19 Y)는 UTM-K(EPSG:5179)라 여기서 경위도로 바꿔요. 그다음은 공통 검사(validate.sql)가 그대로 봐요.
-- 지하여부(c9)는 0~3을 그대로 받아요. 1(지하)만 주소 글자에 "지하"를 붙여요 (3은 2026-10 원천에서 경남 통영 섬 지역 52줄).
insert into stage_norm (line_no, reject_reason, source_key, name, address, lat_txt, lng_txt,
                        bjd_code, sido, sigungu, emd, ri, road_code, road_name,
                        underground, bldg_main, bldg_sub, zip_code)
select r.line_no,
       case when not (trim(r.c9) ~ '^[0-3]$' and trim(r.c10) ~ '^[0-9]+$' and trim(r.c11) ~ '^[0-9]+$') then 'BAD_NUMBER' end,
       trim(r.c1),
       trim(r.c8) || ' ' || case when trim(r.c9) = '1' then '지하 ' else '' end || ltrim(trim(r.c10), '0')
         || case when ltrim(trim(r.c11), '0') <> '' then '-' || ltrim(trim(r.c11), '0') else '' end,
       concat_ws(' ', nullif(trim(r.c3), ''), nullif(trim(r.c4), ''), nullif(trim(r.c8), ''),
                 case when trim(r.c9) = '1' then '지하' end,
                 ltrim(trim(r.c10), '0') || case when ltrim(trim(r.c11), '0') <> '' then '-' || ltrim(trim(r.c11), '0') else '' end),
       st_y(p.g)::text, st_x(p.g)::text,
       trim(r.c2), trim(r.c3), trim(r.c4), nullif(trim(r.c5), ''), nullif(trim(r.c6), ''), trim(r.c7), trim(r.c8),
       trim(r.c9), trim(r.c10), trim(r.c11), nullif(trim(r.c12), '')
from stage_raw r
cross join lateral (
  select case when trim(r.c18) ~ '^-?[0-9]+(\.[0-9]+)?$' and trim(r.c19) ~ '^-?[0-9]+(\.[0-9]+)?$'
              then st_transform(st_setsrid(st_makepoint(trim(r.c18)::float8, trim(r.c19)::float8), 5179), 4326) end as g
) p;
