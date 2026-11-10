-- 오타 찾기용 도로명 목록을 이 시도 범위만 지워요 (도로명주소 적재 뒤 fill_road_names.sql로 다시 채움). 자리표시: 1 load_scope
-- 시군구 코드 앞 두 자리가 시도 코드예요. 남은 옛 이름이 있어도 사전에 그 주소가 없으면 찾기 결과가 없어서 틀린 값이 되지 않아요.
delete from area.road_names where left(sigungu_code, 2) = ?;
