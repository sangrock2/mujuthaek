-- 처리 1회의 측정 기록 (2026-10-20): 모델 호출마다 시간·토큰(입력·캐시 읽기·캐시 쓰기·출력·추론)·종료 사유·오류 코드·추정 비용과
-- 단계별 시간(입력 해석·그림 판독·공급표·섹션 추출·결합 검증·재확인·격리·발행), 그 합계. 형식은 mujuthaek_extraction/usage.py.
-- 공고 원문·오류 문구·사용자 정보는 넣지 않습니다. cost_usd(예산 기준 추정)는 그대로 둡니다.
alter table extraction_jobs add column usage jsonb not null default '{}';
