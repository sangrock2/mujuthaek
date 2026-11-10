-- 이번 시도 파일에 없는 점포(폐업 등)를 그 시도 안에서만 지워요. 자리표시: 1 load_scope
delete from area.stores t
where t.load_scope = ?
  and not exists (select 1 from stage_norm s
                  where s.skip_reason is null and s.reject_reason is null and s.source_key = t.source_key);
