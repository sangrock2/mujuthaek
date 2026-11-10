-- 접수 상태를 저장해요. 날짜 두 칸(apply_start·apply_end)으로 조회할 때 계산하면 마감 시각(「10/30 17:00까지」), 여러 접수 기간,
-- 확인 전까지 보류한 접수 기간을 반영하지 못했어요. 원문 일정으로 계산한 상태를 저장하고, 상태가 바뀔 수 있는 시각에 다시 계산해요.
-- UNKNOWN: 일정이 없거나 확실하지 않아 단정할 수 없음 (날짜가 없다는 이유만으로 상시 모집(ALWAYS)으로 보지 않아요)
alter table notice.notices
    add column status text not null default 'UNKNOWN'
        check (status in ('UPCOMING', 'APPLYING', 'CLOSED', 'ALWAYS', 'UNKNOWN')),
    add column next_status_check_at timestamptz,          -- 접수 상태를 다시 계산할 시각
    add column needs_check boolean not null default false; -- 원문 확인 전까지 보류한 항목이 있는지 (화면의 「확인 필요」)

create index notices_status_idx on notice.notices (field, status) where current_version > 0 and not hidden;
create index notices_status_check_idx on notice.notices (next_status_check_at);

-- 이미 공개된 공고는 다음 재계산 때 바로 계산해요
update notice.notices set next_status_check_at = now() where current_version > 0;
