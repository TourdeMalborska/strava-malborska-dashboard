# Secrets inventory — Tour de Malborska

This document is the single source of truth for **which** secrets the project
uses, **where** they are consumed, and **how** they map to the Infisical
project `tourdemalborska`.

> Values are never recorded here. This is a key-name inventory only.

## Management model

- **Source of truth:** Infisical project `tourdemalborska` (Cloud, **EU** —
  `https://eu.infisical.com`).
- **Single environment: `prod`.** The project has only one real credential set
  (live Strava app, live Supabase), so all secrets live in the `prod`
  environment. The `dev` and `staging` environments are intentionally left
  empty — there is no separate test Strava/Supabase to populate them, and
  storing placeholders there only creates confusion.
- **Distribution:** push/sync for hosted platforms. Infisical pushes secrets
  into Vercel and GitHub so the application and the CI workflow keep reading
  plain environment variables. No code or workflow changes are required to
  consume them.
- **Local development: pull at runtime.** Local runs use `infisical run`, which
  injects `prod/app` secrets into the process. No local `.env` is kept (see
  "Local development" below).
- **No runtime fetch in production:** neither the Vercel function nor the
  GitHub Actions job calls Infisical at runtime, so Infisical is never in the
  request/backup hot path.

### Infisical layout

- Project: `tourdemalborska` (EU)
- Environments: `prod` (the only populated one), `dev` / `staging` (empty)
- Folders (in `prod`):
  - `/app`    → application runtime secrets, synced to **Vercel**
  - `/backup` → backup workflow secrets, synced to **GitHub Actions**

## `prod/app` — application runtime (synced to Vercel)

Consumed by the FastAPI app (`api/index.py`, `config.py`, `strava.py`,
`coros_mcp.py`). Also the source for local development via `infisical run`.

| Key | Consumed in | Secret? | In Infisical? | Notes |
|---|---|---|---|---|
| `SUPABASE_URL` | `config.py` | secret | ✅ seeded | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | `config.py` | secret | ✅ seeded | Service-role key — server-side only. |
| `STRAVA_CLIENT_ID` | `config.py`, `api/index.py`, `strava.py` | secret | ✅ seeded | Strava OAuth app ID. |
| `STRAVA_CLIENT_SECRET` | `config.py`, `api/index.py`, `strava.py` | secret | ✅ seeded | Strava OAuth app secret. |
| `STRAVA_VERIFY_TOKEN` | `config.py`, `api/index.py` | secret | ✅ seeded | Strava webhook verification token. |
| `STRAVA_REDIRECT_URI` | `config.py` | config | ⬜ TODO | Optional; defaults to the Vercel prod callback. |
| `CRON_SECRET` | `api/index.py` | secret | ⬜ TODO | Bearer token guarding `/sync/daily`. |
| `GITHUB_BACKUP_TOKEN` | `api/index.py` | secret | ⬜ TODO | PAT to dispatch the backup workflow. |
| `COROS_TEST_SECRET` | `api/index.py` | secret | ⬜ TODO | Guards `/test/coros/connection`. |
| `COROS_MCP_URL` | `coros_mcp.py` | config | ⬜ TODO | Optional; defaults to the EU COROS MCP URL. |
| `STRAVA_ACCESS_TOKEN` | `api/index.py` | secret | ⬜ TODO | Test-only (`/activities`); not needed in normal operation. |

> The ⬜ TODO rows currently live only in Vercel's env settings. Add them to
> Infisical `prod/app` so Infisical becomes the complete source of truth, then
> let the Vercel integration push them back.

## `prod/backup` — backup workflow (synced to GitHub Actions)

Consumed by `.github/workflows/backup-supabase.yml` and
`scripts/backup_supabase.sh`. Folder exists in Infisical but is **empty** — add
these as GitHub Actions **secrets** via the integration:

| Key | Consumed in | In Infisical? | Notes |
|---|---|---|---|
| `SUPABASE_DB_URL` | workflow env / `backup_supabase.sh` | ⬜ TODO | Postgres connection string (`malborska_backup` role). |
| `AWS_ACCESS_KEY_ID` | workflow env | ⬜ TODO | S3 upload credentials. |
| `AWS_SECRET_ACCESS_KEY` | workflow env | ⬜ TODO | S3 upload credentials. |
| `NEW_RELIC_LICENSE_KEY` | workflow env | ⬜ TODO | Backup result reporting. |

The following are **non-secret** and should stay as GitHub Actions **variables**
(`vars`), not pushed through Infisical:

| Variable | Consumed in | Notes |
|---|---|---|
| `AWS_REGION` | workflow env / script | S3 region. |
| `S3_BUCKET` | workflow env / script | Backup bucket name. |
| `S3_BACKUP_PREFIX` | workflow env / script | Key prefix inside the bucket. |

## Integration wiring (where each consumer gets its keys)

```
Infisical EU · tourdemalborska · prod
├── /app     ──push──▶ Vercel env vars      ──▶ FastAPI app at runtime
│             └─pull── infisical run        ──▶ local development
└── /backup  ──push──▶ GitHub Actions secrets ─▶ backup-supabase.yml
```

- **Local dev** and **Vercel** consume `prod/app`.
- **GitHub Actions** consumes `prod/backup`.
- The Vercel and GitHub pushes are configured as native integrations in the
  Infisical dashboard (not yet wired — see TODO above).

## Local development

No local `.env` is kept. Secrets are injected at runtime from Infisical:

```powershell
infisical run --env=prod --path=/app -- uvicorn api.index:app --reload
```

Note: because there is only one credential set, local runs use the **live**
`prod` secrets and therefore talk to the real Strava/Supabase. Prefer read-only
endpoints (`/health`, `/athletes`) when testing locally, and be deliberate
about endpoints that write.

If you ever need a local `.env` file (offline work), generate it from Infisical
and keep it gitignored — do not hand-maintain it:

```powershell
infisical export --env=prod --path=/app --format=dotenv > .env
```

`config.py` still calls `load_dotenv()`, so a generated `.env` is picked up
automatically if present; when absent it is a harmless no-op.

See `.env.example` for the key-name template.

## Rotation / offboarding checklist

1. Rotate the value at its origin (Strava, Supabase, AWS IAM, GitHub PAT, etc.).
2. Update it in Infisical (`prod/app` or `prod/backup`).
3. Let the sync push it to Vercel / GitHub (or re-trigger the integration sync).
4. Redeploy Vercel if the runtime needs the new value immediately.
