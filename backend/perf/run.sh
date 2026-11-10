#!/usr/bin/env bash
# 테스트 한 번 = 결과 폴더 하나. k6를 돌리고 그 구간의 숫자·그래프 이미지·느린 쿼리·버전·데이터 양을 다 모아요.
#   perf/run.sh <smoke|load|soak|stress|breakpoint|spike> ["고친 것 메모"]
# 결과: perf/results/<yyyyMMdd-HHmm>_<test>_<api 버전>/  (README 「결과 폴더」)
source "$(dirname "$0")/lib/common.sh"

TEST="${1:-}"
NOTE="${2:-}"
case "$TEST" in
  smoke) LOAD="2명" ;;
  load) LOAD="100명" ;;
  soak) LOAD="50명" ;;
  stress) LOAD="50→1,000명" ;;
  breakpoint) LOAD="초당 20건~" ;;
  spike) LOAD="20→500→20명" ;;
  *) sed -n '2,4p' "$0"; exit 1 ;;
esac

echo "== 준비 확인"
curl -sf "$PROM/-/ready" > /dev/null || { echo "Prometheus가 없어요: docker compose -f perf/docker-compose.yml up -d" >&2; exit 1; }
curl -sf "$GRAFANA/api/health" > /dev/null || { echo "Grafana가 없어요: docker compose -f perf/docker-compose.yml up -d" >&2; exit 1; }
curl -sf -o /dev/null http://127.0.0.1:18080/actuator/prometheus || { echo "서버 지표가 안 보여요: 다른 터미널에서 perf/tunnel.sh" >&2; exit 1; }
curl -sf -o /dev/null http://127.0.0.1:19100/metrics || warn "node-exporter가 안 보여요(perf/server.sh exporters-up). 서버 CPU 그래프가 빠져요"

VERSIONS="$(remote_versions)" || { echo "서버에 SSH로 붙지 못했어요 (perf/.env의 SSH_KEY)" >&2; exit 1; }
API_TAG="$(sed -n 's/^API_TAG=//p' <<< "$VERSIONS")"
NOTIFICATION_TAG="$(sed -n 's/^NOTIFICATION_TAG=//p' <<< "$VERSIONS")"

NAME="$(date +%Y%m%d-%H%M)_${TEST}_${API_TAG:-unknown}"
OUT="$PERF_DIR/results/$NAME"
mkdir -p "$OUT"
echo "== $NAME"

if remote_sql < "$PERF_DIR/lib/pg_stats.sql" > "$OUT/pg_before.csv" 2> "$OUT/pg.err"; then PG=1; else
  PG=0; warn "pg_stat_statements를 못 읽었어요(README 「사용자가 할 일」). 느린 쿼리는 빠져요: $(head -c 200 "$OUT/pg.err")"
fi
remote_sql < "$PERF_DIR/lib/table_counts.sql" > "$OUT/table_counts.csv" 2>> "$OUT/pg.err" || warn "데이터 양을 못 읽었어요"

MEMBER=false
[ -n "${JWT_SECRET:-}" ] && [ -n "${TEST_USER_ID:-}" ] && MEMBER=true

START=$(date +%s)
set +e
TEST="$TEST" BASE_URL="$BASE_URL" OUT_DIR="$OUT" \
  K6_PROMETHEUS_RW_SERVER_URL="$PROM/api/v1/write" \
  K6_PROMETHEUS_RW_TREND_STATS='p(95),p(99),avg,max' \
  K6_WEB_DASHBOARD=true K6_WEB_DASHBOARD_EXPORT="$OUT/k6-report.html" K6_WEB_DASHBOARD_OPEN=false \
  k6 run -o experimental-prometheus-rw --tag testid="$NAME" "$PERF_DIR/k6/main.js" 2>&1 | tee "$OUT/k6.log"
K6_EXIT=${PIPESTATUS[0]}
set -e
END=$(date +%s)

if [ "$PG" = 1 ]; then
  remote_sql < "$PERF_DIR/lib/pg_stats.sql" > "$OUT/pg_after.csv" 2>> "$OUT/pg.err" \
    && python3 "$PERF_DIR/lib/tools.py" pgdiff "$OUT/pg_before.csv" "$OUT/pg_after.csv" "$OUT/slow_queries.csv" \
    && rm "$OUT/pg_before.csv" "$OUT/pg_after.csv"
fi
[ -s "$OUT/pg.err" ] || rm -f "$OUT/pg.err"

GIT_SHA="$(git -C "$PERF_DIR" rev-parse --short HEAD)"
git -C "$PERF_DIR" diff --quiet -- . || GIT_SHA="$GIT_SHA(+perf 수정)"
cat > "$OUT/meta.json" <<JSON
{
  "test": "$TEST",
  "load": "$LOAD",
  "note": $(jq -Rn --arg v "$NOTE" '$v'),
  "started_at": "$(TZ=Asia/Seoul date -r "$START" +%Y-%m-%dT%H:%M:%S+09:00)",
  "ended_at": "$(TZ=Asia/Seoul date -r "$END" +%Y-%m-%dT%H:%M:%S+09:00)",
  "start_epoch": $START,
  "end_epoch": $END,
  "api_tag": "$API_TAG",
  "notification_tag": "$NOTIFICATION_TAG",
  "base_url": "$BASE_URL",
  "member_flow": $MEMBER,
  "k6_exit_code": $K6_EXIT,
  "k6_version": $(k6 version | head -1 | jq -Rs 'rtrimstr("\n")'),
  "perf_git_sha": "$GIT_SHA",
  "data_json_sha256": "$(shasum -a 256 "$PERF_DIR/k6/data/data.json" | cut -c1-16)",
  "prometheus_testid": "$NAME"
}
JSON

echo "== 결과 모으기 (Prometheus 마지막 수집을 15초 기다려요)"
sleep 15
"$PERF_DIR/collect.sh" "$OUT"

echo
echo "== 끝: $OUT  (k6 종료 코드 $K6_EXIT: 0 = 합격 기준 통과, 99 = 기준 넘음)"
echo "문서 「결과 기록」 표에 붙일 줄:"
python3 "$PERF_DIR/lib/tools.py" row "$OUT"
