-- 대구도시공사(dudc)는 robots.txt가 사이트 전체 수집을 막아요 (User-agent: * / Disallow: /, 2026-10-19 확인).
-- 정기 수집(run·run-all)에서 빼요. 수집기 코드는 남겨 두고, 기관 허락을 받으면 true로 되돌려요.
update sources set enabled = false where code = 'dudc';
