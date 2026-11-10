-- 지원 비율을 소수로 (「연 3.5% 이자 지원」). 정수만 받으면 3.5를 3·4로 틀리게 바꾸거나 버려야 해요
alter table benefit.benefit_supports alter column rate_pct type numeric(5, 2);
