-- An explicit closure published by the original agency takes precedence over the original schedule.
alter table notice.notices
    add column source_closed_on date,
    add column source_closure_url text,
    add constraint notice_source_closure_pair
        check ((source_closed_on is null) = (source_closure_url is null));

-- GH announced that recruitment 850 ended in the first priority round on November 23.
-- Identify the exact published notice and source so that empty databases and unrelated notices are untouched.
update notice.notices
   set source_closed_on = date '2026-11-23',
       source_closure_url = 'https://apply.gh.or.kr/sb/sr/sr7150/selectPbancDetailView.do?pbancNo=850',
       apply_end = date '2026-11-23',
       status = 'CLOSED',
       next_status_check_at = null,
       updated_at = now()
 where id = '01a1dcb2-e54d-7000-818a-68ff868996ce'
   and provider = 'GH'
   and detail_url = 'https://apply.gh.or.kr/sb/sr/sr7150/selectPbancDetailView.do?pbancNo=850'
   and current_version > 0
   and merged_into is null;
