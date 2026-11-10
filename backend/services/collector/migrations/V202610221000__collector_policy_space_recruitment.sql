-- 정책 분류에 사업공간 모집(SPACE_RECRUITMENT)을 더해요 (2026-10-22 결정).
-- 원본은 raw_policies 한 테이블에 두고 field 칸으로 나눠요: 지원 정책(BENEFIT·STARTUP_SUPPORT) / 사업공간 모집(SPACE_RECRUITMENT).
-- 분류는 목록 단계(1차 거름)에서 정해 저장하고, 이벤트 raw.policy.collected의 field로 나가요. 추출 결과도 분류마다 다른 테이블에 저장해요.

comment on column raw_policies.field is
    'BENEFIT 주거·이주 혜택, STARTUP_SUPPORT 창업 지원금·정책자금·임대료 지원, SPACE_RECRUITMENT 사업공간 모집 (입주·입점 모집, 임대 공급)';

-- 이미 저장한 창업지원 중 사업공간 모집을 옮겨요. 기준은 sources/policy/base.py SPACE_RECRUIT와 같아요.
-- 이미 보낸 이벤트는 field가 STARTUP_SUPPORT 그대로예요. extraction이 아직 정책 큐(mujuthaek.raw.policy)를 꺼내 가지 않아서,
-- 정책 추출 규칙을 붙이기 전에 그 큐를 비우고 이 테이블 기준으로 다시 보내면 돼요 (내용이 같으면 새 버전·이벤트를 만들지 않아요).
update raw_policies
set field = 'SPACE_RECRUITMENT', updated_at = now()
where field = 'STARTUP_SUPPORT'
  and title ~ '입주(기업|자|팀|스타트업|기관)?.{0,6}모집|입점.{0,6}모집|임대\s*공급|입주.{0,4}공고|멤버십.{0,4}모집|입주ㆍ';

create index raw_policies_field_idx on raw_policies (field, status);
