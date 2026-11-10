-- 대출 상품 자격 조건: 주택도시기금 공공 대출(전세·월세·구입)을 사용자가 받을 수 있는지 판정하는 데 써요
-- 한 행 = 상품 하나의 한 시점 조건이에요. 판정은 공고와 상관없이 사람 조건(나이·세대·혼인·출산·소득·순자산·무주택)만 봐요
--   집이 정해져야 보는 조건(보증금 상한, 전용면적, 담보 평가액)과 한도 계산은 넣지 않아요. 한도·금리는 화면용 요약 글자로만 둬요
-- 조건이 바뀌면 코드는 그대로 두고 새 마이그레이션으로 effective_from(시행일)이 다른 행을 더해요
--   판정은 상품마다 effective_from이 기준일 이전인 가장 늦은 행을 써요
-- 공통 규칙(코드): 세대원 전원 무주택. "세대주(예비 세대주 포함)"는 대출을 받으면서 세대주가 된다고 보고 묻지 않아요
create table eligibility.loan_rules (
    id                          uuid    primary key,
    product_code                text    not null,
    product_name                text    not null,
    loan_type                   text    not null check (loan_type in ('JEONSE', 'MONTHLY_RENT', 'PURCHASE')), -- 전세 / 월세 / 구입
    display_order               integer not null,               -- 화면에 보여 줄 순서
    effective_from              date    not null,
    min_age                     integer,                        -- 기준일(대출접수일)의 만 나이 (둘 다 포함)
    max_age                     integer,
    single_householder_required boolean not null default false, -- 단독세대주(1인 세대)여야 함
    under30_single_excluded     boolean not null default false, -- 만 30세 미만 미혼 단독세대주 제외 (부양 6개월 이상 세대는 가능)
    newlywed_required           boolean not null default false,
    newlywed_max_years          integer,                        -- 신혼부부 = 혼인 N년 이내 (3개월 안 결혼 예정 포함). 신혼 필수·신혼 소득 예외에 씀
    newborn_within_months       integer,                        -- 기준일부터 N개월 안에 출산한 자녀가 있어야 함
    newborn_born_since          date,                           -- 그 자녀의 출생일 하한
    first_home_required         boolean not null default false, -- 생애최초 주택구입(세대원 모두 집을 산 적이 없음)이어야 함
    max_income_won              bigint  not null,               -- 부부합산 연소득 상한 (기본, 미혼이면 본인)
    max_income_newlywed_won     bigint,                         -- 신혼가구면 이 상한
    max_income_two_children_won bigint,                         -- 미성년 자녀 2명 이상이면 이 상한
    max_income_first_home_won   bigint,                         -- 생애최초 주택구입이면 이 상한
    max_income_dual_won         bigint,                         -- 맞벌이면 이 상한 (부부 각각은 max_each_income_won 이하)
    max_each_income_won         bigint,
    max_applicant_income_won    bigint,                         -- 신혼가구가 합산 상한을 넘어도 신청인 1인 연소득이 이 이하면 가능
    max_net_asset_won           bigint  not null,               -- 부부합산 순자산 상한
    unverifiable_requirement    text,                           -- 사용자 입력으로 알 수 없는 조건. 있으면 결과는 최대 '확인 필요'
    limit_summary               text    not null,               -- 화면용 한도 요약 (판정에 안 씀)
    rate_summary                text    not null,               -- 화면용 금리 요약 (판정에 안 씀)
    source_url                  text    not null,               -- 상품안내 원문
    unique (product_code, effective_from),
    check (newlywed_max_years is not null
           or (not newlywed_required and max_income_newlywed_won is null and max_applicant_income_won is null))
);

