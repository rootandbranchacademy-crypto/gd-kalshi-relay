"""Run only on the GitHub relay runner. Public read-only historical backfill.

Never performs authenticated or trading calls. Cached responses make reruns resumable.
Final ESPN records and Kalshi settlement metadata are segregated from blind inputs.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from common import ROOT, STUDY, save, utc, digest

BASE = 'https://api.elections.kalshi.com/trade-api/v2'
SPORTS = {'nfl': ('KXNFLGAME','football/nfl'), 'ncaaf': ('KXNCAAFGAME','football/college-football'), 'mlb': ('KXMLBGAME','baseball/mlb'), 'nba': ('KXNBAGAME','basketball/nba'), 'nhl': ('KXNHLGAME','hockey/nhl')}
PT = ZoneInfo('America/Los_Angeles')

def get(url, cache):
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')
    if path.exists():
        return json.loads(path.read_text())['response']
    for attempt in range(4):
        time.sleep(0.25)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'gd-backtest/BT1.0 paper-research', 'Accept':'application/json'})
            with urllib.request.urlopen(req, timeout=30) as response:
                body = json.load(response)
            save(path, {'url':url, 'retrieved_at_utc':datetime.now(timezone.utc).isoformat(), 'response':body})
            return body
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504): raise
            if attempt == 3: raise
        except (OSError, ValueError):
            if attempt == 3: raise
        time.sleep(2 ** attempt)

def paged(path, query, key, cache):
    rows, seen, cursor = [], set(), None
    for _ in range(300):
        q = dict(query)
        if cursor: q['cursor'] = cursor
        page = get(BASE + path + '?' + urllib.parse.urlencode(q), cache)
        rows.extend(page.get(key, [])); cursor = page.get('cursor')
        if not cursor: return rows
        if cursor in seen: raise RuntimeError('Repeated pagination cursor')
        seen.add(cursor)
    raise RuntimeError('Pagination cap reached; coverage incomplete')

def ticker_day(ticker):
    match = re.search(r'-(\d{2})([A-Z]{3})(\d{2})', ticker)
    if not match: return None
    try: return datetime.strptime(''.join(match.groups()), '%y%b%d').date()
    except ValueError: return None

def quote(candles, cutoff):
    """Latest COMPLETE 1-minute candle <= cutoff; never use later prices."""
    for c in sorted(candles, key=lambda x:x['end_period_ts'], reverse=True):
        ts = c['end_period_ts']
        if ts > cutoff or cutoff - ts > STUDY['quote_max_age_seconds']: continue
        def dollars(obj):
            if obj.get('close_dollars') is not None: return float(obj['close_dollars'])
            value = obj.get('close')
            if value is None: return None
            # Archived schema: dollar strings. Live legacy schema: integer cents.
            # A non-integer JSON number is ambiguous (dollars or cents?): reject it.
            if isinstance(value, bool): return None
            if isinstance(value, int): return value / 100
            if isinstance(value, float): return value / 100 if value.is_integer() and value >= 1 else None
            return float(value)
        bid, ask = dollars(c.get('yes_bid',{})), dollars(c.get('yes_ask',{}))
        if bid is not None and ask is not None and 0 < bid <= ask < 1:
            return {'bid':bid, 'ask':ask, 'mid':(bid+ask)/2, 'as_of_utc':datetime.fromtimestamp(ts,timezone.utc).isoformat(), 'provenance':'historical 1-minute candle close; depth unavailable'}
    return None

# ESPN abbreviation -> Kalshi ticker code. Only codes seen in relay data
# (data/latest/kalshi_*.json, 2026-10-14) are listed; unverified codes stay
# unmatched and are logged in the manifest instead of being guessed.
ALIASES = {'nba': {'GS': 'GSW', 'NY': 'NYK', 'SA': 'SAS'}, 'mlb': {'CHW': 'CWS'}}
ET = ZoneInfo('America/New_York')
STRUCTURAL = {'unambiguous_kalshi_event_match', 'already_started_at_cutoff', 'duplicate_matchup',
              'doubleheader', 'schedule_conflict', 'market_not_listed_before_cutoff',
              'no_sportsbook_line_at_cutoff'}

def codes(sport, team):
    a = team.get('abbreviation', '')
    return {a, ALIASES.get(sport, {}).get(a, a)}

def mlb_ticker_start(ticker):
    """MLB event tickers embed the scheduled first pitch as HHMM US/Eastern.
    The ticker is fixed when the event is created, so with created_time <= cutoff it is
    timestamped pre-cutoff schedule evidence. Verified against ESPN on 80/84 pilot games."""
    m = re.search(r'-(\d{2}[A-Z]{3}\d{2})(\d{4})[A-Z]', ticker)
    if not m: return None
    local = datetime.strptime(m.group(1) + m.group(2), '%y%b%d%H%M').replace(tzinfo=ET)
    return local.astimezone(timezone.utc)

def match_market(market, competitors, sport=None):
    label = market.get('yes_sub_title','').casefold().strip()
    matches = []
    for c in competitors:
        t = c['team']; names = [t.get(k,'').casefold().strip() for k in ('displayName','shortDisplayName','name','location','abbreviation')]
        market_abbreviation=market.get('ticker','').rsplit('-',1)[-1].casefold()
        codeset={x.casefold() for x in codes(sport,t)} if sport else {t.get('abbreviation','').casefold()}
        if (label and label in names) or (market_abbreviation and market_abbreviation in codeset): matches.append(str(t['id']))
    return matches[0] if len(matches)==1 else None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--start',default=STUDY['pilot'][0]); ap.add_argument('--end',default=STUDY['pilot'][1]); ap.add_argument('--out',required=True); ap.add_argument('--sports',default=','.join(SPORTS))
    args=ap.parse_args(); out=Path(args.out); cache=out/'raw'; cache.mkdir(parents=True,exist_ok=True)
    start,end=date.fromisoformat(args.start),date.fromisoformat(args.end)
    assert start<=end and (end-start).days<=183
    manifest={'study_id':STUDY['study_id'],'start':args.start,'end':args.end,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'errors':[], 'counts':{},'study_sha256':digest(ROOT/'study.json'),'sports':args.sports,'annotations_sha256':digest(ROOT/'annotations.json')}
    annotations=json.loads((ROOT/'annotations.json').read_text())
    blind, outcomes = [], {}
    odds_path=out/'sportsbook_evidence.json'
    odds=json.loads(odds_path.read_text()) if odds_path.exists() else {}
    if odds_path.exists(): manifest['sportsbook_evidence_sha256']=digest(odds_path)
    try: manifest['historical_cutoff']=get(BASE+'/historical/cutoff',cache)
    except Exception as exc: manifest['errors'].append({'stage':'historical_cutoff','error':str(exc)})
    min_ts=int(datetime.combine(start,datetime.min.time(),PT).timestamp())
    wanted=args.sports.split(',')
    for sport,(series,path) in SPORTS.items():
        if sport not in wanted: continue
        try:
            events=paged('/events',{'series_ticker':series,'min_close_ts':min_ts,'limit':200,'with_nested_markets':'false'},'events',cache)
            event_index={e['event_ticker']:e for e in events if ticker_day(e['event_ticker']) and start<=ticker_day(e['event_ticker'])<=end}
            manifest['counts'][series+'_events']=len(event_index)
        except Exception as exc:
            manifest['errors'].append({'stage':series+'_events','error':str(exc)}); event_index={}
        matched_tickers=set()
        day=start
        while day<=end:
            cutoff=datetime.combine(day,datetime.min.time(),PT)+timedelta(hours=STUDY['cutoff_hour']); cutoff_ts=int(cutoff.timestamp())
            try:
                q={'dates':day.strftime('%Y%m%d'),'limit':1000}
                if sport=='ncaaf': q['groups']=80
                board=get('https://site.api.espn.com/apis/site/v2/sports/'+path+'/scoreboard?'+urllib.parse.urlencode(q),cache)
            except Exception as exc:
                manifest['errors'].append({'stage':sport+'_'+day.isoformat(),'error':str(exc)}); day+=timedelta(days=1); continue
            for g in board.get('events',[]):
                if not g.get('date') or utc(g['date']).astimezone(PT).date()!=day: continue
                comps=g.get('competitions',[])
                if len(comps)!=1 or len(comps[0].get('competitors',[]))!=2: continue
                comp=comps[0]; teams=comp['competitors']; teamids={str(c['team']['id']) for c in teams}
                abb=[codes(sport,c['team']) for c in teams]
                # Exact ticker suffix abbreviation match only; ambiguity stays missing.
                possible=[]
                for ticker,e in event_index.items():
                    if ticker_day(ticker)!=day: continue
                    # MLB inserts scheduled HHMM in the event ticker. Use the
                    # date only for discovery, never derive a chart start from it.
                    suffix=re.sub(r'^.*?-\d{2}[A-Z]{3}\d{2}\d*', '',ticker)
                    if any(a+b==suffix for a in abb[0] for b in abb[1]) or any(a+b==suffix for a in abb[1] for b in abb[0]): possible.append(ticker)
                ticker=possible[0] if len(possible)==1 else None
                if ticker: matched_tickers.add(ticker)
                key=ticker or sport+'-ESPN-'+str(g['id'])
                start_utc=g['date']; ann=annotations.get('events',{}).get(key,{})
                venue=comp.get('venue',{}); v=annotations.get('venues',{}).get(str(venue.get('id')),{})
                row={'id':key,'sport':sport,'day':day.isoformat(),'cutoff_utc':cutoff.astimezone(timezone.utc).isoformat(),'start_utc':start_utc,'teams':[{'id':str(c['team']['id']),'name':c['team']['displayName'],'abbreviation':c['team'].get('abbreviation'),'home_away':c['homeAway']} for c in teams],'venue':{'id':str(venue.get('id','')),'name':venue.get('fullName')},'quotes':{},'missing':[], 'source_espn_id':str(g['id']), 'schedule_provenance':'current historical ESPN record; original morning version unavailable'}
                if not ticker: row['missing'].append('unambiguous_kalshi_event_match')
                if utc(start_utc)<=cutoff: row['missing'].append('already_started_at_cutoff')
                if v.get('verified') and v.get('source') and all(k in v for k in ('lat','lon')):
                    row['coordinates']={'lat':v['lat'],'lon':v['lon'],'source':v['source']}
                else: row['missing'].append('verified_venue_coordinates')
                if ann.get('schedule_source') and ann.get('schedule_available_at_utc') and utc(ann['schedule_available_at_utc'])<=cutoff and ann.get('scheduled_start_utc') and utc(ann['scheduled_start_utc'])==utc(start_utc):
                    row['schedule_verified_at_cutoff']=True; row['schedule_provenance']=ann['schedule_source']+' available '+ann['schedule_available_at_utc']
                else:
                    row['missing'].append('timestamped_scheduled_start')
                    if ann.get('scheduled_start_utc') and ann.get('schedule_available_at_utc') and utc(ann['schedule_available_at_utc'])<=cutoff and utc(ann['scheduled_start_utc'])!=utc(start_utc):
                        row['missing'].append('schedule_conflict'); row['schedule_conflict']={'evidence_start_utc':ann['scheduled_start_utc'],'espn_start_utc':start_utc}
                ev=odds.get(sport+'-ESPN-'+str(g['id']),{})
                if ev.get('no_line_at_cutoff'): row_flags=['no_sportsbook_line_at_cutoff']
                else: row_flags=[]
                if not ann.get('sportsbook_source') and ev and not row_flags: ann={**ev,**ann}
                if ann.get('sportsbook_source') and ann.get('sportsbook_available_at_utc') and utc(ann['sportsbook_available_at_utc'])<=cutoff and ann.get('sportsbook_favorite_team_id') in teamids:
                    row['sportsbook_favorite_team_id']=ann['sportsbook_favorite_team_id']
                else: row['missing'].extend(row_flags or ['timestamped_sportsbook_favorite'])
                decl={str(c['team']['id']):annotations.get('teams',{}).get(sport+':'+str(c['team']['id'])) for c in teams}
                if all(d and d.get('rule') and d.get('canonical_name')==c['team']['displayName'] for d,c in zip(decl.values(),teams)):
                    row['syllables_by_team_id']={tid:d['words'] for tid,d in decl.items()}; row['syllable_rule']=sorted({d['rule'] for d in decl.values()})
                elif set(ann.get('syllables_by_team_id',{}))==teamids:
                    row['syllables_by_team_id']=ann['syllables_by_team_id']
                else: row['missing'].append('frozen_name_syllables')
                markets=[]
                if ticker:
                    for endpoint in ('/markets','/historical/markets'):
                        try: markets+=paged(endpoint,{'event_ticker':ticker,'limit':200},'markets',cache)
                        except Exception as exc: manifest['errors'].append({'stage':key+endpoint,'error':str(exc)})
                markets=list({m['ticker']:m for m in markets}.values())
                settled={}
                for m in markets:
                    tid=match_market(m,teams,sport)
                    if not tid: continue
                    settled[tid]={'ticker':m['ticker'],'result':m.get('result'),'status':m.get('status'),'settlement_value_dollars':m.get('settlement_value_dollars'),'settlement_ts':m.get('settlement_ts')}
                    if not m.get('open_time') or utc(m['open_time'])>cutoff or not m.get('created_time') or utc(m['created_time'])>cutoff: continue
                    candles=None
                    q={'start_ts':cutoff_ts-STUDY['quote_max_age_seconds'],'end_ts':cutoff_ts,'period_interval':1}
                    for ep in ('/historical/markets/'+m['ticker']+'/candlesticks','/series/'+series+'/markets/'+m['ticker']+'/candlesticks'):
                        try:
                            data=get(BASE+ep+'?'+urllib.parse.urlencode(q),cache)
                            candles=data.get('candlesticks',[])
                            if candles: break
                        except urllib.error.HTTPError as exc:
                            if exc.code!=404: manifest['errors'].append({'stage':key+'_candles','error':str(exc)})
                        except Exception as exc: manifest['errors'].append({'stage':key+'_candles','error':str(exc)})
                    price=quote(candles or [],cutoff_ts)
                    if price:
                        row['quotes'][tid]={**price,'market_ticker':m['ticker'],'created_time':m['created_time'],'open_time':m['open_time'],'rules_primary':m.get('rules_primary'),'rules_provenance':'current market metadata; original rule version not guaranteed'}
                created=[utc(m['created_time']) for m in markets if m.get('created_time')]
                if ticker and sport=='mlb' and 'timestamped_scheduled_start' in row['missing'] and created:
                    tstart=mlb_ticker_start(ticker)
                    if tstart and min(created)<=cutoff:
                        if tstart==utc(start_utc):
                            row['missing'].remove('timestamped_scheduled_start'); row['schedule_verified_at_cutoff']=True
                            row['schedule_provenance']='Kalshi event ticker HHMM (US/Eastern), event created '+min(created).isoformat()+'; equals current ESPN start'
                        else:
                            row['missing'].append('schedule_conflict'); row['schedule_conflict']={'ticker_start_utc':tstart.isoformat(),'espn_start_utc':start_utc}
                if ticker and markets and not any(m.get('created_time') and utc(m['created_time'])<=cutoff for m in markets):
                    row['missing'].append('market_not_listed_before_cutoff')
                if set(row['quotes'])!=teamids: row['missing'].append('paired_quote_before_cutoff')
                row['missing']=sorted(set(row['missing'])); blind.append(row)
                outcomes[key]={'espn_final':comp.get('status',{}).get('type',{}).get('completed',False),'teams':{str(c['team']['id']):{'score':c.get('score'),'winner':c.get('winner')} for c in teams},'kalshi':settled}
            day+=timedelta(days=1)
        unmatched=sorted(set(event_index)-matched_tickers)
        if unmatched: manifest.setdefault('unmatched_kalshi_events',{})[series]=unmatched
    # Duplicate events: one Kalshi event claimed by two ESPN games, or two ESPN
    # games between the same teams on one day (doubleheaders). Reject all copies.
    by_ticker=collections.Counter(r['id'] for r in blind if not r['id'].split('-')[1:2]==['ESPN'])
    by_pair=collections.Counter((r['sport'],r['day'],tuple(sorted(t['id'] for t in r['teams']))) for r in blind)
    for r in blind:
        if by_ticker.get(r['id'],0)>1: r['missing'].append('duplicate_matchup')
        if by_pair[(r['sport'],r['day'],tuple(sorted(t['id'] for t in r['teams'])))]>1: r['missing'].append('doubleheader')
        r['missing']=sorted(set(r['missing']))
        r['structural_exclusions']=sorted(set(r['missing'])&STRUCTURAL)
    save(out/'blind_inputs.json',blind); save(out/'outcomes.json',outcomes)
    manifest['counts']['scoreboard_games']=len(blind); manifest['counts']['paired_quotes']=sum(len(r['quotes'])==2 for r in blind)
    manifest['blind_sha256']=digest(out/'blind_inputs.json'); manifest['outcomes_sha256']=digest(out/'outcomes.json')
    save(out/'manifest.json',manifest); print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    if os.environ.get('GITHUB_ACTIONS')!='true': raise SystemExit('Collection is relay-only; run on GitHub Actions. Local replay reads saved relay files only.')
    main()
