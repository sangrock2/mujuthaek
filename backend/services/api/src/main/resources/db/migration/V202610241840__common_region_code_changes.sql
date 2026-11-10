-- 폐지된 법정동코드(10자리) → 지금 코드. 2026 행정구역 개편의 시군구 계보 안에서만 계산해서 채워요(RegionLoader).
-- 한 예전 코드가 여러 새 코드로 갈라질 수 있어요: 인천 중구 2811000000 → 제물포구 2812500000, 영종구 2815500000.
-- 동·리는 동 이름이 하나만 맞을 때만 있어요. 이 표에 없는 폐지 코드는 대응을 모르는 코드예요.
create table common.region_code_changes (
    old_code   text not null check (old_code ~ '^[0-9]{10}$'),
    new_code   text not null check (new_code ~ '^[0-9]{10}$'),
    base_date  date not null,                    -- 계산에 쓴 법정동코드표 기준일
    primary key (old_code, new_code)
);
