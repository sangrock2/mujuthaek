#!/usr/bin/env bash
# 운영 서버 쪽 성능 테스트 준비.
#   perf/server.sh exporters-up     node-exporter·cAdvisor 켜기 (compose profile perf)
#   perf/server.sh exporters-down   끄기 (테스트가 다 끝나면)
#   perf/server.sh version          지금 떠 있는 서비스 버전 (versions.env)
#   perf/server.sh check            pg_stat_statements가 켜져 있는지, DB에 붙는지
source "$(dirname "$0")/lib/common.sh"

compose="docker compose -f compose.prod.yml --env-file .env --env-file versions.env --profile perf"

case "${1:-}" in
  exporters-up) remote "cd $REMOTE_DIR && $compose up -d node-exporter cadvisor && $compose ps node-exporter cadvisor" ;;
  exporters-down) remote "cd $REMOTE_DIR && $compose stop node-exporter cadvisor && $compose rm -f node-exporter cadvisor" ;;
  version) remote_versions ;;
  check)
    echo "select current_database() as db, current_user as db_user,
            exists(select 1 from pg_extension where extname = 'pg_stat_statements') as pg_stat_statements;" | remote_sql
    ;;
  *) sed -n '2,7p' "$0"; exit 1 ;;
esac
