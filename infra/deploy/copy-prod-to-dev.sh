#!/usr/bin/env bash
# 운영 api DB의 공고·혜택·생활권·판정 기준 데이터를 개발 api DB(api_dev)로 한 번 복사해요. 운영 서버(/opt/mujuthaek)에서 손으로 돌려요.
#   사용: copy-prod-to-dev.sh [--dry-run] [--skip-big]
#     --dry-run   옮길 테이블·줄 수(추정)·같이 비워지는 개발 테이블만 보여 주고 끝내요
#     --skip-big  area.address_points·area.stores(수 GB, 주소 검색·상권에만 써요)는 빼요
# 옮기는 것: 스키마 notice·benefit·area·eligibility의 테이블 (아래 EXCLUDE 제외). 회원·알림·채팅·트래픽·관리자 기록은 옮기지 않아요.
# 방법: 개발 DB의 대상 테이블을 비우고(TRUNCATE … CASCADE) 운영에서 pg_dump --data-only로 뜬 데이터를 넣어요. 한 트랜잭션이라 중간에 실패하면 그대로예요.
# 운영 DB 계정은 .env(API_DB_URL·API_DB_USER·API_DB_PASSWORD), 개발 DB 계정·암호는 실행할 때 입력받아요(파일·명령 기록에 남기지 않아요).
# pg_dump·psql은 서버에 설치하지 않고 postgres 이미지(PG_IMAGE)로 돌려요.
set -euo pipefail

BASE="${MUJUTHAEK_DIR:-/opt/mujuthaek}"
PG_IMAGE="${PG_IMAGE:-postgres:17-alpine}"
PG_NETWORK="${PG_NETWORK:-}"            # 로컬 시험용 (예: mujuthaek_default). 서버는 비워 둬요
DEV_DB_NAME="${DEV_DB_NAME:-api_dev}"
SCHEMAS=(notice benefit area eligibility)
# 사용자가 만든 데이터·관리자 기록은 옮기지 않아요
EXCLUDE=(notice.notice_reports area.area_reports eligibility.criteria_set_history)
BIG=(area.address_points area.stores)

DRY_RUN=no
SKIP_BIG=no
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=yes ;;
    --skip-big) SKIP_BIG=yes ;;
    *)
      echo "사용: $0 [--dry-run] [--skip-big]" >&2
      exit 2
      ;;
  esac
done

cd "$BASE"
[ -f .env ] || { echo "${BASE}/.env가 없어요" >&2; exit 1; }

env_value() {
  local line
  line="$(grep -E "^$1=" .env | tail -n 1 || true)"
  line="${line#*=}"
  line="${line%\"}"
  echo "${line#\"}"
}

# 운영: jdbc:postgresql://호스트:포트/DB?… → 호스트·포트·DB
SRC_URL="$(env_value API_DB_URL)"
SRC_USER="$(env_value API_DB_USER)"
SRC_PASS="$(env_value API_DB_PASSWORD)"
if [ -z "$SRC_URL" ] || [ -z "$SRC_USER" ] || [ -z "$SRC_PASS" ]; then
  echo ".env에 API_DB_URL·API_DB_USER·API_DB_PASSWORD가 없어요" >&2
  exit 1
fi
rest="${SRC_URL#jdbc:postgresql://}"
rest="${rest%%\?*}"
SRC_DB="${rest#*/}"
hostport="${rest%%/*}"
SRC_HOST="${hostport%%:*}"
SRC_PORT=5432
[ "$hostport" != "$SRC_HOST" ] && SRC_PORT="${hostport#*:}"

DEV_HOST="${DEV_DB_HOST:-$SRC_HOST}"
DEV_PORT="${DEV_DB_PORT:-$SRC_PORT}"
read -rp "개발 DB(${DEV_HOST}/${DEV_DB_NAME}) 계정: " DEV_USER
read -rsp "개발 DB 암호: " DEV_PASS
echo
if [ -z "$DEV_USER" ] || [ -z "$DEV_PASS" ]; then
  echo "계정·암호가 비었어요" >&2
  exit 1
fi
if [ "$DEV_HOST" = "$SRC_HOST" ] && [ "$DEV_DB_NAME" = "$SRC_DB" ]; then
  echo "운영 DB와 개발 DB가 같아요 (${SRC_DB}). 멈춰요" >&2
  exit 1
fi

# postgres 이미지로 psql·pg_dump. 암호는 환경 변수로만 넘겨요 (명령줄에 남지 않게).
# 표준 입력은 데이터를 흘려 넣을 때(PG_STDIN=1)만 붙여요. 아니면 확인 질문에 쓸 입력을 먹어 버려요
pg() {
  local which="$1" tool="$2"
  shift 2
  local opts=(--rm)
  [ -n "$PG_NETWORK" ] && opts+=(--network "$PG_NETWORK")
  [ "${PG_STDIN:-}" = 1 ] && opts+=(-i)
  if [ "$which" = src ]; then
    PGPASSWORD="$SRC_PASS" docker run "${opts[@]}" -e PGPASSWORD "$PG_IMAGE" \
      "$tool" -h "$SRC_HOST" -p "$SRC_PORT" -U "$SRC_USER" -d "$SRC_DB" "$@"
  else
    PGPASSWORD="$DEV_PASS" docker run "${opts[@]}" -e PGPASSWORD "$PG_IMAGE" \
      "$tool" -h "$DEV_HOST" -p "$DEV_PORT" -U "$DEV_USER" -d "$DEV_DB_NAME" "$@"
  fi
}

