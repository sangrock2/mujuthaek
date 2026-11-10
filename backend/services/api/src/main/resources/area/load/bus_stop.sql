-- 버스정류장: 국토교통부 전국 버스정류장 위치정보 (CP949). 좌표는 WGS84.
insert into stage_norm (line_no, source_key, name, sub_kind, address, lat_txt, lng_txt, extra)
select line_no,
       "정류장번호",
       "정류장명",
       null,
       null,
       "위도",
       "경도",
       jsonb_strip_nulls(jsonb_build_object('city_code', "도시코드", 'city', "도시명"))
from stage_raw;
