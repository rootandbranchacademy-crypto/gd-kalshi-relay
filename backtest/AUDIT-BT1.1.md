# GD-C1.0 retrospective backtest: independent audit and BT1.1

Auditor: Claude (Anthropic), 2026-10-14. Paper research only. No trades, no schedule changes, no purchases.
Branch `bt1.1-audit`. The committed BT1.0 pilot (`data/backtest/2026-04-14_2026-04-20/`) is untouched; BT1.1 writes to `data/backtest/bt1.1/`.

## Decision

A strict six-month backtest is **not feasible with free evidence**. It is **feasible in principle** with one paid source, The Odds API historical snapshots (START 20K plan, $30/month, historical access included), which supplies both missing pre-cutoff inputs: the sportsbook favorite and, for NBA/NHL/NFL, the scheduled start. Nothing is purchased until Brian authorizes it. Without that source the pipeline correctly produces zero predictions for every game.

## Verified

- Engine identity: `gd_engine.py` SHA256 `35bd6397…656f`, matching study.json.
- Build: pyswisseph 2.10.3.2 built from the pinned source (sha256 checked) with gcc, Linux, Python 3.13; ephemerides and sefstars.txt match the workflow hashes. Self-tests pass exactly: BALATL −26.5, HOUTEN −20.5.
- Pilot files: blind/outcome/prediction/study/annotation hashes all match manifest and lock. Counts reproduced: 144 games (MLB 95, NBA 17, NHL 32), 128 with paired quotes, 16 unmatched, dispositions 119 missing-data and 25 timing-exclusion, 0 predictions. All 25 timing exclusions are the engine's sankranti flag (Sun within 1° of a sign boundary, mid-April solar ingress); no station or eclipse flags in the window.
- Original nine integrity tests pass. They test plumbing, not validity.
- Cutoffs: all seven pilot cutoffs are 13:00Z (06:00 PDT); `ZoneInfo` handles DST.
- Quotes: every one of 256 quotes is at or before the cutoff; maximum age 7 minutes (limit 3 hours). Markets required `created_time` and `open_time` at or before cutoff.
- Outcome separation: `replay.py` never opens `outcomes.json` or raw responses; scoring checks the lock first. This is separation by code, not by access control.
- `expected_expiration_time` and closing odds are never used. Current ESPN starts are not accepted as morning evidence.
- Replay rules match the frozen GD-C1.0 text: Kalshi favorite with mid ≥ 55¢ and sportsbook agreement; |total| > 3 in ≥ 9/11 minutes (±5) and ≥ 15/21 (±10); engine timing filter unchanged (any body stationing within ±3 days, Pluto included; eclipse ±3 days; Sun within 1° of a sign boundary); at most four picks per day.

## Defective (fixed in BT1.1)

1. **Team-code mismatches lost 16 of 144 games.** ESPN and Kalshi abbreviations differ (NBA GS/GSW, NY/NYK, SA/SAS; MLB CHW/CWS). Fixed with an alias table restricted to codes seen in relay data. ARI and ATH Kalshi codes are not verified, so those 8 MLB games stay unmatched; the collector now logs unmatched Kalshi event tickers so the next relay run can verify them.
2. **No duplicate or doubleheader rejection.** Two ESPN games could map to one Kalshi event. Fixed: any shared ticker or same-day repeat pairing excludes all copies.
3. **Silent unit error was possible.** A non-integer JSON number such as 0.42 was divided by 100. Fixed: ambiguous numeric prices are rejected.
4. **Scoring did not check the study hash.** A study change between replay and scoring went unnoticed. Fixed.
5. **Unsafe workflow trigger.** Any push touching `backtest/**` ran with `full_if_ready=true`, so an annotation commit could launch the six-month expansion unattended. Fixed: pushes never expand; expansion needs a manual dispatch.
6. **The expansion gate could never pass.** BT1.0 required zero missing inputs of any kind, so one ambiguous ticker or doubleheader blocked six months permanently. BT1.1 keeps every evidence gate at zero tolerance but counts structurally excluded games (unmatched market, doubleheader, schedule conflict, no sportsbook line by the cutoff, market listed after the cutoff) as exclusions, capped at 15% of games. This is a disclosed change of protocol, versioned as BT1.1; it needs Brian's approval before any expansion.

## Unknown

- Kalshi codes for ARI and ATH.
- Whether Odds API 06:00 Pacific snapshots contain a DraftKings line for most April–October games (untested; games without one become structural exclusions).
- Whether ESPN's current records changed a game's venue after the fact (venue IDs come from current records).
- Historical candle coverage for the whole six months (the Kalshi historical cutoff is 2026-08-15; the collector queries both live and historical endpoints).

## Gap table (pilot, 144 games)

| Input | BT1.0 | BT1.1 now | Evidence needed | Recoverable? |
|---|---|---|---|---|
| Venue coordinates | 0 | 144 | Static facts; 58 venues sourced from Wikipedia, URLs and fetch times in annotations.json | Done |
| Name syllables | 0 | 144 | Team-level declarations under a frozen rule, written before replay | Done (rule BT1.1-SYL-1) |
| Kalshi event match | 128 | 136 projected | Verified team codes | 8 MLB games need ARI/ATH codes from a relay run |
| Scheduled start, MLB | 0 | 80 of 84 matched | Kalshi event ticker HHMM (ET), fixed at creation days before cutoff; must equal current ESPN start | Done; 4 conflicts excluded |
| Scheduled start, NBA/NHL | 0 | 0 of 49 | Timestamped pre-cutoff schedule | Only via Odds API `commence_time` (paid); no free archive found |
| Sportsbook favorite | 0 | 0 of 144 | Timestamped pre-cutoff moneyline | Only via Odds API historical (paid). Wayback could not be tested (proxy blocked) |

