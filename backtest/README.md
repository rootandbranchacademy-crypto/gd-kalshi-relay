# GD-C1.0 retrospective backtest

> **BT1.1 (2026-10-14).** Audit, fixes and evidence rules are in
> [AUDIT-BT1.1.md](AUDIT-BT1.1.md). Summary: venues and name syllables are now
> annotated; MLB scheduled starts come from Kalshi event tickers; the sportsbook
> favorite (and NBA/NHL/NFL schedule) needs the optional, paid `collect_odds.py`
> stage (`ODDS_API_KEY` secret, not enabled). Pushes no longer trigger the
> six-month expansion. BT1.1 output goes to `data/backtest/bt1.1/`.

This is a separate, outcome-blind, resumable backfill and replay job. It does not
change the daily relay or either AI's scheduled task. No trades or API keys.

Frozen engine: Brian's original `gd_engine.py`, SHA256 recorded in `study.json`.
BT1.0 freezes a 06:00 America/Los_Angeles cutoff, a four-pick maximum, exhaustive
screening and mechanical ranking by family convergence and timing robustness.
These replay/ranking choices are **not evidence of what GPT or Claude would have
published**. The qualitative original ranking cannot be reconstructed uniquely.

The first pilot covers April 14–20, 2026. Intended full period: April 14–October
13. The workflow is one-time/manual, with no cron schedule. It only scales after
the pilot's coverage gate passes; missing inputs cause an explicit stop.

## Pipeline

1. `collect.py` runs on the GitHub relay. It paginates historical/current market
   metadata, caches raw GET responses, and downloads each game's 1-minute candles
   ending at or before the 6 a.m. cutoff. The latest complete valid candle within
   three hours supplies bid/ask. Post-event quotes, volume, team records and closing
   odds never feed the predictor. Current historical ESPN records are explicitly
   not treated as contemporaneous morning schedules or timestamped sportsbook lines.
2. Raw final scores and market results go only to `outcomes.json`. Predictor inputs
   are whitelisted into `blind_inputs.json` without outcomes.
3. `replay.py` verifies the unchanged engine hash and the two reference self-tests.
   It applies timing exclusions, strict input gates, all 21 one-minute charts and
   predeclared syllable candidates. It writes predictions and a SHA256 lock before
   the separate score command reveals outcomes.
4. `score.py` checks that neither predictions nor outcomes changed after locking,
   requires Kalshi/ESPN agreement, and reports hits/baselines only for the same
   selected events. Returns are historical candle-close price proxies, not proven
   fills. Net returns are blank until historical fees are verified. Wilson begins
   at five settled. Every missing-data reason and excluded game stays in the output.

`annotations.json` requires sourced stadium coordinates, timestamped pre-cutoff
schedule/sportsbook evidence and outcome-hidden team syllable declarations. None is
invented. Empty annotations mean a coverage pilot, not an accuracy claim. Mapping
ambiguities between team names/tickers are rejected rather than guessed.

Outputs are committed under `data/backtest/<start>_<end>/` with immutable file
hashes. Raw cached GET responses make each batch resumable. Predictions are stored
separately from the prospective Google Doc. The HTML report summarizes coverage.

## Run

Use the **GD-C1.0 historical pilot** workflow's **Run workflow** button. Defaults are
the seven-day pilot. `full_if_ready=true` expands to the frozen full period only
after the pilot gate passes. It is initially true; a coverage failure stops expansion.
The initial code deployment also triggers the pilot once.

Local commands may replay already-relayed files, but may not collect provider data:

```
python3 -m unittest discover -s backtest -p 'test_*.py'
GD_EPHE=/path/to/ephe GD_SWE_PATH=/path/to/built/source python3 backtest/replay.py data/backtest/2026-04-14_2026-04-20
python3 backtest/score.py data/backtest/2026-04-14_2026-04-20
```

## Documentation

- https://docs.kalshi.com/getting_started/historical_data
- https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks

Historical minute candles include bid/ask OHLC; no assumption of full orderbook
depth. The six-month forecast record is retrospective, developed after that period.
Outcome hiding reduces pipeline leakage but cannot eliminate a model's historical
knowledge. GPT/Claude cohorts need separately locked blind selections and are not
filled from the shared engine's results.
