-- 지하철역: 철도산업정보센터 "전체_도시철도역사정보" 엑셀을 collector가 UTF-8 CSV로 바꿔 올린 파일.
-- 환승역은 노선마다 줄이 따로라 역번호(노선별)로 넣고, 같은 역을 묶는 건 세권 계산(4단계)에서 해요.
insert into stage_norm (line_no, source_key, name, sub_kind, address, lat_txt, lng_txt, extra)
select line_no,
       "역번호",
       "역사명",
       "노선명",
       nullif(trim("역사도로명주소"), ''),
       "역위도",
       "역경도",
       jsonb_strip_nulls(jsonb_build_object('line_code', "노선번호", 'transfer', "환승역구분", 'operator', "운영기관명"))
from stage_raw;
