-- NULL은 구버전/외부 실행 회차: 자동 정리하지 않아요.
alter table crawl_runs add column owner_instance uuid;
