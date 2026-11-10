-- 서울시 청년안심주택 출처 등록. soco.seoul.go.kr 모집공고 게시판(BMSR00015)을 목록 JSON·상세 화면으로 수집해요.
insert into sources (code, name) values ('soco', '서울시 청년안심주택')
on conflict (code) do nothing;
