-- 보증금 대출 상품 (준비할 돈 계산). 한도·조건은 바뀌어서 관리자가 넣어요 (관리자 기준값 화면 LOAN_PRODUCTS).
create table eligibility.loan_products (
    code                  text        primary key,          -- YOUTH_BEOTIMMOK …
    name                  text        not null,             -- 청년전용 버팀목 전세자금
    provider              text,                             -- 주택도시기금 …
    max_amount_won        bigint      not null check (max_amount_won >= 0),
    deposit_ratio         numeric(4, 3) not null check (deposit_ratio > 0 and deposit_ratio <= 1), -- 보증금의 몇 %까지
    max_annual_income_won bigint,                           -- 가구 연소득 상한 (없으면 제한 없음)
    max_total_assets_won  bigint,                           -- 총자산 상한
    min_age               integer,
    max_age               integer,
    target_groups         text[],                           -- YOUTH, NEWLYWED … (비우면 누구나)
    enabled               boolean     not null default true,
    source                text,                             -- 근거 (상품 안내 주소 등)
    updated_at            timestamptz not null default now()
);
