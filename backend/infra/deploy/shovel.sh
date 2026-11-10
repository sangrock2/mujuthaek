#!/usr/bin/env bash
# 운영 이벤트를 개발 서버로 복사하는 RabbitMQ shovel 설정. 한 번만 손으로 돌려요 (다시 돌려도 같은 결과).
#   운영 서버에서: shovel.sh prod [--mode results|raw] [--recreate]
#                  큐 dev.mirror를 mujuthaek.events에 묶고, 이 큐만 읽는 계정 shovel을 만들어요
#                  results(기본): 운영 추출 결과 extraction.completed·policy.extracted·area.source.ready
#                                 → 개발 api가 운영과 같은 공고·혜택·생활권을 받아요 (개발 추출은 recorded 모드라 새 결과를 못 만들어요)
#                  raw:           수집 원본 raw.notice.collected·raw.policy.collected·area.source.ready → 개발 추출이 처리 (추출을 시험할 때)
#                  모드를 바꿔 다시 돌리면 다른 모드의 바인딩은 풀어요. --recreate는 큐를 지우고 새로 만들어요(쌓인 메시지도 지워져요)
#   개발 서버에서: shovel.sh dev    운영 dev.mirror → 개발 mujuthaek.events로 옮기는 동적 shovel from-prod를 만들어요
# shovel 계정 암호는 실행할 때 입력받아요 (파일·명령 기록에 남기지 않아요). 두 서버에 같은 암호를 넣어요.
# 교환기·라우팅 키는 contracts/와 같아요: mujuthaek.events(topic), 라우팅 키 = eventType.
set -euo pipefail

BASE="${MUJUTHAEK_DIR:-/opt/mujuthaek}"
PROD_HOST="10.20.5.63"
EXCHANGE="mujuthaek.events"
QUEUE="dev.mirror"
RESULT_KEYS=(extraction.completed policy.extracted area.source.ready)
RAW_KEYS=(raw.notice.collected raw.policy.collected area.source.ready)
QUEUE_ARGS='{"x-message-ttl":259200000,"x-max-length":20000}'   # 3일, 2만 건 (개발 서버가 오래 꺼져 있어도 운영이 넘치지 않게)
API="http://127.0.0.1:15672/api"

usage() {
  echo "사용: $0 prod [--mode results|raw] [--recreate]  |  $0 dev" >&2
  exit 2
}
[ $# -ge 1 ] || usage
ROLE="$1"
shift
MODE=results
RECREATE=no
while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      [ $# -ge 2 ] || usage
      MODE="$2"
      shift 2
      ;;
    --recreate)
      RECREATE=yes
      shift
      ;;
    *) usage ;;
  esac
done
case "$ROLE:$MODE" in
  prod:results) ROUTING_KEYS=("${RESULT_KEYS[@]}") ;;
  prod:raw) ROUTING_KEYS=("${RAW_KEYS[@]}") ;;
  dev:results) [ "$RECREATE" = no ] || usage ;;
  *) usage ;;
esac
cd "$BASE"

# 관리 API 계정은 .env의 RABBITMQ_USER·RABBITMQ_PASSWORD (값은 출력하지 않아요)
env_value() {
  local line
  line="$(grep -E "^$1=" .env | tail -n 1)"
  line="${line#*=}"
  line="${line%\"}"
  echo "${line#\"}"
}
ADMIN_USER="$(env_value RABBITMQ_USER)"
ADMIN_PASS="$(env_value RABBITMQ_PASSWORD)"
if [ -z "$ADMIN_USER" ] || [ -z "$ADMIN_PASS" ]; then
  echo ".env에 RABBITMQ_USER·RABBITMQ_PASSWORD가 없어요" >&2
  exit 1
fi

# 관리 API 호출. 계정은 권한 600 임시 설정 파일로, 본문(암호가 들어갈 수 있음)은 표준 입력으로 넘겨 프로세스 목록에 보이지 않게 해요
CURL_CONFIG="$(mktemp)"
chmod 600 "$CURL_CONFIG"
trap 'rm -f "$CURL_CONFIG"' EXIT
printf 'user = "%s:%s"\n' "$ADMIN_USER" "$ADMIN_PASS" > "$CURL_CONFIG"

