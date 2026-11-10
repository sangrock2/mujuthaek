-- 리뷰 2026-10-22: 정책 판정 틀 지원 지역은 시군구 5자리만(계약 검사에만 기대지 않게)
alter table notice.policy_judgments
    add constraint policy_judgments_region_codes_5digit
        check (array_to_string(region_codes, ',') ~ '^([0-9]{5}(,[0-9]{5})*)?$');
