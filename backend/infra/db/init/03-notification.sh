#!/bin/bash
# 알림 서버(services/notification) 데이터베이스와 사용자. 새 볼륨이면 처음 뜰 때 자동으로 돌고,
# 이미 있는 볼륨에는 make db-notification으로 한 번 돌려요. 여러 번 돌려도 괜찮아요.
# 비밀번호는 infra/.env의 NOTIFICATION_DB_PASSWORD (없으면 앱 기본값과 같은 notification-pass)
set -euo pipefail

password="${NOTIFICATION_DB_PASSWORD:-notification-pass}"
role_exists=$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -tAc \
  "select 1 from pg_roles where rolname = 'notification_app'")
if [ "$role_exists" != "1" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "create role notification_app login password '${password}';"
fi
db_exists=$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -tAc \
  "select 1 from pg_database where datname = 'notification'")
if [ "$db_exists" != "1" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -c "create database notification owner notification_app;"
fi
