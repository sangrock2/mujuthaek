#!/usr/bin/env bash
# 테스트용: 묶음 시각(08:00·18:00)이나 조용한 시간을 기다리는 발송 줄을 지금 보내도록 당겨요. 로컬 DB에서만 쓰세요.
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
docker compose -f "$dir/../../../infra/docker-compose.yml" --env-file "$dir/../../../infra/.env" \
  exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d notification -c "update deliveries set scheduled_at = now() where status = '\''PENDING'\''"'
echo "5초 안에 워커가 보내요"
