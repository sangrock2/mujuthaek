#!/bin/bash
set -euo pipefail
for db in api notification collector extraction; do
  variable="${db^^}_DB_PASSWORD"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    --set="db=$db" --set="role=${db}_app" --set="password=${!variable}" <<'SQL'
CREATE ROLE :"role" LOGIN PASSWORD :'password';
CREATE DATABASE :"db" OWNER :"role";
SQL
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
done
