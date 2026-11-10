#!/bin/bash
# area 저장·조회 방식 비교. 사용법:
#   BENCH_PSQL="psql postgresql://user:pass@localhost:5432/api" BENCH_DSN="host=localhost dbname=api user=… password=…" \
#     bash run.sh synthetic   # 빈 DB에 가짜 자료를 만들어 비교 (area 마이그레이션이 적용된 DB)
#     bash run.sh real        # 원천 21개를 실제로 적재한 DB에서 비교 (자료는 건드리지 않고 bench 스키마만 씀)
# 결과는 results-<mode>-<날짜>.txt 에 남아요. 비교 C(파티션·다시 넣기)는 area.stores_part, bench.* 를 만들었다 지워요.
set -euo pipefail
cd "$(dirname "$0")"
MODE=${1:?synthetic 또는 real}
PSQL=${BENCH_PSQL:-psql}
OUT="results-${MODE}-$(date +%Y%m%d-%H%M).txt"
q() { $PSQL -q -v ON_ERROR_STOP=1 "$@"; }
log() { echo "$@" | tee -a "$OUT"; }

DROP_PARTIAL='drop index if exists area.fac_subway_gix, area.fac_bus_gix, area.fac_school_gix, area.fac_park_gix, area.fac_hosp2_gix, area.fac_clinic_gix, area.st_conv_gix, area.st_mart_gix'
log "# area 비교 ($MODE) $(date '+%F %T')"
q -c "$DROP_PARTIAL" -c 'drop table if exists area.stores_part cascade' -c 'drop table if exists area.stores_seoul_new'   # 지난 실행이 남긴 것
log "$($PSQL -At -c 'select version()')"
if [ "$MODE" = synthetic ]; then
  loaded=$($PSQL -At -c "select count(*) from area.load_runs where status = 'SUCCEEDED'")
  if [ "$loaded" != "0" ]; then echo "실제 적재 기록이 ${loaded}건 있는 DB예요. synthetic은 area.stores를 비워서 여기서는 못 돌려요 (real 모드를 쓰세요)" >&2; exit 1; fi
  q -f 00_setup.sql -f 01_facilities.sql -f 02_stores.sql
  for r in "1 700000" "700001 1400000" "1400001 2100000" "2100001 2772484"; do set -- $r; q -v from=$1 -v to=$2 -f 02b_stores_chunk.sql; done
  q -c 'create index if not exists stores_geom_gix on area.stores using gist (geom)' \
    -c 'create index if not exists stores_group_idx on area.stores (industry_group)' \
    -c 'create index if not exists stores_scope_idx on area.stores (load_scope)'
else
  q -f 00_sites_real.sql
fi
q -c 'vacuum analyze area.stores' -c 'vacuum analyze area.facilities' -c 'vacuum analyze bench.sites'
log "$($PSQL -At -F' ' -c "select 'stores', count(*), pg_size_pretty(pg_total_relation_size('area.stores')) from area.stores union all select 'facilities', count(*), pg_size_pretty(pg_total_relation_size('area.facilities')) from area.facilities")"

log "## A. 세권 지표 계산 — 공간 인덱스 하나"
python3 bench_a.py "공간 인덱스 하나" | tee -a "$OUT"
python3 bench_a_each.py | tee -a "$OUT"
q -c "create index if not exists fac_subway_gix on area.facilities using gist (geom) where kind='SUBWAY_STATION'" \
  -c "create index if not exists fac_bus_gix on area.facilities using gist (geom) where kind='BUS_STOP'" \
  -c "create index if not exists fac_school_gix on area.facilities using gist (geom) where kind='SCHOOL'" \
  -c "create index if not exists fac_park_gix on area.facilities using gist (geom) where kind='PARK'" \
  -c "create index if not exists fac_hosp2_gix on area.facilities using gist (geom) where kind='HOSPITAL' and sub_kind='SECONDARY'" \
  -c "create index if not exists fac_clinic_gix on area.facilities using gist (geom) where kind='HOSPITAL' and sub_kind='CLINIC'" \
  -c "create index if not exists st_conv_gix on area.stores using gist (geom) where industry_group='CONVENIENCE_STORE'" \
  -c "create index if not exists st_mart_gix on area.stores using gist (geom) where industry_group='MART'" \
  -c 'analyze area.facilities' -c 'analyze area.stores'
log "## A. 세권 지표 계산 — + 종류별 부분 인덱스"
python3 bench_a.py "+ 종류별 부분 인덱스" | tee -a "$OUT"
python3 bench_a_each.py | tee -a "$OUT"

log "## B. 목록 API 읽기"
q -f 03_read_tables.sql
python3 bench_b.py | tee -a "$OUT"

log "## C. 파티션 — 조회"
q -f 04_part.sql
q -c "insert into area.stores_part (id, source_key, load_scope, name, large_code, small_code, industry_group, geom, data_date) select id, source_key, load_scope, name, large_code, small_code, industry_group, geom, data_date from area.stores"
q -c 'create index on area.stores_part using gist (geom)' -c 'create index on area.stores_part (industry_group)' \
  -c "create index on area.stores_part using gist (geom) where industry_group='CONVENIENCE_STORE'" \
  -c "create index on area.stores_part using gist (geom) where industry_group='MART'" -c 'analyze area.stores_part'
python3 bench_c2.py | tee -a "$OUT"

log "## C. 서울 다시 넣기 — 테이블 하나 (시간만 재고 되돌려요)"
q -f 05_stage.sql
$PSQL -v ON_ERROR_STOP=1 -f 06_reload_single.sql 2>&1 | grep -E "Time|inserted|^ +[0-9]|DELETE|UPDATE" | tee -a "$OUT" || true
log "## C. 서울 다시 넣기 — 파티션 바꿔 끼우기"
P=$($PSQL -At -c "select inhrelid::regclass from pg_inherits i join pg_class c on c.oid=i.inhrelid where inhparent='area.stores_part'::regclass and pg_get_expr(c.relpartbound, c.oid) like '%서울%'")
SWAP_SQL=$(mktemp)
trap 'rm -f "$SWAP_SQL"' EXIT
sed "s/__OLD__/$P/" 07_reload_swap.template.sql > "$SWAP_SQL"
$PSQL -v ON_ERROR_STOP=1 -f "$SWAP_SQL" 2>&1 | grep -E "Time|ERROR" | tee -a "$OUT"

log "## 정리"
q -c 'drop table if exists area.stores_part cascade' -c 'drop table if exists area.stores_seoul_new' \
  -c "$DROP_PARTIAL" -c 'drop schema if exists bench cascade'
log "결과: $OUT"
