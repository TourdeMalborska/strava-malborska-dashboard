# Secrets inventory — Tour de Malborska

This document is the single source of truth for **which** secrets the project
uses, **where** they are consumed, and **how** they map to the Infisical
project `tourdemalborska`.

> Values are never recorded here. This is a key-name inventory only.

## Management model

- **Source of truth:** Infisical project `tourdemalborska` (Cloud, EU).
- **Distribution:** push/sync. Infisical pushes secrets into each platform so
  the application and the CI workflow keep reading plain environment variables.
  No code or workflow changes are required to consume them.
- **No runtime fetch:** neither the Vercel function nor the GitHub Actions job
  calls Infisical at runtime, so Infisical is never in the request/backup hot
  path.

### Infisical layout

- Project: `tourdemalborska`
- Environments: `dev`, (staging/other), `prod`
- Folders:
  - `/app`    → application runtime secrets, synced to **Vercel**
  - `/backup` → backup workflow secrets, synced to **GitHub Actions**

## `/app` — application runtime (synced to Vercel)

Consumed by the FastAPI app (`api/index.py`, `config.py`, `strava.py`,
`coros_mcp.py`). Also used for local development.

| Key | Consumed in | Secret? | Notes |
|---|---|---|---|
| `SUPABASE_URL` | `config.py` | secret | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | `config.py` | secret | Service-role key — server-side only. |
| `STRAVA_CLIENT_ID` | `config.py`, `api/index.py`, `strava.py` | secret | Strava OAuth app ID. |
| `STRAVA_CLIENT_SECRET` | `config.py`, `api/index.py`, `strava.py` | secret | Strava OAuth app secret. |
| `STRAVA_VERIFY_TOKEN` | `config.py`, `api/index.py` | secret | Strava webhook verification token. |
| `STRAVA_REDIRECT_URI` | `config.py` | config | Optional; defaults to the Vercel prod callback. |
| `CRON_SECRET` | `api/index.py` | secret | Bearer token guarding `/sync/daily`. |
| `GITHUB_BACKUP_TOKEN` | `api/index.py` | secret | PAT to dispatch the backup workflow. |
| `COROS_TEST_SECRET` | `api/index.py` | secret | Guards `/test/coros/connection`. |
| `COROS_MCP_URL` | `coros_mcp.py` | config | Optional; defaults to the EU COROS MCP URL. |
| `STRAVA_ACCESS_TOKEN` | `api/index.py` | secret | Test-only (`/activities`); not needed in normal operation. |

## `/backup` — backup workflow (synced to GitHub Actions)

Consumed by `.github/workflows/backup-supabase.yml` and
`scripts/backup_supabase.sh`.

Push these as GitHub Actions **secrets**:

| Key | Consumed in | Notes |
|---|---|---|
| `SUPABASE_DB_URL` | workflow env / `backup_supabase.sh` | Postgres connection string (`malborska_backup` role). |
| `AWS_ACCESS_KEY_ID` | workflow env | S3 upload credentials. |
| `AWS_SECRET_ACCESS_KEY` | workflow env | S3 upload credentials. |
| `NEW_RELIC_LICENSE_KEY` | workflow env | Backup result reporting. |

The following are **non-secret** and should stay as GitHub Actions **variables**
(`vars`), not pushed as secrets:

| Variable | Consumed in | Notes |
|---|---|---|
| `AWS_REGION` | workflow env / script | S3 region. |
| `S3_BUCKET` | workflow env / script | Backup bucket name. |
| `S3_BACKUP_PREFIX` | workflow env / script | Key prefix inside the bucket. |

## Local development

Preferred (no local `.env`):

```powershell
infisical run --env=dev --path=/app -- uvicorn api.index:app --reload
```

If you must materialize a `.env` (offline work), generate it and keep it
gitignored:

```powershell
infisical export --env=dev --path=/app --format=dotenv > .env
```

See `.env.example` for the key-name template.

## Rotation / offboarding checklist

1. Rotate the value at its origin (Strava, Supabase, AWS IAM, GitHub PAT, etc.).
2. Update it in Infisical (`/app` or `/backup`, correct environment).
3. Let the sync push it to Vercel / GitHub (or re-trigger the integration sync).
4. Redeploy Vercel if the runtime needs the new value immediately.
