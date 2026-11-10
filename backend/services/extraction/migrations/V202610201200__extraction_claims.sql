-- 원본 버전 처리권 (2026-10-20, mujuthaek_extraction/worker.py).
-- 같은 원본 글의 같은 버전을 두 처리가 동시에 하면(큐 재전달·다시 처리 이벤트·워커 여러 대) 각자 앞선 비용을 0으로 읽어 공고당 예산의 몇 배를 쓰고
-- 결과도 두 번 발행합니다. 처리 전에 이 행을 잡고, 처리 중에는 기한을 늘리고, 끝나면 지웁니다.
-- 워커가 죽으면 기한(expires_at)이 지난 뒤 다른 처리가 이어받습니다.
create table extraction_claims (
    raw_post_id uuid        not null,
    raw_version int         not null,
    owner       text        not null,             -- 처리 하나마다 새로 만드는 무작위 값 (호스트 이름 등 개인정보 없음)
    expires_at  timestamptz not null,
    created_at  timestamptz not null default now(),
    primary key (raw_post_id, raw_version)
);
