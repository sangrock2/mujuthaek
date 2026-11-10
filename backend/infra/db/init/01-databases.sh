#!/bin/bash
# 컨테이너를 처음 만들 때(볼륨이 비었을 때) 한 번만 실행돼요.
# 프로그램마다 DB와 사용자를 따로 둬요: collector, extraction, api (알림 notification은 03-notification.sh)
set -euo pipefail

create_db() {
  local db=$1 user=$2 password=$3
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
    create role ${user} login password '${password}';
    create database ${db} owner ${user};
SQL
  # PostGIS는 슈퍼유저만 설치할 수 있어서 여기서 미리 깔아둬요
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" -c "create extension if not exists postgis;"
}

create_db api api_app "$API_DB_PASSWORD"
create_db collector collector_app "$COLLECTOR_DB_PASSWORD"
create_db extraction extraction_app "$EXTRACTION_DB_PASSWORD"