call() {
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$body" ]; then
    printf '%s' "$body" | curl -fsS -K "$CURL_CONFIG" -X "$method" -H "content-type: application/json" --data-binary @- "$API$path"
  else
    curl -fsS -K "$CURL_CONFIG" -X "$method" "$API$path"
  fi
  echo
}

read -rsp "shovel 계정 암호: " SHOVEL_PASS
echo
[ -n "$SHOVEL_PASS" ] || { echo "암호가 비었어요" >&2; exit 1; }

json() {
  python3 -c 'import json, sys; print(json.dumps(json.loads(sys.argv[1])))' "$1"
}

# 앱이 만드는 교환기와 같은 설정으로 미리 만들어 둬요 (이미 있으면 그대로)
call PUT "/exchanges/%2F/$EXCHANGE" '{"type":"topic","durable":true}'

if [ "$ROLE" = prod ]; then
  if [ "$RECREATE" = yes ]; then
    curl -sS -o /dev/null -K "$CURL_CONFIG" -X DELETE "$API/queues/%2F/$QUEUE" # 없으면 404, 그대로 넘어가요
    echo "큐 ${QUEUE}를 지웠어요 (쌓인 메시지 포함)"
  fi
  call PUT "/queues/%2F/$QUEUE" "{\"durable\":true,\"arguments\":$QUEUE_ARGS}"
  # 고른 모드에 없는 바인딩은 풀어요 (모드를 바꿔 다시 돌릴 때)
  call GET "/queues/%2F/$QUEUE/bindings" \
    | python3 -c '
import json, sys
keep = set(sys.argv[2:])
for b in json.load(sys.stdin):
    if b["source"] == sys.argv[1] and b["routing_key"] not in keep:
        print(b["properties_key"])' "$EXCHANGE" "${ROUTING_KEYS[@]}" \
    | while read -r props; do
      call DELETE "/bindings/%2F/e/$EXCHANGE/q/$QUEUE/$props" > /dev/null
      echo "바인딩 풀기: $props"
    done
  for key in "${ROUTING_KEYS[@]}"; do
    call POST "/bindings/%2F/e/$EXCHANGE/q/$QUEUE" "{\"routing_key\":\"$key\"}"
  done
  user_body="$(SHOVEL_PASS="$SHOVEL_PASS" python3 -c 'import json, os; print(json.dumps({"password": os.environ["SHOVEL_PASS"], "tags": ""}))')"
  call PUT "/users/shovel" "$user_body"
  # dev.mirror만 읽어요. 같은 설정으로 큐를 다시 선언할 수 있게 configure도 그 큐만
  call PUT "/permissions/%2F/shovel" '{"configure":"^dev\\.mirror$","write":"^$","read":"^dev\\.mirror$"}'
  echo "운영 설정 끝($MODE): $QUEUE ← $EXCHANGE (${ROUTING_KEYS[*]}), 계정 shovel"
else
  src_uri="$(SHOVEL_PASS="$SHOVEL_PASS" python3 -c 'import os, urllib.parse; print("amqp://shovel:" + urllib.parse.quote(os.environ["SHOVEL_PASS"], safe="") + "@'"$PROD_HOST"':5672")')"
  body="$(SRC_URI="$src_uri" python3 -c '
import json, os, sys
print(json.dumps({"value": {
    "src-protocol": "amqp091", "src-uri": os.environ["SRC_URI"], "src-queue": sys.argv[1], "src-queue-args": json.loads(sys.argv[2]),
    "dest-protocol": "amqp091", "dest-uri": "amqp://", "dest-exchange": sys.argv[3],
    "ack-mode": "on-confirm", "reconnect-delay": 30,
}}))' "$QUEUE" "$(json "$QUEUE_ARGS")" "$EXCHANGE")"
  call PUT "/parameters/shovel/%2F/from-prod" "$body"
  echo "개발 설정 끝: 운영 $QUEUE → 개발 $EXCHANGE (라우팅 키 그대로). 상태: 관리 화면 Admin → Shovel Status"
fi
