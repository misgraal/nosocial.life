#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/home/nosocial/app/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
MYSQL_CONTAINER="${MYSQL_CONTAINER:-nosocial-mysql}"

mkdir -p "$BACKUP_DIR"

if [ ! -f .env ]; then
  echo "Missing .env in current directory" >&2
  exit 1
fi

set -a
source .env
set +a

if [ -z "${DB_NAME:-}" ] || [ -z "${DB_USER:-}" ] || [ -z "${DB_PASSWORD:-}" ]; then
  echo "DB_NAME, DB_USER and DB_PASSWORD must be set in .env" >&2
  exit 1
fi

docker exec -e MYSQL_PWD="$DB_PASSWORD" "$MYSQL_CONTAINER" \
  mysqldump -u"$DB_USER" "$DB_NAME" \
  > "$BACKUP_DIR/mysql-$TIMESTAMP.sql"

if [ -d runtime ]; then
  tar -czf "$BACKUP_DIR/runtime-$TIMESTAMP.tar.gz" runtime
fi

find "$BACKUP_DIR" -type f \( -name 'mysql-*.sql' -o -name 'runtime-*.tar.gz' \) -mtime +"$RETENTION_DAYS" -delete

echo "Backup completed: $BACKUP_DIR"
