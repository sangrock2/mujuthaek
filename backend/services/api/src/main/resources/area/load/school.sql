-- 학교: 전국초중등학교위치 표준데이터 (CP949). 운영 중인 초·중·고만 써요.
insert into stage_norm (line_no, skip_reason, source_key, name, sub_kind, address, lat_txt, lng_txt, extra)
select line_no,
       case
         when trim("운영상태") is distinct from '운영' then 'NOT_OPERATING'
         when trim("학교급구분") not in ('초등학교', '중학교', '고등학교') then 'OTHER_SCHOOL_TYPE'
       end,
       "학교ID",
       "학교명",
       case trim("학교급구분")
         when '초등학교' then 'ELEMENTARY'
         when '중학교' then 'MIDDLE'
         when '고등학교' then 'HIGH'
       end,
       coalesce(nullif(trim("소재지도로명주소"), ''), nullif(trim("소재지지번주소"), '')),
       "위도",
       "경도",
       jsonb_strip_nulls(jsonb_build_object('founding', "설립형태", 'branch', "본교분교구분"))
from stage_raw;
