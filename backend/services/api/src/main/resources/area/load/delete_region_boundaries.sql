-- 이번 파일에 없는 경계(없어진 구역)를 같은 단계(SIG·EMD) 안에서만 지워요. 자리표시: 1 level
delete from area.region_boundaries t
where t.level = ?
  and not exists (select 1 from stage_norm s
                  where s.skip_reason is null and s.reject_reason is null and s.source_key = t.code);
