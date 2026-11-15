"""
Delete everything held for one provider account (deletion on user request, or
clean-up after a revocation). Strava API Policy 2.5 / 7.4; support page promises
deletion within 30 days.

DEFAULT IS A DRY RUN: it only reports what would be deleted. Add --yes to delete.

Usage (run from the repo root, secrets injected by Infisical):

    infisical run --env=prod --path=/app -- python scripts/purge_athlete.py strava 123456
    infisical run --env=prod --path=/app -- python scripts/purge_athlete.py strava 123456 --yes

Arguments: <provider> <provider_user_id>
  provider          strava | coros | garmin | wahoo
  provider_user_id  the id stored in athlete_providers.provider_user_id

After deleting, send the person the written confirmation the policy requires
(see the support page: deletion is confirmed by message).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import providers  # noqa: E402


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    do_delete = "--yes" in argv
    if len(args) != 2 or args[0] not in providers.PROVIDERS:
        print(__doc__)
        return 2

    provider, uid = args
    result = providers.purge_provider_data(provider, uid, dry_run=not do_delete)

    print(("DELETED" if do_delete else "DRY RUN (nothing deleted)") + f": {provider} {uid}")
    for key in ("link_found", "activities", "monthly_totals", "webhook_events", "athlete_deleted"):
        print(f"  {key}: {result[key]}")
    if not result["link_found"]:
        print("  (no provider link found - nothing else to delete)")
    if not do_delete:
        print("Re-run with --yes to delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
