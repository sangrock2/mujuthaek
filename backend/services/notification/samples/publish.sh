#!/usr/bin/env bash
# 테스트 알림 메시지를 RabbitMQ(mujuthaek.events)에 넣어요. 알림 서버가 받아서 메일을 보내요.
#
#   ./samples/publish.sh 받을주소@example.com            # 6개 모두
#   ./samples/publish.sh 받을주소@example.com 3 5        # 3번·5번만
#
# 실행할 때마다 eventId·dedupKey가 새로 만들어져서 여러 번 보내도 매번 새 메일이 가요.
# 1·2번(새 공고·새 정책)은 08:00·18:00 묶음이라 바로 안 가요. 바로 보려면 ./samples/send-now.sh
set -euo pipefail

email="${1:?받을 주소를 넣어 주세요 (SES 샌드박스면 인증한 주소)}"
shift
picks=("$@")

dir="$(cd "$(dirname "$0")" && pwd)"
env_file="$dir/../../../infra/.env"
[[ -f "$env_file" ]] && set -a && source "$env_file" && set +a
user="${RABBITMQ_USER:-mujuthaek}"
pass="${RABBITMQ_PASSWORD:-mq-pass}"
user_id="${NOTIFICATION_TEST_USER_ID:-0192b6f0-0000-7000-8000-0000000000a1}"
run="$(date +%Y%m%d%H%M%S)"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

for file in "$dir"/[1-6]-*.json; do
  n="$(basename "$file" | cut -d- -f1)"
  if (( ${#picks[@]} > 0 )) && [[ ! " ${picks[*]} " == *" $n "* ]]; then
    continue
  fi
  body="$(sed -e "s/__EVENT_ID__/$(uuidgen | tr 'A-Z' 'a-z')/" -e "s/__NOW__/$now/" \
    -e "s/__RUN__/$run/" -e "s/__USER_ID__/$user_id/" -e "s/__EMAIL__/$email/" "$file")"
  result="$(jq -n --arg payload "$body" \
      '{properties: {content_type: "application/json"}, routing_key: "notification.requested",
        payload: $payload, payload_encoding: "string"}' |
    curl -s -u "$user:$pass" -H 'content-type: application/json' -d @- \
      'http://localhost:15672/api/exchanges/%2F/mujuthaek.events/publish')"
  if [[ "$(jq -r '.routed' <<<"$result")" == "true" ]]; then
    echo "보냄: $(basename "$file")"
  else
    echo "못 보냄: $(basename "$file") → $result (알림 서버를 한 번 띄워서 큐를 만들었는지 확인)" >&2
  fi
done
