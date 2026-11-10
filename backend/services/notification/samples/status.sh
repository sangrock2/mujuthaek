#!/usr/bin/env bash
# 최근 발송 줄 상태 (주소는 보여 주지 않아요)
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
docker compose -f "$dir/../../../infra/docker-compose.yml" --env-file "$dir/../../../infra/.env" \
  exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d notification -c "select type, status, digest, to_char(scheduled_at at time zone '\''Asia/Seoul'\'', '\''MM-DD HH24:MI'\'') as scheduled_kst, attempts, last_error, provider_message_id from deliveries order by created_at desc limit 12"'
