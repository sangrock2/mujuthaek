-- 6단계 생활권 점수: 대상 위치(임시 테이블 target_locations)의 항목 점수 5개를 규칙 버전(?)으로 계산해 location_scores에 반영해요.
-- 지표가 없으면(근처에 그 시설이 아예 없음) 그 지표는 0점. round()는 0.5를 올려요 — 자바 쪽도 HALF_UP으로 맞춰요.
delete from area.location_scores s using target_locations t
 where s.location_id = t.location_id and s.score_kind = 'LIFE';
insert into area.location_scores (location_id, score_kind, category, score, score_version)
select t.location_id, w.score_kind, w.category,
       round(sum(w.weight * coalesce(area.piecewise(m.value, r.xs, r.ys), 0)))::smallint,
       w.score_version
from target_locations t
join area.notice_locations l on l.location_id = t.location_id and l.status in ('OK', 'APPROX')
cross join area.score_weights w
join area.score_rules r on r.score_version = w.score_version and r.metric = w.metric
left join area.location_metrics m on m.location_id = t.location_id and m.metric = w.metric
where w.score_version = ? and w.score_kind = 'LIFE'
group by t.location_id, w.score_kind, w.category, w.score_version
