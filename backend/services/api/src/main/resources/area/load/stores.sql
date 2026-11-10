-- 상가(상권)정보: 소상공인시장진흥공단 시도별 파일 (UTF-8). 시도 파일 하나가 적재 한 번이에요.
-- 업종 묶음은 적용 단계(apply_stores.sql)에서 area.industry_group_rules로 정해요.
insert into stage_norm (line_no, source_key, name, address, lat_txt, lng_txt,
                        large_code, large_name, middle_code, middle_name, small_code, small_name)
select line_no,
       "상가업소번호",
       concat_ws(' ', nullif(trim("상호명"), ''), nullif(trim("지점명"), '')),
       nullif(trim("도로명주소"), ''),
       "위도",
       "경도",
       nullif(trim("상권업종대분류코드"), ''), "상권업종대분류명",
       nullif(trim("상권업종중분류코드"), ''), "상권업종중분류명",
       nullif(trim("상권업종소분류코드"), ''), "상권업종소분류명"
from stage_raw;
