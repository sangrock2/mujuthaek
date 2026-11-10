-- 창업지원 공고 API 출처. 정책 테이블(raw_policies …)에 field = STARTUP_SUPPORT로 저장해요.

insert into sources (code, name) values
    ('kstartup', 'K-Startup 창업지원사업 공고'),
    ('bizinfo', '기업마당 지원사업 공고')
on conflict (code) do nothing;
