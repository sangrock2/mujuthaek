#!/usr/bin/env bash
# 서버 지표를 노트북 Prometheus로 가져오는 SSH 터널. 테스트하는 동안 다른 터미널에 켜 둬요(Ctrl+C로 닫아요).
#   노트북 18080 → 서버 api 8080, 18081 → notification 8081, 19100 → node-exporter, 19101 → cAdvisor
source "$(dirname "$0")/lib/common.sh"

key=()
[ -n "$SSH_KEY" ] && key=(-i "$SSH_KEY")
echo "터널: $SSH_USER@$EC2_HOST (Ctrl+C로 닫아요)"
exec ssh ${key[@]+"${key[@]}"} -N \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18080:127.0.0.1:8080 \
  -L 127.0.0.1:18081:127.0.0.1:8081 \
  -L 127.0.0.1:19100:127.0.0.1:9100 \
  -L 127.0.0.1:19101:127.0.0.1:9101 \
  "$SSH_USER@$EC2_HOST"
