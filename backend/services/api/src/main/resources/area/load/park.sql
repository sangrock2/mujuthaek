-- 공원: 전국도시공원정보 표준데이터 (CP949). 면적(㎡)은 extra.area_m2에 숫자로.
insert into stage_norm (line_no, source_key, name, sub_kind, address, lat_txt, lng_txt, extra)
select line_no,
       "관리번호",
       "공원명",
       nullif(trim("공원구분"), ''),
       coalesce(nullif(trim("소재지도로명주소"), ''), nullif(trim("소재지지번주소"), '')),
       "위도",
       "경도",
       jsonb_strip_nulls(jsonb_build_object(
         'area_m2', case when replace(trim("공원면적"), ',', '') ~ '^[0-9]+(\.[0-9]+)?$'
                         then replace(trim("공원면적"), ',', '')::numeric end))
from stage_raw;
