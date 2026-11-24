-- Migration 011: carry user-entered profile through the OAuth round trip
--
-- Why
--   Some providers (Hammerhead Karoo, Garmin Personal API) expose no name or
--   sex. For those, the connect page asks the athlete for first name, last name
--   and sex. That input has to survive the redirect to the provider and back,
--   so it is stored on the short-lived oauth_states row (15 min expiry,
--   single-use, deleted when the callback consumes it).
--
-- Safety
--   Adds one nullable column. Existing rows and existing code are unaffected.
--   Run this BEFORE deploying the app change that writes it.
--
-- Run in the Supabase SQL editor. Idempotent.

alter table public.oauth_states
    add column if not exists profile jsonb;
