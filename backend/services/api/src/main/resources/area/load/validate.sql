-- 모든 원천 공통 검사. 쓰는 줄(skip_reason이 비어 있음)만 봐요.
-- 순서: 키·이름 → 좌표 숫자 → 위도·경도 뒤바뀜 고치기 → 한국 범위 → 키 중복(앞 줄을 남김).
update stage_norm
set lat = case when trim(lat_txt) ~ '^-?[0-9]+(\.[0-9]+)?$' then trim(lat_txt)::double precision end,
    lng = case when trim(lng_txt) ~ '^-?[0-9]+(\.[0-9]+)?$' then trim(lng_txt)::double precision end,
    source_key = nullif(trim(source_key), ''),
    name = nullif(trim(name), '')
where skip_reason is null;

update stage_norm set reject_reason = 'NO_KEY'
where skip_reason is null and reject_reason is null and source_key is null;

update stage_norm set reject_reason = 'NO_NAME'
where skip_reason is null and reject_reason is null and name is null;

update stage_norm set reject_reason = 'NO_COORD'
where skip_reason is null and reject_reason is null
  and (lat is null or lng is null or lat = 0 or lng = 0);

update stage_norm set lat = lng, lng = lat, fixed = true
where skip_reason is null and reject_reason is null
  and lat between 124 and 132 and lng between 33 and 39;

update stage_norm set reject_reason = 'OUT_OF_RANGE'
where skip_reason is null and reject_reason is null
  and not (lat between 33 and 39 and lng between 124 and 132);

update stage_norm s set reject_reason = 'DUPLICATE_KEY'
from (select line_no, row_number() over (partition by source_key order by line_no) as rn
      from stage_norm where skip_reason is null and reject_reason is null) d
where s.line_no = d.line_no and d.rn > 1;