Projected predictions under BT1.1 without the paid source: zero, because every game still lacks the sportsbook favorite.

## Syllables: objectivity and residual discretion

GD-C1.0 matched syllables by hand. BT1.1-SYL-1 replaces that with a rule applied to canonical ESPN names only: spelling onset plus first vowel, union with the first vowel of every CMUdict 1.0.32 pronunciation, the book's substitutions (w→v, f→pa/pha, z→jha, e≈ai, o≈au), English t/d matching both dental and retroflex cells. Declarations never see charts, quotes or outcomes, and are hashed into each manifest before replay.

Check against Claude's 17 prospective word declarations (picks C1–C4): the rule covers all 17, with 10 extra tokens across 7 words (for example Houston adds ho, Canucks adds ke and ku). Extras make the sound module fire more often than hand practice did; each match is worth 16–18 points, so this is a material difference to report beside any result.

Remaining discretion, disclosed: cluster reduction to the first consonant, dental/retroflex equivalence, y as a vowel, using every CMUdict pronunciation, and skipping "St." and "76ers". The rule was adjusted once to reproduce the published Flyers declaration (diphthong AY also gives a); that is calibration to prospective declarations, not to outcomes. Claude's training data runs to June 2026, so hindsight knowledge of April–June results exists in principle; it cannot enter the replay except through these rule choices, which never touch results.

## Method fidelity: BT replay versus prospective GD-C1.0

The replay is a deterministic reading of GD-C1.0, not a reconstruction of what GPT or Claude would have published.

- Ranking is mechanical (technique families, then timing agreement, then median score). Prospective ranking was qualitative.
- The cutoff is 06:00 Pacific. Claude's prospective entries were published the night before or at about 07:00.
- The slate is every ESPN game on the Pacific date. Prospective runs screened games starting after publication and before 03:00 the next day.
- Spreads over 5¢ are excluded; prospectively they could be recorded as exceptions.
- Prices are one-minute candle closes, not order-book asks with depth.
- Syllables are matched by the declared rule, not by hand.
- Not implemented in either: Gulika; graha yuddha and parivartana are unscored; no orb extensions; no personal factors.

## What a strict rerun needs

1. Brian authorizes The Odds API START 20K plan ($30/month) and adds the key as the repository secret `ODDS_API_KEY`. Estimated use: about 210 credits for the pilot week, about 6,000 for six months, at 10 credits per sport-day snapshot.
2. Someone with push rights pushes branch `bt1.1-audit` to `main` (this session's GitHub token is invalid). The push reruns only the pilot, into `data/backtest/bt1.1/`.
3. Read coverage first. Expand only by manual dispatch with `full_if_ready=true`, and only if the BT1.1 gate passes and Brian approves the gate change.

## Approximate study, if no data is bought (not run)

GD-C1.0-BT-A1 would be a separate cohort, never added to GD-C1.0 totals. Relaxed assumptions:
- The favorite comes from the 06:00 Kalshi mid alone, with no sportsbook confirmation. This drops a frozen requirement.
- NBA/NHL scheduled starts come from current ESPN records, which may include later revisions.

The MLB ticker schedule, venues, syllables, quotes and engine stay strict. Every result would be labelled A1.

## Prospective GPT-versus-Claude comparison: requirements

A shared engine replay says nothing about either model. A real comparison needs:

1. **Same inputs.** One relay snapshot at one cutoff for both models.
2. **Independent picks.** Each model decides without reading the other's same-day entry. Today both models read the shared log, which contains the other's entries.
3. **Locks before play.** Picks are hash-locked before the first game, for example as a commit to the relay repository, so timestamps cannot be argued.
4. **Fixed method and output.** The same method version and the same pick rule for both.
5. **Pre-registered metric.** Hit rate against the market-favorite baseline on the same events, plus paired disagreements.
6. **Enough settled picks.** Roughly 400 per model to detect a 5-point edge at about 2 standard errors. The current station rule excludes most days (2 pickable days in the 14 after October 13), so that sample would take a long time.

Until those conditions hold, gpt_performance and claude_performance stay unavailable.

## Validation

- 20 tests pass: the original 9 plus 11 failure-path tests.
  - Ambiguous units; stale quote; quote exactly at cutoff.
  - Verified-only aliases; ET ticker time across DST.
  - Odds snapshot or line after cutoff; pick'em; duplicate odds events.
  - Each missing gate blocks charting; timing-calculation error.
  - Settlement needing both sources; tampered prediction lock; deterministic syllable rule.
- An offline collector smoke test with synthetic fixtures confirmed three behaviours:
  - The CWS alias match.
  - MLB ticker schedule acceptance.
  - Rejection of a doubleheader with a schedule conflict.
- No provider was called from this session. All provider collection remains in the GitHub relay.
