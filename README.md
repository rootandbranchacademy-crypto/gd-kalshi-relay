# gd-kalshi-relay

Data relay for the Gambler's Dharma × Kalshi paper test. A GitHub Action pulls
Kalshi game-winner markets and ESPN scoreboards every 30 minutes from 4:00 to 8:30 a.m. Pacific,
plus an evening pass, and commits the raw JSON to `data/`. Cloud agents that
can't reach Kalshi or ESPN read it from here.

**Paper research only. No trading, no credentials.**

## Files (read these)

| File | Contents |
|---|---|
| `data/latest/manifest.json` | `fetched_at_utc`, Pacific date, counts, errors. Check first. |
| `data/latest/kalshi_open.json` | `series.<SERIES>[]` → Kalshi events with nested `markets` (yes_bid_dollars, yes_ask_dollars, volume_fp, open_interest_fp, status, rules_primary) |
| `data/latest/kalshi_settled.json` | Events settled in the last 4 days, with `result` |
| `data/latest/espn_{nfl,ncaaf,mlb,nba,nhl}.json` | `dates.<YYYYMMDD>` → ESPN scoreboard (events[].date = scheduled start UTC; finals and scores) |
| `data/snapshots/<date>/<HHMM>Z/` | Point-in-time copies, kept 30 days, for auditing quoted prices |

Raw URL pattern (public repo):
`https://raw.githubusercontent.com/<owner>/gd-kalshi-relay/main/data/latest/<file>`

## Rules for agents

- Quote prices **as of the snapshot's `fetched_at_utc`**, and say so. A relay price is not a live executable quote.
- If `fetched_at_utc` is more than 3 hours old, or `errors` is non-empty for a series you need, report it; don't fill gaps from memory.
- Use the snapshot folder that matches the entry time when recording a pick's paper entry price.
