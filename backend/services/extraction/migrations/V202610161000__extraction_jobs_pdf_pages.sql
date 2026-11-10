-- 첨부 PDF를 extraction이 직접 읽어 만든 쪽·표 구조 JSON (서비스 흐름 3단계 결과). 공고 원문만 들어 있습니다.
alter table extraction_jobs add column pdf_pages jsonb not null default '[]';
