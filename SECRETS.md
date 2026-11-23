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
  - `/backup` → reserved for backup secrets (currently unused, see below)

### Ownership domains (who manages which Vercel env vars)

Vercel's Production env holds three distinct groups. Keeping them separate is
the core of the architecture:

1. **Infisical-owned (app secrets):** the app's own Strava/Supabase/cron/GitHub/
   Garmin/COROS keys. Infisical is the source of truth and pushes these to
   Vercel. See `prod/app` below.
2. **Vercel–Supabase integration-owned:** `POSTGRES_*`, `NEXT_PUBLIC_*`,
   `SUPABASE_ANON/JWT/SECRET/PUBLISHABLE_*`. Auto-managed by the integration —
   Infisical must leave these alone.
3. **GitHub Actions-owned (backup):** lives in the repo, not Vercel. See
   the backup section below.

## `prod/app` — application runtime (synced to Vercel)

Consumed by the FastAPI app (`api/index.py`, `config.py`, `strava.py`,
`coros.py`, `coros_mcp.py`, `wahoo.py`, `hammerhead.py`, `garmin.py`). Also the source for local development via `infisical run`.

These are the application's **own** secrets — Infisical owns them and pushes
them into Vercel. (This is distinct from the Vercel–Supabase integration vars,
which Infisical must NOT manage — see the section below.)

| Key | Consumed in | Vercel type | In Infisical? | In Vercel? | Notes |
|---|---|---|---|---|---|
| `SUPABASE_URL` | `config.py` | Config | ✅ seeded | ✅ | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | `config.py` | Secret | ✅ seeded | ✅ | Service-role key — server-side only. |
| `STRAVA_CLIENT_ID` | `config.py`, `api/index.py`, `strava.py` | Secret | ✅ seeded | ✅ | Strava OAuth app ID. |
| `STRAVA_CLIENT_SECRET` | `config.py`, `api/index.py`, `strava.py` | Secret | ✅ seeded | ✅ | Strava OAuth app secret. |
| `STRAVA_VERIFY_TOKEN` | `config.py`, `api/index.py` | Secret | ✅ seeded | ✅ | Strava webhook verification token. |
| `STRAVA_REDIRECT_URI` | `config.py` | Config | ✅ added | ✅ | Optional; defaults to the Vercel prod callback. |
| `CRON_SECRET` | `api/index.py` | Secret | ✅ added | ✅ | Bearer token guarding `/sync/daily`. |
| `GITHUB_BACKUP_TOKEN` | `api/index.py` | Secret | ✅ added | ✅ | PAT to dispatch the backup workflow. |
| `GARMIN_API_KEY` | `garmin.py` | Secret | ✅ added | ✅ | Garmin Personal API key. |
| `GARMIN_HOST` | `garmin.py` | Config | ⬜ optional | — | Defaults to `https://personal.connectapi.garmin.com`. |
| `COROS_CLIENT_ID` | `coros.py` | Config | ✅ added | ✅ | Public OAuth client ID (PKCE, no client secret). |
| `COROS_REDIRECT_URI` | `coros.py` | Config | ✅ added (not in Vercel) | — (default used) | Optional; defaults to the prod callback. Must match COROS registration. |
| `COROS_TEST_SECRET` | `api/index.py` | Secret | ⬜ optional | ❌ missing | Guards `/test/coros/connection`. Intentionally unset: endpoint fails closed (503). PoC; candidate for removal. |
| `COROS_MCP_URL` | `coros.py`, `coros_mcp.py` | Config | ✅ added (not in Vercel) | — (default used) | Optional; defaults to the EU COROS MCP URL. |
| `WAHOO_CLIENT_ID` | `wahoo.py` | Secret | ✅ added | ✅ | Wahoo OAuth app ID. |
| `WAHOO_CLIENT_SECRET` | `wahoo.py` | Secret | ✅ added | ✅ | Wahoo OAuth app secret. |
| `WAHOO_REDIRECT_URI` / `WAHOO_HOST` | `wahoo.py` | Config | ⬜ optional | — | Default to the prod callback / `https://api.wahooligan.com`. |
| `HAMMERHEAD_CLIENT_ID` | `hammerhead.py` | Secret | ✅ added | ✅ | Hammerhead OAuth app ID. |
| `HAMMERHEAD_CLIENT_SECRET` | `hammerhead.py` | Secret | ✅ added | ✅ | Hammerhead OAuth app secret. |
| `HAMMERHEAD_REDIRECT_URI` | `hammerhead.py` | Config | ⬜ optional | — | Defaults to the prod callback. |
| `SUPPORT_EMAIL` | `api/index.py` | Config | ✅ added | ✅ | Contact email on `/support`; falls back to the school website. |
| `STRAVA_ACCESS_TOKEN` | `api/index.py` | Secret | ⬜ optional | ❌ missing | Test-only (`/activities`); not needed in normal operation. |

