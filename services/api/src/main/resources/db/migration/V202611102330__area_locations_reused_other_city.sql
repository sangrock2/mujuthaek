-- 다른 도시 공고의 좌표를 그대로 다시 쓴 위치 줄을 지워요 (2026-11-10 코드 검토: 좌표 재사용을 주소 글자만으로 해 「중앙로 7」 같은 주소가 다른 도시
-- 좌표를 받았음. 이제는 받은 법정동코드도 같아야 다시 써요). 표시: 좌표를 찾았다(OK)는데 받은 법정동과 찾은 법정동의 시군구가 다르고 경계 밖 표시도 없음.
-- 받은 코드가 시도 전체이거나, 일반구가 있는 시와 그 구(수원시 41110 · 장안구 41111)이면 정상이라 빼요(목록은 CityDistricts와 같음).
-- 지표·생활 점수는 cascade로 함께 지워져요. 배포 뒤 위치 보충 발행(--notice.backfill=locations)을 한 번 돌리면 이 위치들을 새로 찾고 점수를 다시 보내요
delete from area.notice_locations
 where status = 'OK'
   and not region_mismatch
   and bjd_code_given is not null
   and bjd_code_found is not null
   and substr(bjd_code_given, 3, 3) <> '000'
   and left(bjd_code_found, 5) <> left(bjd_code_given, 5)
   and not (left(bjd_code_given, 5) in ('41110', '41130', '41170', '41190', '41270', '41280', '41460', '41590', '43110',
                                        '44130', '47110', '48120', '52110')
            and left(bjd_code_found, 4) = left(bjd_code_given, 4));
