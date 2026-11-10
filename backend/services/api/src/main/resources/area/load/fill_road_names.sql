-- 이 시도 범위의 도로명 목록을 사전(address_points)에서 다시 채워요. 자리표시: 1 load_scope
insert into area.road_names (sigungu_code, road_name)
select distinct sigungu_code, road_name from area.address_points where load_scope = ?
on conflict do nothing;
