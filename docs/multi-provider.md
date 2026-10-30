# Multi-provider data model

## Context

Tour de Malborska started as a Strava-only club ranking. Athletes increasingly
use other devices/platforms (COROS, Garmin, Wahoo, SRAM Hammerhead Karoo). The
app needs to record **where each activity came from** so it can:

1. **Dedup across providers.** The same ride often reaches multiple platforms
   (e.g. a COROS device auto-uploads to Strava). Without provenance the ranking
   would double-count kilometers.
2. **Measure per-source volume.** Product decisions depend on it — e.g. revisit
   the COROS integration approach (MCP vs Partner API) once COROS users > 20.
3. **Debug and build trust.** When a number looks wrong, the first question is
   which provider produced it.

## The `source` field

`activities.source` (text, NOT NULL, default `'strava'`) records the ingesting
provider. Allowed values are constrained by a CHECK: `strava`, `coros`,
`garmin`, `wahoo`. Extend the CHECK as providers are added.

- Added by migration `migrations/001_add_activity_source.sql`.
- Stamped in each provider's save path (`strava.py` sets `source='strava'`).
- Existing rows backfilled to `'strava'` (all pre-dated multi-provider support).

## Provider identity model (current, as of migration 002)

Identity is provider-neutral and app-owned:

- **`athletes`** — the canonical person, keyed by `athlete_id` (uuid,
  `gen_random_uuid()`). Holds only display/profile fields, never tokens.
- **`athlete_providers`** — one row per (athlete × provider): `provider`,
  `provider_user_id`, `access_token`, `refresh_token`, `expires_at`, `scope`,
  `status`, `last_sync`. Unique on `(provider, provider_user_id)`. This is where
  all tokens live.
- **`activities.athlete_id`** — canonical link (plus `source` for provenance).
- **`oauth_states`** — short-lived PKCE/state store for OAuth round-trips.

Per model B, each provider authorization creates its OWN `athletes` row;
duplicate people across providers are accepted for now (reconciliation later via
name/email match).

### Access & RLS

- The application accesses Supabase only via the **service-role key**, which
  bypasses RLS.
- **Google Looker/Data Studio** reads via a **dedicated DB account through a
  reporting view** — never the base tables directly, and never the token tables.
- `athlete_providers` and `oauth_states` hold secrets, so migration 002 enables
  (and forces) RLS on them with **no anon/authenticated policies** and revokes
  those roles' grants → service-role-only. Reporting is unaffected (it reads a
  view, not these tables).

### Reporting-view dependency (constraint on cleanup migration 003)

Looker/Data Studio reads a dedicated reporting view. Before migration 003 drops
the legacy columns (`athletes.strava_athlete_id` + inline tokens,
`activities.strava_athlete_id`), confirm the view does not reference them. If it
does, rewrite the view to use the canonical `athlete_id` first. Inspect with:

```sql
select table_name, view_definition
from information_schema.views where table_schema = 'public';
```

## COROS integration approach (decision log)

COROS exposes two integration surfaces:

- **COROS MCP** (`https://mcpeu.coros.com/mcp` for EU accounts): OAuth 2.0,
  per-user (single-user) scope, polling (no webhooks). No application/approval
  required — can start immediately. Designed primarily for AI assistants, so
  using it for unattended server-side batch ingestion is somewhat against the
  grain (session-based JSON-RPC tool calls rather than a plain REST API, and an
  OAuth model oriented at AI clients). Access tokens last 30 days; refresh
  tokens 180 days, rotating on each refresh.
- **COROS Partner API**: the platform-oriented integration (REST, two-way sync,
  webhooks, GPX). Architecturally correct for a multi-athlete ingestion
  backend, but requires applying for and being granted Partner API access.

**Decision (MVP):** start with COROS MCP because it needs no approval and the
expected COROS user count is small. Record `source='coros'` on ingested
activities. **Re-evaluate MCP vs Partner API when COROS users > 20.**

No sync-duration / call-duration tracking is needed at this scale (a handful of
users polled once daily); provenance (`source`) is the metric that matters.