**Reserved / future keys in Infisical `prod/app`** (no code reads them yet):
`POLAR_CLIENT_ID`, `POLAR_CLIENT_SECRET` (Polar integration).

**Not yet synced:** the Infisical → Vercel sync is OFF by decision. Before enabling
it: (1) exclude `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`, which in Vercel are
owned by the Supabase integration; (2) `COROS_MCP_URL` and `COROS_REDIRECT_URI`
exist in Infisical but not in Vercel, so enabling the sync would push them. Make
sure their values equal the code defaults first.
## Vercel–Supabase integration vars (NOT managed by Infisical)

When Supabase is connected to Vercel, the integration automatically injects the
following into the Vercel project. **Infisical must not own or push these** —
doing so would conflict with the integration, which overwrites them on its own
schedule. Leave them entirely to the Vercel–Supabase integration.

- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_SUPABASE_URL`
- `POSTGRES_DATABASE`
- `POSTGRES_HOST`
- `POSTGRES_PASSWORD`
- `POSTGRES_PRISMA_URL`
- `POSTGRES_URL`
- `POSTGRES_URL_NON_POOLING`
- `POSTGRES_USER`
- `SUPABASE_ANON_KEY`
- `SUPABASE_JWT_SECRET`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`

Notes:
- The current FastAPI code only reads `SUPABASE_URL` and
  `SUPABASE_SERVICE_ROLE_KEY` from this provider; it does not use the
  `POSTGRES_*` or `NEXT_PUBLIC_*` vars. Those exist because the integration adds
  a full set by default.
- `POSTGRES_URL` / `POSTGRES_URL_NON_POOLING` are the direct Postgres connection
  strings. The backup workflow's `SUPABASE_DB_URL` (in GitHub, see below) is a
  dedicated connection string for the restricted `malborska_backup` role — keep
  it separate; do not reuse an integration-managed URL for backups.

## Backup workflow secrets (managed directly in GitHub)

Consumed by `.github/workflows/backup-supabase.yml` and
`scripts/backup_supabase.sh`. **Decision:** these are managed directly as GitHub
Actions **secrets**, NOT synced from Infisical. GitHub cannot reveal stored
values, so syncing would require rotating all four credentials for little gain.
The Infisical `/backup` folder is intentionally unused. Revisit when these
credentials are next rotated (then store the new values in Infisical `prod/backup`
and enable the GitHub integration).

| Key | Consumed in | Where managed | Notes |
|---|---|---|---|
| `SUPABASE_DB_URL` | workflow env / `backup_supabase.sh` | ✅ GitHub secret | Postgres connection string (`malborska_backup` role). |
| `AWS_ACCESS_KEY_ID` | workflow env | ✅ GitHub secret | S3 upload credentials. |
| `AWS_SECRET_ACCESS_KEY` | workflow env | ✅ GitHub secret | S3 upload credentials. |
| `NEW_RELIC_LICENSE_KEY` | workflow env | ✅ GitHub secret | Backup result reporting. |
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
└── /backup  (unused; backup secrets live directly in GitHub Actions secrets)
```

- **Local dev** and **Vercel** consume `prod/app`.
- **GitHub Actions** uses its own secrets (see the backup section above).
- The Infisical → Vercel push is a native integration configured in the
  Infisical dashboard.

## Local development

No local `.env` is kept. Secrets are injected at runtime from Infisical:

```powershell
infisical run --env=prod --path=/app -- uvicorn api.index:app --reload
```

Manual COROS debugging scripts live in `scripts/` (`coros_connect_test.py`,
`coros_detail_test.py`); run them from the repo root, e.g.
`infisical run --env=prod --path=/app -- python scripts/coros_detail_test.py`.

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
