#!/usr/bin/env python3
"""Gambler's Dharma x Kalshi data relay.

Runs on GitHub Actions (open internet). Pulls Kalshi game-winner events and
ESPN scoreboards and writes raw JSON into data/, so cloud agents that cannot
reach Kalshi or ESPN (Claude cloud, Codex cloud) can read it from GitHub.

Paper-test data only. No trading, no credentials.

Output:
  data/latest/kalshi_open.json      open events + nested markets, all series
  data/latest/kalshi_settled.json   events settled in the last 4 days
  data/latest/espn_<sport>.json     scoreboards for yesterday/today/tomorrow (PT)
  data/latest/manifest.json         fetch time (UTC), counts, any errors
  data/snapshots/<YYYY-MM-DD>/<HHMM>Z/...  same files, kept for audit
"""
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KALSHI = "https://api.elections.kalshi.com/trade-api/v2/events"
SERIES = ["KXNFLGAME", "KXNCAAFGAME", "KXMLBGAME", "KXNBAGAME", "KXNHLGAME"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d}"
SPORTS = {
    "nfl": "football/nfl",
    "ncaaf": "football/college-football",
    "mlb": "baseball/mlb",
    "nba": "basketball/nba",
    "nhl": "hockey/nhl",
}
UA = {"User-Agent": "gd-kalshi-relay/1.0 (paper research)", "Accept": "application/json"}


def get_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def kalshi_events(series, status, extra=None):
    out, cursor = [], None
    for _ in range(20):  # page cap
        q = {"series_ticker": series, "status": status,
             "with_nested_markets": "true", "limit": "200"}
        if extra:
            q.update(extra)
        if cursor:
            q["cursor"] = cursor
        page = get_json(KALSHI + "?" + urllib.parse.urlencode(q))
        out.extend(page.get("events", []))
        cursor = page.get("cursor")
        if not cursor:
            break
    return out


def main(root):
    now = datetime.now(timezone.utc)
    pt_today = now.astimezone(ZoneInfo("America/Los_Angeles")).date()
    dates = [(pt_today + timedelta(days=k)).strftime("%Y%m%d") for k in (-1, 0, 1)]
    latest = os.path.join(root, "data", "latest")
    os.makedirs(latest, exist_ok=True)
    manifest = {"fetched_at_utc": now.isoformat(timespec="seconds"),
                "pacific_date": pt_today.isoformat(), "counts": {}, "errors": []}

    def save(name, obj):
        with open(os.path.join(latest, name), "w") as f:
            json.dump(obj, f, separators=(",", ":"))

    min_close = str(int((now - timedelta(days=4)).timestamp()))
    for status, fname, extra in (("open", "kalshi_open.json", None),
                                 ("settled", "kalshi_settled.json", {"min_close_ts": min_close})):
        bundle = {"fetched_at_utc": manifest["fetched_at_utc"], "status": status, "series": {}}
        for s in SERIES:
            try:
                bundle["series"][s] = kalshi_events(s, status, extra)
                manifest["counts"][f"kalshi_{status}_{s}"] = len(bundle["series"][s])
            except Exception as e:  # noqa: BLE001
                manifest["errors"].append(f"kalshi {status} {s}: {e}")
        save(fname, bundle)

    for key, path in SPORTS.items():
        bundle = {"fetched_at_utc": manifest["fetched_at_utc"], "dates": {}}
        for d in dates:
            try:
                bundle["dates"][d] = get_json(ESPN.format(path=path, d=d))
                manifest["counts"][f"espn_{key}_{d}"] = len(bundle["dates"][d].get("events", []))
            except Exception as e:  # noqa: BLE001
                manifest["errors"].append(f"espn {key} {d}: {e}")
        save(f"espn_{key}.json", bundle)

    save("manifest.json", manifest)

    snap = os.path.join(root, "data", "snapshots", pt_today.isoformat(), now.strftime("%H%MZ"))
    shutil.copytree(latest, snap, dirs_exist_ok=True)
    print(json.dumps(manifest, indent=1))
    # Fail the job only if nothing at all came back.
    return 1 if not any(manifest["counts"].values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
