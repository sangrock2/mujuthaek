-- 정책·혜택 API 출처. 테이블은 게시판 수집과 같이 써요 (raw_posts.board_key = 'policy', kind = 'POLICY').
-- raw_post_versions.meta에는 API 응답 원본(목록 + 상세 + 지원조건)을, raw_files.role에는 POLICY_DOC·FORM·ATTACHMENT를 넣어요.

insert into sources (code, name) values
    ('gov24', '정부24 보조금24 (행정안전부 공공서비스 혜택)'),
    ('bokjiro_central', '복지로 중앙부처 복지서비스'),
    ('bokjiro_local', '복지로 지자체 복지서비스'),
    ('youth', '온통청년 청년정책')
on conflict (code) do nothing;
