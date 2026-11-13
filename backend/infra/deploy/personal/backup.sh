#!/bin/bash
set -euo pipefail
cd /opt/mujuthaek-source/backend/infra/deploy/personal
umask 077
mkdir -p runtime/backups
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
for db in api notification collector extraction; do
  docker compose --env-file .env --env-file versions.env -f compose.prod.yml exec -T postgres \
    pg_dump -U postgres -Fc "$db" > "runtime/backups/${db}-${timestamp}.dump.tmp"
  mv "runtime/backups/${db}-${timestamp}.dump.tmp" "runtime/backups/${db}-${timestamp}.dump"
  python3 backup_upload.py "runtime/backups/${db}-${timestamp}.dump"
done
# S3 backups expire after the approved 30 days. Local copies remain until reviewed.
