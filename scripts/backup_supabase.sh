
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${SUPABASE_DB_URL:?Missing SUPABASE_DB_URL}"
: "${AWS_REGION:?Missing AWS_REGION}"
: "${S3_BUCKET:?Missing S3_BUCKET}"
: "${S3_BACKUP_PREFIX:?Missing S3_BACKUP_PREFIX}"

export PGSSLMODE=require
export PGCONNECT_TIMEOUT=20

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

STAMP="$(date -u +%Y-%m-%d_%H%M%S)"
NAME="malborska_${STAMP}"
DIR="$WORKDIR/$NAME"
mkdir -p "$DIR"

echo "Checking database identity..."

DB_USER="$(psql "$SUPABASE_DB_URL" -X -At \
  -v ON_ERROR_STOP=1 \
  -c 'SELECT current_user')"

if [ "$DB_USER" != "malborska_backup" ]; then
  echo "ERROR: Unexpected database user: $DB_USER"
  exit 1
fi

echo "Checking required tables..."

psql "$SUPABASE_DB_URL" -X \
  -v ON_ERROR_STOP=1 -At \
  -c "
SELECT CASE WHEN
  (SELECT count(*) FROM pg_tables
   WHERE schemaname = 'public'
     AND tablename IN
       ('activities','athletes','families','webhook_events','athlete_providers')) = 5
THEN 'OK' ELSE 'ERROR' END;
" | grep -qx "OK"

echo "Exporting PostgreSQL database..."

pg_dump "$SUPABASE_DB_URL" \
  --format=custom \
  --schema=public \
  --enable-row-security \
  --no-owner \
  --no-acl \
  --file="$DIR/database.dump"

echo "Checking dump structure..."

pg_restore --list "$DIR/database.dump" \
  > "$DIR/dump_contents.txt"

for TABLE in activities athletes families webhook_events athlete_providers; do
  if ! grep -Eq "TABLE DATA public ${TABLE} " \
    "$DIR/dump_contents.txt"; then
    echo "ERROR: Missing table data: $TABLE"
    exit 1
  fi
done

if ! grep -Eq \
  "SEQUENCE SET public webhook_events_id_seq " \
  "$DIR/dump_contents.txt"; then
  echo "ERROR: Missing sequence state"
  exit 1
fi

echo "Exporting role metadata..."

psql "$SUPABASE_DB_URL" -X \
  -v ON_ERROR_STOP=1 --csv \
  -c "
SELECT rolname, rolcanlogin, rolinherit,
       rolcreatedb, rolcreaterole, rolbypassrls
FROM pg_roles
ORDER BY rolname;
" > "$DIR/roles.csv"

echo "Exporting grant metadata..."

psql "$SUPABASE_DB_URL" -X \
  -v ON_ERROR_STOP=1 --csv \
  -c "
SELECT grantee, table_schema, table_name,
       privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
ORDER BY table_name, grantee, privilege_type;
" > "$DIR/grants.csv"

echo "Creating archive..."

tar -czf "$WORKDIR/$NAME.tar.gz" \
  -C "$WORKDIR" "$NAME"

cd "$WORKDIR"
sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256"

PREFIX="${S3_BACKUP_PREFIX#/}"
PREFIX="${PREFIX%/}"

echo "Uploading archive to S3..."

aws s3 cp "$NAME.tar.gz" \
  "s3://$S3_BUCKET/$PREFIX/$NAME.tar.gz" \
  --region "$AWS_REGION" \
  --no-progress

echo "Uploading checksum..."

aws s3 cp "$NAME.tar.gz.sha256" \
  "s3://$S3_BUCKET/$PREFIX/$NAME.tar.gz.sha256" \
  --region "$AWS_REGION" \
  --no-progress

echo "BACKUP UPLOAD COMPLETED: $NAME"
