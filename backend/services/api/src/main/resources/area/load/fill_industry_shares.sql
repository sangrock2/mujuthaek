-- 업종 묶음별 전국 점포 수를 다시 채워요 (상가 적재 뒤 같은 트랜잭션). 입지계수의 분모예요.
with t as (
  select count(*) as total,
         count(*) filter (where industry_group = 'FOOD') as food,
         count(*) filter (where industry_group = 'CAFE') as cafe,
         count(*) filter (where large_code = 'G2') as retail
  from area.stores
)
insert into area.industry_shares (industry, store_count, total_count, updated_at)
select v.industry, v.n, t.total, now()
from t cross join lateral (values ('FOOD', t.food), ('CAFE', t.cafe), ('RETAIL', t.retail)) v(industry, n)
on conflict (industry) do update
  set store_count = excluded.store_count, total_count = excluded.total_count, updated_at = now();