# 줄 수: 200MB 미만은 정확히 세고, 큰 테이블은 통계 추정(~)
ROWS_SQL() {
  echo "case when pg_total_relation_size(c.oid) < 200 * 1024 * 1024
    then (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from %s', c.oid::regclass), false, true, '')))[1]::text
    else '~' || greatest(c.reltuples, 0)::bigint end"
}

skip_list=("${EXCLUDE[@]}")
[ "$SKIP_BIG" = yes ] && skip_list+=("${BIG[@]}")
schemas_sql="$(printf "'%s'," "${SCHEMAS[@]}")"
skip_sql="$(printf "'%s'," "${skip_list[@]}")"

# 옮길 테이블: 운영에 있는 그 스키마의 테이블 (제외 목록 빼고)
mapfile -t TABLES < <(pg src psql -At -c "
  select n.nspname || '.' || c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p') and n.nspname in (${schemas_sql%,})
    and n.nspname || '.' || c.relname not in (${skip_sql%,})
  order by 1")
[ "${#TABLES[@]}" -gt 0 ] || { echo "옮길 테이블이 없어요" >&2; exit 1; }
tables_sql="$(printf "'%s'," "${TABLES[@]}")"

# 개발 DB에도 같은 테이블이 있는지 (api 마이그레이션 버전이 같아야 해요)
mapfile -t MISSING < <(pg dev psql -At -c "
  select t from unnest(array[${tables_sql%,}]) t where to_regclass(t) is null")
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "개발 DB에 없는 테이블이 있어요 (개발 api를 운영과 같은 버전으로 먼저 배포해요): ${MISSING[*]}" >&2
  exit 1
fi

echo "== 운영 ${SRC_HOST}/${SRC_DB} → 개발 ${DEV_HOST}/${DEV_DB_NAME}"
echo "옮길 테이블 ${#TABLES[@]}개 (200MB 넘는 테이블의 줄 수는 통계 추정 ~):"
pg src psql -At -F $'\t' -c "
  select c.oid::regclass, $(ROWS_SQL), pg_size_pretty(pg_total_relation_size(c.oid))
  from pg_class c where c.oid in (select unnest(array[${tables_sql%,}])::regclass) order by c.oid::regclass::text" \
  | while IFS=$'\t' read -r name rows size; do printf '  %-42s %14s  %s\n' "$name" "$rows" "$size"; done
echo "옮기지 않음: ${skip_list[*]}"

# TRUNCATE … CASCADE로 같이 비워지는 개발 테이블 (옮기지 않는 테이블이 옮길 테이블을 참조하면)
mapfile -t CASCADE < <(pg dev psql -At -c "
  select distinct con.conrelid::regclass::text from pg_constraint con
  where con.contype = 'f' and con.confrelid::regclass::text in (${tables_sql%,})
    and con.conrelid::regclass::text not in (${tables_sql%,}) order by 1")
if [ "${#CASCADE[@]}" -gt 0 ]; then
  echo "같이 비워지는 개발 테이블 (옮길 테이블을 참조해요): ${CASCADE[*]}"
fi

if [ "$DRY_RUN" = yes ]; then
  echo "(--dry-run: 바꾼 것 없음)"
  exit 0
fi

read -rp "개발 DB ${DEV_DB_NAME}의 위 테이블을 비우고 운영 데이터로 채울까요? (yes): " answer
[ "$answer" = yes ] || { echo "그만뒀어요"; exit 0; }

# 옮기는 테이블끼리 걸린 외래키(notices.merged_into 같은 자기 참조 포함)는 넣는 동안 풀었다가 다 넣은 뒤 다시 걸어 검증해요.
# 줄 순서 때문에 넣다가 막히지 않게요. 같은 트랜잭션이라 다시 걸 때 어긋나면 전부 되돌려져요 (개발 계정이 테이블 주인이어야 해요)
fk_where="contype = 'f' and conrelid::regclass::text in (${tables_sql%,}) and confrelid::regclass::text in (${tables_sql%,})"
DROP_FK="$(pg dev psql -At -c "select format('alter table %s drop constraint %I;', conrelid::regclass, conname) from pg_constraint where ${fk_where}")"
ADD_FK="$(pg dev psql -At -c "select format('alter table %s add constraint %I %s;', conrelid::regclass, conname, pg_get_constraintdef(oid)) from pg_constraint where ${fk_where}")"

dump_args=(--data-only --no-owner --no-privileges)
for t in "${TABLES[@]}"; do dump_args+=(-t "$t"); done

echo "복사 중… (큰 테이블은 몇 분 걸려요)"
{
  echo "truncate table $(IFS=,; echo "${TABLES[*]}") cascade;"
  echo "$DROP_FK"
  pg src pg_dump "${dump_args[@]}" 2> >(grep -v "circular foreign-key\|detail: \|hint: " >&2)
  echo "$ADD_FK"
} | PG_STDIN=1 pg dev psql -q -v ON_ERROR_STOP=1 --single-transaction -f - > /dev/null

pg dev psql -q -c "analyze $(IFS=,; echo "${TABLES[*]}");" > /dev/null
echo "끝: 개발 DB 줄 수"
pg dev psql -At -F $'\t' -c "
  select c.oid::regclass, $(ROWS_SQL) from pg_class c
  where c.oid in (select unnest(array[${tables_sql%,}])::regclass) order by c.oid::regclass::text" \
  | while IFS=$'\t' read -r name rows; do printf '  %-42s %14s\n' "$name" "$rows"; done
