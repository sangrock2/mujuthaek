-- 7단계 상권 점수(공공 상가): 업종 묶음별 전국 점포 비율과 상권 점수 규칙. 점수는 사용자 업종이 있어야 해서 요청 때 계산하고 저장하지 않아요.

-- 업종 묶음별 전국 점포 수 (입지계수의 분모). 상가 적재(STORES) 때 area/load/fill_industry_shares.sql로 다시 채워요.
--   FOOD = 음식점 묶음, CAFE = 카페 묶음, RETAIL = 소매 대분류(G2)
create table area.industry_shares (
    industry    text        primary key check (industry in ('FOOD', 'CAFE', 'RETAIL')),
    store_count bigint      not null,
    total_count bigint      not null,           -- 그때 전국 전체 점포 수
    updated_at  timestamptz not null default now()
);

-- 상권 점수 규칙 (규칙 버전 2026.1). 생활권 계산은 score_weights의 LIFE 지표만 써서 영향이 없어요.
-- 구간은 실제 공공 상가 공고 정답 케이스가 아직 없어 임시 값이에요 — 공고로 맞춰 보고 새 버전으로 고쳐요.
--   밀도: 300m 안 점포가 많을수록 유동 인구가 많다고 봐요
--   경쟁: 입지계수 = (300m 안 같은 업종 ÷ 300m 안 전체) ÷ (전국 같은 업종 ÷ 전국 전체). 1보다 크면 과밀이라 낮게
--   교통: 가장 가까운 도시철도역 거리
insert into area.score_rules values
 ('2026.1', 'commercial_store_count_300m',  '{0,30,100,200}',      '{0,50,85,100}'),
 ('2026.1', 'commercial_location_quotient', '{0.5,1.0,1.5,2.5}',   '{100,70,40,0}'),
 ('2026.1', 'commercial_station_m',         '{300,500,1000,2000}', '{100,85,55,0}');
