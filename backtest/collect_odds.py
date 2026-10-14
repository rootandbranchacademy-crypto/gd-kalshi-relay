"""Optional relay-only stage: timestamped pre-cutoff sportsbook favorite and scheduled
start from The Odds API historical snapshots. Runs only on GitHub Actions and only
when the ODDS_API_KEY secret exists (a paid plan; do not enable without Brian's
authorization). Read-only; no trading.

Endpoint (docs: https://the-odds-api.com/liveapi/guides/v4/): GET
/v4/historical/sports/{sport}/odds?regions=us&markets=h2h&date=<ISO>. The API returns
"the closest snapshot equal to or earlier than" the date, with the snapshot timestamp
(5-minute snapshots since Sept 2022). Cost: 10 credits per region per market per call.

Output: <out>/sportsbook_evidence.json keyed "<sport>-ESPN-<espn id>", consumed by
collect.py. Evidence is accepted only if the snapshot timestamp and the bookmaker's
market last_update are both at or before the 06:00 Pacific cutoff. The favorite is
DraftKings' shorter moneyline (GD-C1.0 used DraftKings via ESPN prospectively); a tie,
a missing DraftKings line or an unmatched team name gives no evidence. The API key is
never written to the cache or outputs.
"""
import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from common import STUDY, save, utc, digest

API = 'https://api.the-odds-api.com/v4/historical/sports/{sport}/odds'
SPORT_KEYS = {'nfl': 'americanfootball_nfl', 'ncaaf': 'americanfootball_ncaaf', 'mlb': 'baseball_mlb',
              'nba': 'basketball_nba', 'nhl': 'icehockey_nhl'}
BOOK = 'draftkings'
PT = ZoneInfo('America/Los_Angeles')


def fetch(sport, cutoff, key, cache):
    public = API.format(sport=SPORT_KEYS[sport]) + '?' + urllib.parse.urlencode(
        {'regions': 'us', 'markets': 'h2h', 'oddsFormat': 'american', 'date': cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')})
    path = cache / ('odds-' + hashlib.sha256(public.encode()).hexdigest() + '.json')
    if path.exists(): return json.loads(path.read_text())
    for attempt in range(4):
        try:
            with urllib.request.urlopen(public + '&apiKey=' + urllib.parse.quote(key), timeout=30) as r:
                body = json.load(r)
                used = r.headers.get('x-requests-used'); remaining = r.headers.get('x-requests-remaining')
            record = {'url_without_key': public, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                      'requests_used': used, 'requests_remaining': remaining, 'response': body}
            save(path, record); return record
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3: raise
        time.sleep(2 ** attempt)


def evidence_for(game, snapshot, cutoff):
    """One ESPN game + one snapshot -> evidence dict or (None, reason)."""
    ts = snapshot.get('timestamp')
    if not ts or utc(ts) > cutoff: return None, 'snapshot_after_cutoff_or_missing'
    comp = game['competitions'][0]; names = {c['team']['displayName']: str(c['team']['id']) for c in comp['competitors']}
    hits = [e for e in snapshot.get('data', []) if {e.get('home_team'), e.get('away_team')} == set(names)]
    if len(hits) != 1: return None, 'no_unique_name_match' if not hits else 'duplicate_odds_events'
    e = hits[0]
    book = [b for b in e.get('bookmakers', []) if b.get('key') == BOOK]
    market = [m for b in book for m in b.get('markets', []) if m.get('key') == 'h2h']
    if len(market) != 1: return None, 'no_draftkings_h2h'
    m = market[0]
    if not m.get('last_update') or utc(m['last_update']) > cutoff: return None, 'line_after_cutoff'
    prices = {o['name']: o['price'] for o in m.get('outcomes', []) if o.get('name') in names}
    if len(prices) != 2: return None, 'incomplete_prices'
    (a, pa), (b, pb) = prices.items()
    if pa == pb: return None, 'pick_em'
    fav = a if pa < pb else b
    return {'scheduled_start_utc': e['commence_time'], 'schedule_source': 'The Odds API historical snapshot commence_time',
            'schedule_available_at_utc': ts, 'sportsbook_favorite_team_id': names[fav],
            'sportsbook_source': 'The Odds API historical snapshot, DraftKings h2h ' + json.dumps(prices, sort_keys=True),
            'sportsbook_available_at_utc': m['last_update'], 'snapshot_timestamp': ts}, None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--start', required=True); ap.add_argument('--end', required=True); ap.add_argument('--out', required=True)
    args = ap.parse_args(); out = Path(args.out); cache = out / 'raw'; cache.mkdir(parents=True, exist_ok=True)
    key = os.environ.get('ODDS_API_KEY')
    if not key:
        print('ODDS_API_KEY not configured: no sportsbook evidence collected (expected until authorized).'); return
    from collect import get, SPORTS
    evidence, report = {}, {'unmatched': {}, 'requests_remaining': None}
    day, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    while day <= end:
        cutoff = datetime.combine(day, datetime.min.time(), PT) + timedelta(hours=STUDY['cutoff_hour'])
        for sport, (_, path) in SPORTS.items():
            q = {'dates': day.strftime('%Y%m%d'), 'limit': 1000}
            if sport == 'ncaaf': q['groups'] = 80
            board = get('https://site.api.espn.com/apis/site/v2/sports/' + path + '/scoreboard?' + urllib.parse.urlencode(q), cache)
            games = [g for g in board.get('events', []) if g.get('date') and utc(g['date']).astimezone(PT).date() == day]
            if not games: continue
            record = fetch(sport, cutoff.astimezone(timezone.utc), key, cache)
            report['requests_remaining'] = record.get('requests_remaining')
            for g in games:
                if len(g.get('competitions', [])) != 1: continue
                ev, why = evidence_for(g, record['response'], cutoff.astimezone(timezone.utc))
                gid = sport + '-ESPN-' + str(g['id'])
                if ev: evidence[gid] = ev
                else:
                    report['unmatched'].setdefault(why, []).append(gid)
                    # The snapshot exists but DraftKings had no usable line by the cutoff: the
                    # prospective method could not have named a favorite either (structural).
                    if why in ('no_draftkings_h2h', 'line_after_cutoff', 'incomplete_prices', 'pick_em'):
                        evidence[gid] = {'no_line_at_cutoff': why, 'snapshot_timestamp': record['response'].get('timestamp')}
        day += timedelta(days=1)
    save(out / 'sportsbook_evidence.json', evidence); save(out / 'sportsbook_evidence_report.json', report)
    print(json.dumps({'evidence': len(evidence), **{k: len(v) for k, v in report['unmatched'].items()}}, indent=2))


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise SystemExit('Relay-only stage; run on GitHub Actions.')
    main()