-- 2026-10-20 06:15 ~ 06:46 KST(전세)와 2026-10-21 19:50 ~ 20:00 KST(월세·구입)에 주택도시기금 포털 상품안내 원문으로 확인한 값이에요
--   조사 기록: 작업노트 조사자료_대출상품_20261020/ (대출상품_현행조건_상세.md, 공공대출_상품목록_정리_20261021.md)
-- effective_from 2026-01-01 = 2026년 순자산 기준(전세·월세 3.45억, 구입 5.11억)을 쓰기 시작한 날
-- 넣지 않은 상품: 신규 접수가 끝난 중소기업취업청년 전월세보증금대출(2024-12-31까지)·갱신만료 임차인 버팀목,
--   피해자 결정·확인서 같은 따로 증명할 자격이 필요한 상품(전세피해·전세사기·주거취약계층·부도임대·재해주택),
--   팀 논의 중인 상품(신혼희망타운전용, 오피스텔구입, 수익·손익공유형 모기지)
-- 단순화한 곳:
--   청년전용 버팀목의 병역 복무기간 나이 연장(최대 만 39세)과 혁신도시·재개발 이주 소득 예외(6천만원)는 넣지 않았어요
--   신혼부부전용 전세는 2026-10-19부터 "합산 7.5천만원 초과라도 신청인 1인 5천만원 이하면 가능"이 더해져 시행일 행을 둘로 나눴어요
--   주거안정월세 우대형(취업준비생·사회초년생·장려금·주거급여 수급자)은 모두 일반형 소득 기준(5천만원) 안이라 일반형 기준으로 판정하고 금리 요약에만 적어요
--   청년 주택드림 디딤돌의 "청약 당첨 때 만 39세 이하"는 당첨일을 몰라서 나이로 보지 않고 확인할 수 없는 조건 문장에 넣었어요
insert into eligibility.loan_rules (
    id, product_code, product_name, loan_type, display_order, effective_from,
    min_age, max_age, single_householder_required, under30_single_excluded,
    newlywed_required, newlywed_max_years, newborn_within_months, newborn_born_since, first_home_required,
    max_income_won, max_income_newlywed_won, max_income_two_children_won, max_income_first_home_won,
    max_income_dual_won, max_each_income_won, max_applicant_income_won,
    max_net_asset_won, unverifiable_requirement, limit_summary, rate_summary, source_url) values
    ('ff1b1c77-00af-4cb8-98dc-974d8928d69e', 'BEOTIMMOK_GENERAL', '버팀목전세자금', 'JEONSE', 10, '2026-01-01',
     19, null, false, false,
     false, 7, null, null, false,
     50000000, 75000000, 60000000, null,
     null, null, null,
     345000000, null,
     '수도권 1.2억 원 / 그 외 0.8억 원 (신혼·2자녀 이상 2.5억 원 / 1.6억 원), 보증금의 70% (신혼·2자녀 이상 80%)',
     '연 2.5~3.5%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020101.jsp'),
    ('cf52e263-00d2-46f8-9fa9-641c533575e0', 'BEOTIMMOK_YOUTH', '청년전용 버팀목전세자금', 'JEONSE', 20, '2026-01-01',
     19, 34, false, false,
     false, 7, null, null, false,
     50000000, 75000000, 60000000, null,
     null, null, null,
     345000000, null,
     '1.5억 원 (만 25세 미만 단독세대주 1.2억 원), 보증금의 80%',
     '연 2.2~3.3%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020301.jsp'),
    ('d4cc7224-663b-4ec9-85d2-17f6324daf4d', 'BEOTIMMOK_NEWLYWED', '신혼부부전용 전세자금', 'JEONSE', 30, '2026-01-01',
     19, null, false, false,
     true, 7, null, null, false,
     75000000, null, null, null,
     null, null, null,
     345000000, null,
     '수도권 2.5억 원 / 그 외 1.6억 원, 보증금의 80%',
     '연 1.9~3.3%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020401.jsp'),
    ('f11e3c27-e2dc-4cb0-a959-719b87aba144', 'BEOTIMMOK_NEWLYWED', '신혼부부전용 전세자금', 'JEONSE', 30, '2026-10-19',
     19, null, false, false,
     true, 7, null, null, false,
     75000000, null, null, null,
     null, null, 50000000,
     345000000, null,
     '수도권 2.5억 원 / 그 외 1.6억 원, 보증금의 80%',
     '연 1.9~3.3% (신청인 1인 소득으로 받으면 +0.3%p)',
     'https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020401.jsp'),
    ('d4aaf9f1-7b8a-4e9d-bc11-1bc1a9c28b84', 'BEOTIMMOK_NEWBORN', '신생아 특례 버팀목대출', 'JEONSE', 40, '2026-01-01',
     19, null, false, false,
     false, null, 24, '2023-01-01', false,
     130000000, null, null, null,
     200000000, 130000000, null,
     345000000, null,
     '2.4억 원, 보증금의 80%',
     '연 1.3~4.3%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05021401.jsp'),
    ('4e299f28-d256-47e2-b0da-34cd62c4537d', 'YOUTH_MONTHLY_RENT', '청년전용 보증부월세대출', 'MONTHLY_RENT', 50, '2026-01-01',
     19, 34, true, false,
     false, null, null, null, false,
     50000000, null, null, null,
     null, null, null,
     345000000, null,
     '보증금 4,500만 원 + 월세금 1,200만 원 (24개월, 월 50만 원 이내)',
     '보증금 연 1.3%, 월세금 연 0%(월 20만 원까지)·1.0%(초과분)',
     'https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020701.jsp'),
    ('042dda10-f19a-4475-aa09-e0a4f6aeb9e1', 'HOUSING_STABILITY_MONTHLY_RENT', '주거안정월세대출', 'MONTHLY_RENT', 60, '2026-01-01',
     19, null, false, false,
     false, null, null, null, false,
     50000000, null, null, null,
     null, null, null,
     345000000, null,
     '1,440만 원 (월 60만 원 이내)',
     '우대형(취업준비생·사회초년생·근로/자녀장려금·주거급여 수급자 등) 연 1.3%, 일반형 연 1.8%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020201.jsp'),
    ('ec291d1b-8470-47ef-9afb-91f1c018c0d5', 'DIDIMDOL', '내집마련 디딤돌대출', 'PURCHASE', 70, '2026-01-01',
     19, null, false, true,
     false, 7, null, null, false,
     60000000, 85000000, 70000000, 70000000,
     null, null, 60000000,
     511000000, null,
     '2억 원 (생애최초 2.4억 원, 신혼·2자녀 이상 3.2억 원), LTV 70% (생애최초 80%)',
     '연 2.85~4.15%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0503/FP05030101.jsp'),
    ('b5180bc9-5be1-455e-98dd-eca36aa1a62d', 'DIDIMDOL_NEWLYWED', '신혼부부전용 구입자금', 'PURCHASE', 80, '2026-01-01',
     19, null, false, true,
     true, 7, null, null, true,
     85000000, null, null, null,
     null, null, 60000000,
     511000000, null,
     '3.2억 원, LTV 80% (수도권·규제지역 70%)',
     '연 2.55~3.85%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0503/FP05030601.jsp'),
    ('9d446b5e-3674-47d0-9e4f-834569bd7a8b', 'DIDIMDOL_NEWBORN', '신생아 특례 디딤돌대출', 'PURCHASE', 90, '2026-01-01',
     19, null, false, false,
     false, null, 24, '2023-01-01', false,
     130000000, null, null, null,
     200000000, 130000000, null,
     511000000, null,
     '4억 원, LTV 70% (생애최초 80%)',
     '연 1.8~4.5%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0503/FP05030801.jsp'),
    ('7d194d6a-7227-4e4c-9252-6f6946326880', 'DIDIMDOL_YOUTH_DREAM', '청년 주택드림 디딤돌대출', 'PURCHASE', 100, '2026-01-01',
     19, null, false, false,
     false, 7, null, null, false,
     70000000, 100000000, null, null,
     null, null, 70000000,
     511000000, '청년 주택드림 통장으로 청약에 당첨되어야 해요 (당첨 때 만 39세 이하, 통장 1년 이상 가입·1천만 원 이상 납입)',
     '미혼 3억 원, 신혼 4억 원, LTV 70% (생애최초 80%)',
     '연 2.4~4.15%',
     'https://nhuf.molit.go.kr/FP/FP05/FP0503/FP05030901.jsp');
