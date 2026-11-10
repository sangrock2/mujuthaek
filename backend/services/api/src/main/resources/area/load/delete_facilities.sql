-- 이번 파일에 없는 줄(폐교·폐업 등)을 지워요. 자리표시: 1 source
delete from area.facilities f
where f.source = ?
  and not exists (select 1 from stage_norm s
                  where s.skip_reason is null and s.reject_reason is null and s.source_key = f.source_key);
