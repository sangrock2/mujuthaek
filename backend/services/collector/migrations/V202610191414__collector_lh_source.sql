-- LH 출처 등록 (담당자4). LH 분양임대공고문·상세정보·공급정보 API와 마이홈 모집공고 API로 수집해요.
insert into sources (code, name) values ('lh', 'LH 한국토지주택공사')
on conflict (code) do nothing;
