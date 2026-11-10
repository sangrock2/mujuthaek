-- 병원: 심평원 1.병원정보서비스 (CP949). 좌표(X) = 경도, 좌표(Y) = 위도.
-- 2차 이상(상급종합 01, 종합병원 11, 병원 21)과 동네 의원(의원 31, 보건소 71, 보건의료원 75)만 써요.
insert into stage_norm (line_no, skip_reason, source_key, name, sub_kind, address, lat_txt, lng_txt, extra)
select line_no,
       case when trim("종별코드") not in ('01', '11', '21', '31', '71', '75') then 'OTHER_TYPE' end,
       "암호화요양기호",
       "요양기관명",
       case
         when trim("종별코드") in ('01', '11', '21') then 'SECONDARY'
         when trim("종별코드") in ('31', '71', '75') then 'CLINIC'
       end,
       nullif(trim("주소"), ''),
       "좌표(Y)",
       "좌표(X)",
       jsonb_strip_nulls(jsonb_build_object('type_code', trim("종별코드"), 'type_name', "종별코드명"))
from stage_raw;
