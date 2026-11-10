-- 확인 전까지 보류한 접수 일정이 있던 공고의 마감일(apply_end)을 지금 규칙(CompletedNotice.applyPeriod)으로 다시 정해요 (2026-11-10 코드 검토 뒤 재검토).
-- 공고 전체 접수 기간(schedule)이 없고 순위·대상별 접수 구간(applicationWindows)으로 마감일을 정한 공고에서, 구간 수가 원문 접수(APPLICATION) 일정 수보다
-- 적으면 보류해 빠진 더 늦은 접수가 있을 수 있어 마감일을 비워요. 예전 규칙은 보류한 2순위를 빼고 1순위 마감을 마감일로 적어 D-day·마감 알림이 앞당겨졌어요.
-- 새로 들어오는 공고는 이미 이 규칙이에요. 접수 상태는 예전부터 맞았어요(statusWindows가 보류 구간을 날짜 모르는 구간으로 넣음)
update notice.notices n
   set apply_end = null,
       updated_at = now()
  from notice.notice_versions v
 where v.notice_id = n.id
   and v.version = n.current_version
   and n.apply_end is not null
   and v.payload -> 'schedule' ->> 'applyStartOn' is null
   and v.payload -> 'schedule' ->> 'applyEndOn' is null
   and jsonb_typeof(v.payload -> 'applicationWindows') = 'array'
   and jsonb_array_length(v.payload -> 'applicationWindows') > 0
   and jsonb_typeof(v.payload -> 'notice' -> 'schedules') = 'array'
   and jsonb_array_length(v.payload -> 'applicationWindows')
       < (select count(*)
            from jsonb_array_elements(v.payload -> 'notice' -> 'schedules') s
           where jsonb_typeof(s -> 'kinds') = 'array' and s -> 'kinds' @> '["APPLICATION"]'::jsonb);
