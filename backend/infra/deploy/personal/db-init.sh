#!/bin/bash
set -euo pipefail
# Passwords never appear in psql's argument list (visible in the process table): psql reads each one from the
# container environment it already has, by variable name (\getenv, psql 15+).
for db in api notification collector extraction; do
  variable="${db^^}_DB_PASSWORD"
  : "${!variable:?$variable is required}"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    --set="db=$db" --set="role=${db}_app" --set="password_variable=$variable" <<'SQL'
\getenv password :password_variable
CREATE ROLE :"role" LOGIN PASSWORD :'password';
CREATE DATABASE :"db" OWNER :"role";
SQL
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
done
