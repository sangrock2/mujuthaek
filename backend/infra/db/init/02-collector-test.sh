#!/bin/bash
# collector 실제 DB 테스트용 데이터베이스 (services/collector/tests/test_storage_postgres.py). 테스트가 테이블을 비워요.
# 새 볼륨이면 처음 뜰 때 자동으로 돌고, 이미 있는 볼륨에는 make migrate-collector-test가 다시 불러요. 여러 번 돌려도 괜찮아요.
set -euo pipefail

exists=$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -tAc \
  "select 1 from pg_database where datname = 'collector_test'")
if [ "$exists" != "1" ]; then
  # 사용자는 collector_app을 같이 써요 (01-databases.sh가 만들어요)
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -c "create database collector_test owner collector_app;"
fi
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname collector_test -c "create extension if not exists postgis;"
