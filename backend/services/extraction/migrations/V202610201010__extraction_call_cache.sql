-- 성공한 모델 호출 다시 쓰기 (2026-10-20, mujuthaek_extraction/model/call_cache.py).
-- 열쇠는 응답을 정하는 모든 것(요청 전부·모델 설정·실제 요청 본문·응답 처리 코드)의 sha256이라, 하나라도 바뀌면 다시 쓰지 않습니다.
-- 정상 종료이고 출력 형식을 통과한 응답만 넣습니다. 공고 원문에서 뽑은 내용만 있고 사용자 정보·키는 없습니다.
-- 보관: created_at이 EXTRACTION_CALL_CACHE_DAYS(기본 90일)보다 오래된 행은 워커 다시 처리 주기·retry 명령이 지웁니다.
create table extraction_call_cache (
    key        text primary key,                   -- sha256 hex
    model      text not null,                      -- local·gpt-6-luna (처음 받은 모델)
    call_name  text not null,                      -- structure·schedules·image_text 등
    response   jsonb not null,                     -- 응답 글자·모델 ID·종료 사유·처음 받을 때의 토큰 수
    usage      jsonb,                              -- 제공자가 준 사용량 원본
    created_at timestamptz not null default now()
);
create index extraction_call_cache_created_idx on extraction_call_cache (created_at);
