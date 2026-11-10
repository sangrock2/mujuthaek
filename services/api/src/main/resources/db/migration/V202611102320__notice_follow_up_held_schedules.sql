-- 이미 저장한 후속 안내 일정에서 보류한 일정을 빼요 (NoticeContent.schedules와 같은 규칙, 2026-11-10 코드 검토 뒤 재검토).
-- 후속 안내는 일정만 저장하고 보류 항목은 두지 않아, 보류한 일정이 확정처럼 보였어요. 보류 항목은 그 후속 안내를 만든 extraction.completed(extraction_results)에서
-- 읽어요. 보류 범위가 그 일정이거나 그 위·아래와 겹치면(/schedules, /schedules/1, /schedules/2/endsAt) 그 일정을 빼요.
-- 새 규칙으로 저장한 줄은 이미 빠져 차례가 달라졌으니, 저장된 일정이 원래 이벤트의 일정 그대로인 줄만 고쳐요
update notice.notice_follow_ups f
   set schedules = coalesce((
           select jsonb_agg(s.value order by s.idx)
             from jsonb_array_elements(f.schedules) with ordinality as s(value, idx)
            where not exists (
                  select 1
                    from jsonb_array_elements(r.payload -> 'heldItems') h
                   where coalesce(h ->> 'target', '') <> ''
                     and (h ->> 'target' = '/schedules/' || (s.idx - 1)
                          or starts_with('/schedules/' || (s.idx - 1), (h ->> 'target') || '/')
                          or starts_with(h ->> 'target', '/schedules/' || (s.idx - 1) || '/')))), '[]'::jsonb),
       updated_at = now()
  from notice.extraction_results r
 where r.event_id = f.source_event_id
   and jsonb_typeof(r.payload -> 'heldItems') = 'array'
   and f.schedules = r.payload -> 'notice' -> 'schedules'
   and exists (select 1
                 from jsonb_array_elements(r.payload -> 'heldItems') h
                where h ->> 'target' = '/schedules' or starts_with(h ->> 'target', '/schedules/'));
