truncate area.stores;
drop index if exists area.stores_geom_gix; drop index if exists area.stores_group_idx;
drop index if exists area.stores_small_code_idx; drop index if exists area.stores_scope_idx;
drop table if exists bench.mix;
create table bench.mix (grp text, large text, small text, w float8, cum float8);
insert into bench.mix (grp, large, small, w) values
 ('CONVENIENCE_STORE','G2','G20405',0.02), ('MART','G2','G20404',0.015), ('CAFE','I2','I21201',0.04),
 ('FOOD','I2','I20101',0.25), ('BAR','I2','I21103',0.04), ('G2','G2','G21304',0.235),
 ('S2','S2','S20101',0.12), ('P1','P1','P10501',0.06), ('Q1','Q1','Q10201',0.04),
 ('R1','R1','R10202',0.04), ('L1','L1','L10201',0.05), ('M1','M1','M10101',0.04),
 ('I1','I1','I10101',0.015), ('N1','N1','N10101',0.02);
update bench.mix m set cum = s.c from (select small, sum(w) over (order by small) / sum(w) over () c from bench.mix) s where s.small = m.small;
