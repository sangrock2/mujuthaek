-- 상가 모집은 수집하지 않아요 (2026-10-22 결정). 기준은 sources/policy/base.py SHOP_RECRUIT·SHOP_SUPPORT와 같아요.
--   상가 모집: 전통시장 청년몰·점포·상가·푸드존 부스에 들어올 상인을 뽑는 공고 (청년몰 입점 모집, 상가 임대공급, 청년상인·점포운영자 모집 …)
--   점포 임차료 지원·상가 임대료 감면·점포 환경개선처럼 돈을 주는 사업은 그대로 수집해요
-- 수집기는 목록이 바뀌지 않은 수집 완료(DONE) 정책을 다시 거르지 않아서, 이미 수집한 상가 모집을 여기서 SKIPPED로 바꿔요.
-- 사업공간 모집(SPACE_RECRUITMENT)으로 나눴던 상가 모집은 창업지원(STARTUP_SUPPORT)으로 되돌려요 (분류도 수집기와 같게).
-- 2026-10-22 로컬 데이터: 10건 (온통청년 5, 기업마당 2, K-Startup 2, 보조금24 1). 저장한 버전은 그대로 남아요.

update raw_policies
set status = 'SKIPPED',
    field = case when field = 'SPACE_RECRUITMENT' then 'STARTUP_SUPPORT' else field end,
    attempts = 0, last_error = null, updated_at = now()
where status in ('PENDING', 'DONE', 'FAILED')
  and title ~ '청년몰|청춘창고|청년\s*상인.{0,6}모집|입점\s*상인|점포\s*운영자|(?:점포|상가|매장|스토어|청년식당).{0,15}(?:모집|입점|입주|임대\s*공급)'
  and title !~ '직매장|임차료|임대료|감면|안심벨|컨설팅|환경\s*개선';
