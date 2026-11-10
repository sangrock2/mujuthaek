-- 관심 정책에 창업지원 사업(STARTUP_SUPPORT)을 더해요. 창업지원 사업·사업공간 모집은 benefit이 아니라 notice.policy_judgments에 있고
-- target_id는 정책 ID(rawPolicyId)예요. 사업공간 모집은 그동안 benefit에서 찾아 저장되지 않았어서 바꿀 줄이 없어요.
alter table account.favorites drop constraint favorites_target_type_check;
alter table account.favorites add constraint favorites_target_type_check
    check (target_type in ('NOTICE', 'BENEFIT', 'STARTUP_SUPPORT', 'SPACE_RECRUITMENT'));
