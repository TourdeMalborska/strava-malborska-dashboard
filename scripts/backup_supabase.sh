
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
  -v ON_ERROR_STOP=1 -c 'SELECT current_user')"

if [ "$DB_USER" != "malborska_backup" ]; then
  echo "Unexpected database user: $DB_USER"
  exit 1
fi

echo "Checking public tables and RLS..."
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 \
  -c "
SELECT c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       has_table_privilege(
         current_user, c.oid, 'SELECT'
       ) AS can_select
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r','p')
ORDER BY c.relname;
"

echo "Exporting schema..."
pg_dump "$SUPABASE_DB_URL" \
  --schema=public \
  --schema-only \
  --no-owner \
  --no-acl \
  --file="$DIR/schema.sql"

echo "Exporting data with RLS..."
pg_dump "$SUPABASE_DB_URL" \
  --schema=public \
  --data-only \
  --enable-row-security \
  --inserts \
  --no-owner \
  --no-acl \
  --file="$DIR/data.sql"

echo "Exporting role metadata..."
psql "$SUPABASE_DB_URL" -X \
  -v ON_ERROR_STOP=1 \
  --csv \
  -c "
SELECT rolname, rolcanlogin, rolinherit,
       rolcreatedb, rolcreaterole,
       rolbypassrls
FROM pg_roles
ORDER BY rolname;
" > "$DIR/roles.csv"

echo "Exporting grant metadata..."
psql "$SUPABASE_DB_URL" -X \
  -v ON_ERROR_STOP=1 \
  --csv \
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

sha256sum "$WORKDIR/$NAME.tar.gz" \
  > "$WORKDIR/$NAME.tar.gz.sha256"

PREFIX="${S3_BACKUP_PREFIX#/}"
PREFIX="${PREFIX%/}"

echo "Uploading archive..."
aws s3 cp "$WORKDIR/$NAME.tar.gz" \
  "s3://$S3_BUCKET/$PREFIX/$NAME.tar.gz" \
  --region "$AWS_REGION" \
  --no-progress

echo "Uploading checksum..."
aws s3 cp "$WORKDIR/$NAME.tar.gz.sha256" \
  "s3://$S3_BUCKET/$PREFIX/$NAME.tar.gz.sha256" \
  --region "$AWS_REGION" \
  --no-progress

echo "Checking S3 objects..."
aws s3 ls "s3://$S3_BUCKET/$PREFIX/" \
  --region "$AWS_REGION" | grep -F "$NAME.tar.gz"

echo "BACKUP UPLOAD COMPLETED: $NAME"
