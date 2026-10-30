# sync.py
#
# Provider-neutral daily/rolling sync. Iterates active athlete_providers links
# (not the athletes.active flag) so each provider account is synced
# independently and stamped with the right source + canonical athlete_id.

import time
from datetime import datetime, timezone, timedelta

import providers
import strava

# Per-provider sync handlers. Each returns the number of activities saved.
def _sync_strava_link(link, start_ts, end_ts) -> int:
    access_token = strava.refresh_link_token(link)
    activities = strava.get_activities_range(access_token, start_ts, end_ts)
    strava.save_activities(activities, athlete_id=link["athlete_id"])
    return len(activities) if activities else 0


# provider -> handler. COROS will be added here once its sync is implemented.
_PROVIDER_SYNC = {
    "strava": _sync_strava_link,
}


def sync_link(link, start_ts, end_ts):
    """Sync one athlete_providers link over the given window."""
    provider = link.get("provider")
    link_id = link.get("id")
    athlete_id = link.get("athlete_id")

    handler = _PROVIDER_SYNC.get(provider)
    if handler is None:
        msg = f"no sync handler for provider '{provider}'"
        print(f"[sync] SKIP link={link_id}: {msg}")
        return {"link_id": link_id, "provider": provider, "athlete_id": athlete_id,
                "count": 0, "error": msg}

    try:
        count = handler(link, start_ts, end_ts)
        providers.update_provider_status(
            link_id, last_sync=providers._now_iso(),
            error_message=None, status="active",
        )
        print(f"[sync] link={link_id} provider={provider} synced {count} activities")
        return {"link_id": link_id, "provider": provider, "athlete_id": athlete_id,
                "count": count, "error": None}
    except Exception as e:
        err = str(e)
        print(f"[sync] ERROR link={link_id} provider={provider}: {err}")
        providers.update_provider_status(link_id, error_message=err, status="error")
        return {"link_id": link_id, "provider": provider, "athlete_id": athlete_id,
                "count": 0, "error": err}


def sync_all(start_ts, end_ts, provider=None):
    """Sync all active provider links (optionally filtered to one provider)."""
    links = providers.list_active_links(provider=provider)
    results = []
    for link in links:
        results.append(sync_link(link, start_ts, end_ts))
        time.sleep(0.2)  # gentle pacing between provider calls
    return results


# -------------------------
# Convenience runners
# -------------------------
def run_daily_sync():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    start_ts = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_ts = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)
    return sync_all(start_ts, end_ts)


def run_rolling_sync(hours: int = 4):
    end_ts = datetime.now(timezone.utc)
    start_ts = end_ts - timedelta(hours=hours)
    return sync_all(start_ts, end_ts)
