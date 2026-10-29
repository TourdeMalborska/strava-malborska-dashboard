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

## Provider identity on athletes (current approach)

For the MVP, additional-provider tokens are stored as nullable columns on the
`athletes` table, mirroring the existing Strava token columns (e.g. a future
`coros_athlete_id`, `coros_access_token`, `coros_refresh_token`,
`coros_expires_at`). This keeps the model simple for a small, fixed set of
providers.

**Planned refactor (at scale):** move to an `athlete_providers` table — one row
per athlete per provider, each with its own tokens and external id. Do this when
the number of providers/linked accounts makes the per-column approach unwieldy
(a natural checkpoint is the COROS > 20 users review).

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
