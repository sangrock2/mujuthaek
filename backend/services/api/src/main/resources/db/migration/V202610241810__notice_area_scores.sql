-- 지역 점수: area가 계산한 위치별 생활·상업 점수를 공고 상세에 보여 주려고 보관해요.
-- 사용자 개인 선호·직장·통근 점수는 넣지 않아요 (공통 점수만).
create table notice.notice_area_scores (
    notice_id            uuid          not null references notice.notices (id),
    notice_version       int           not null,           -- 계산에 쓴 위치가 담긴 공고 버전
    location_id          text          not null,           -- 상세 locations[].id
    kind                 text          not null check (kind in ('LIVING', 'COMMERCIAL')),
    score                numeric(5, 2) not null check (score between 0 and 100),
    calculated_at        timestamptz   not null,           -- area가 계산한 시각
    calculation_version  text          not null,           -- area 계산 방식 버전
    received_at          timestamptz   not null,
    primary key (notice_id, location_id, kind),
    foreign key (notice_id, notice_version) references notice.notice_versions (notice_id, version)
);
