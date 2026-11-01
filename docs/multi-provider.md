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

### Backups

Backups run as the restricted `malborska_backup` role via
`pg_dump --enable-row-security`, so a table is only dumped if that role has a
SELECT policy on it.

- **`athlete_providers` IS backed up.** It now holds the OAuth tokens that used
  to live inline on `athletes` (already backed up), so excluding it would
  silently regress disaster recovery (a restore would disconnect every
  athlete). Migration 002 grants SELECT + a `malborska_backup` policy, and
  `scripts/backup_supabase.sh` includes it in the table-count check (now 5) and
  the data-presence loop.
- **`oauth_states` is NOT backed up.** Ephemeral 15-minute PKCE rows, no
  recovery value, kept service-role-only.

Consequence: S3 backups contain live OAuth tokens (as they already did via the
inline `athletes` columns). Keep S3 backup access controlled accordingly.

## Garmin integration approach (decision log)

Garmin exposes two relevant surfaces:

- **Personal API** (`garmin.py`, implemented): a single-account API keyed by a
  Personal API key created on ONE Garmin Connect account. It reads only THAT
  account's data. No per-user OAuth, no approval. Token flow: `POST
  .../personal-api/personal-api-key/token` with `Authorization: ApiKey <key>`
  returns a bearer JWT **as plain text**; data via `GET
  .../activitylist-service/activities/search/activities` with
  `Authorization: Bearer <token>` returns **structured JSON** (distance in
  metres, duration in seconds — no prose parsing, unlike COROS).
- **Connect Developer Program / Activity API** (future, not implemented):
  per-user OAuth with end-user consent, up to 1,000 users on Starter Access —
  the correct path for onboarding many club athletes. Requires applying for and
  being granted Developer Program access.

**Decision (option 3):** start with the **Personal API as a single-athlete
pilot** (validates the data shape and the `source='garmin'` path using the
owner's own account), and pursue the **Developer Program** for true
multi-athlete onboarding later. The Personal API genuinely cannot onboard other
club members — each would need their own key — so it is a plumbing/data-shape
validation, not a club feature.

Implementation notes:
- API key lives in Infisical (prod/app) as `GARMIN_API_KEY`. Not stored in the DB.
- The bearer token is derived on demand each sync from the API key (no
  per-athlete token persisted), keyed by a constant `provider_user_id`
  (`garmin_personal_self`) via `garmin.ensure_personal_link()`.
- Verified live: token exchange + activity search both reachable and working
  from the dev environment (Garmin is not blocked by the corporate proxy).

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

## Wahoo integration (decision log + distance limitation)

Wahoo Cloud API (https://cloud-api.wahooligan.com/) is OAuth 2.0 (confidential
client for our app — client secret, no PKCE), clean REST/JSON, per-user like
Strava. Implemented in `wahoo.py`:
- authorize/token at `api.wahooligan.com/oauth/{authorize,token}`
- identity/profile via `GET /v1/user` (fields: `first`, `last`, `gender`,
  `birth`, `height`, `weight`; NO `email`)
- activities via `GET /v1/workouts` (list: `id`, `name`, `starts`, `minutes`,
  `workout_type_id`, inline `workout_summary`)
- scopes `user_read workouts_read`; current app is **SANDBOX** (test rate
  limits; a sandbox app cannot convert to production — a separate production app
  is needed for real multi-athlete use).

### KEY LIMITATION: no distance for third-party-origin workouts

Wahoo's policy (changelog 2025-04-01: Wahoo no longer shares workout summaries
created by third-party apps) means `workout_summary` — which holds
`distance_accum`, speed, elevation, etc. — is **null / 401** for any workout
that originated in another app. Verified live: a test account whose 30 workouts
all had `fitness_app_id = 1085` (a third-party source) returned NO summary and
NO distance on any workout, via both the inline field and the
`/v1/workouts/{id}/workout_summary` endpoint (401 "not authorized to view this
workout summary").

Consequence for a distance ranking:
- Wahoo yields `minutes` (duration), type, name — but **distance only for
  workouts recorded natively on a Wahoo device** (ELEMNT etc.), which carry a
  populated summary.
- The integration is correct and future-proof: `normalize_activity` returns
  `distance = None` when the summary is absent, so no bad data is stored; such
  activities simply don't contribute km until a real-distance workout exists.
- **TODO (verify):** test with an activity recorded on a native Wahoo device to
  confirm `workout_summary.distance_accum` is populated and km flow through.
- **Possible future workaround:** download the raw `.fit` file
  (`/v1/workout_file_uploads` / FIT) and parse distance from it — significantly
  more work (binary parsing); only pursue if native-device coverage proves
  insufficient.

### Wahoo workout_type_id mapping (from live data)

- `0`  = outdoor cycling  -> counts toward the ranking
- `1`  = running
- `12` = MyWhoosh / indoor-virtual ride -> EXCLUDED (simulated distance)
- `26` = swimming
Refine against Wahoo's full workout-type reference as needed.

## Backlog: post-authorization UX

After a successful provider authorization, the app currently returns the user
to the connect page (`/`) with a provider-aware success message (fixed from the
old behavior that bounced everyone to strava.com). Open decision on the ideal
destination:
- Recommended: a "connected" confirmation that keeps the user in the app and
  offers next steps — primary "Zobacz ranking" (view ranking) + secondary
  "Połącz kolejne konto" (connect another provider).
- Needs: the public ranking URL (Looker/Data Studio report, or the future
  `tdm.szkolaprzymalborskiej.pl`) to wire the "view ranking" button.
- NOT recommended: returning the user to the provider's own site — the user's
  destination is the Tour de Malborska ranking, not Wahoo/Strava/Garmin.

## Wahoo: duplicate records + where distance actually lives (investigation)

Investigated a real BOLT trainer ride (2026-11-01, "Indoor Cycling", 7.30 km on
the Wahoo phone app). The Wahoo API `GET /v1/workouts` returned the SAME physical
ride as TWO separate records:

| record | name | fitness_app_id | plan_id | workout_summary |
|---|---|---|---|---|
| `511618809` | Indoor Cycling | 1085 | null | **null** (no metrics) |
| `511573120` | AE1. Recovery Spin 30min HR. | 1197 (TrainingPeaks) | 18103587 | **full** (7299.5 m, 32:22, etc.) |

Both have `started_at = 2026-11-01T11:56:51Z`, confirming one ride. The summary
on the TP record even carries `name: "Indoor Cycling"`, `time_zone`, and a FIT
`file.url` (`...ELEMNT_BOLT_B213...fit`, `fitness_app_id: 1`) — i.e. the ride was
recorded natively on the BOLT (app 1), attached to the TrainingPeaks plan record
(1197) which carried the summary. App 1085 is a separate connected partner that
re-shared a summary-less stub of the same ride.

### Findings
1. **Distance capture works.** The 7.30 km reached Supabase on record 511573120
   (`source=wahoo`, `distance=7299.5`). Wahoo DOES provide km for native BOLT
   rides — via the inline `workout_summary` on the record that carries it.
2. **Wahoo returns duplicates.** One ride => multiple cloud records (a
   summary-less stub + the summary-bearing record). The phone app merges them;
   the API exposes them separately. Both currently save -> the ride is stored
   twice (once with 7.3 km, once null).
3. App-id map so far (from live data): `1` = native Wahoo/ELEMNT device file,
   `30` = Wahoo iOS app (`WAHOOAPPIOS` token), `1197` = TrainingPeaks (confirmed
   by `plan_id`), `1085` = another connected partner (summary withheld;
   suspected Strava — confirm in Wahoo app > Authorized Apps).

### OPEN TEST (next)
Ride a FREE trainer ride (NO TrainingPeaks structured workout) and re-query. The
question: with no TP/plan record to carry the summary, does the distance still
come through (e.g. on a native app-1 / app-30 record), or do we only get the
summary-less stub? This determines whether Wahoo distance depends on the ride
being tied to a plan, or is available for any native BOLT ride.

## Backlog: cross-record / cross-provider de-duplication

The same physical ride can appear multiple times:
- Within Wahoo (summary-less stub + summary-bearing record, as above).
- Across providers (Strava + Garmin + COROS + Wahoo copies of one ride, since
  devices/apps auto-share to each other).

Without dedup the ranking will double-count. Deferred for now (beta), but needed
before the ranking is trusted.

Proposed match key (candidate): same `athlete_id` + same activity start time
(to the second) + same distance (within a small tolerance). Resolution rule:
keep ONE record, preferring the copy that HAS distance/summary; discard
summary-less duplicates. Start time is the most reliable join — in the Wahoo
case both records shared `started_at = 11:56:51`.

Reference case: ride 2026-11-01 11:56:51Z — records 511618809 (null) and
511573120 (7.30 km) are the same ride.

## Manual-entry tracking (per provider)

Tracking which activities are manual (entered by hand, not device-recorded)
matters for data trust. Support varies by provider:

- **Strava**: `activity.manual` boolean — captured reliably.
- **Garmin**: `isManualActivity` boolean — captured reliably.
- **Wahoo**: `manual` lives on `workout_summary` (not the workout stub). Captured
  when a summary is present; `None` (unknown) when the summary is withheld
  (third-party-origin workouts).
- **COROS**: ⚠️ `querySportRecords` prose exposes NO manual flag — a manually
  created COROS activity looks identical to a device-recorded one. The parser
  sets `manual = None` (unknown), not a misleading False. Reference: activity
  `481427340851708308` (2026-10-31, 35.16 km) was created manually in COROS but
  the list gives no indication.
  - **Consequence:** manual COROS entries cannot be flagged from the list, and a
    hand-set `manual=true` will be OVERWRITTEN to None on the next sync (upsert).
  - **TODO:** call the COROS `getActivityDetail` MCP tool per activity to read a
    manual indicator (needs a live COROS call to verify the detail shape).

`activities.manual` is nullable: True = manual, False = device-recorded,
None = unknown (provider didn't say).
