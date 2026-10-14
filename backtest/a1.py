"""GD-C1.0-BT-A1 approximate cohort: outcome-blind replay, lock, then scoring.

  python3 backtest/a1.py predict   # never opens outcomes.json
  python3 backtest/a1.py score     # verifies the lock, then reads outcomes

Inputs: data/backtest/a1/<chunk>/ (relay collection), backtest/annotations_a1.json
(venues + team syllables, frozen before predict), backtest/study_a1.json.
Relaxations are listed in study_a1.json and repeated in every output.
"""
import collections
import json
import statistics
import sys
from pathlib import Path
from common import ROOT, STUDY, digest, save, utc, validate_engine
from replay import predict
from score import settle, wilson

DATA = ROOT.parent / 'data' / 'backtest' / 'a1'
A1 = json.loads((ROOT / 'study_a1.json').read_text())
ANN = ROOT / 'annotations_a1.json'
for k in ('favorite_min_mid', 'max_spread', 'daily_pick_limit'):
    assert A1[k] == STUDY[k], f'A1 {k} must equal the inherited study value'


def chunks():
    return sorted(p for p in DATA.iterdir() if (p / 'manifest.json').exists())


def relax(row, ann):
    row = json.loads(json.dumps(row)); miss = set(row['missing'])
    if row['sport'] not in A1['sports']: return None
    quotes = row['quotes']
    if len(quotes) == 2:
        fav = max(quotes, key=lambda k: quotes[k]['mid'])
        row['sportsbook_favorite_team_id'] = fav            # relaxation 1
        miss.discard('timestamped_sportsbook_favorite')
    if row['sport'] != 'mlb': miss.discard('timestamped_scheduled_start')   # relaxation 2
    v = ann['venues'].get(row['venue']['id'])
    if v and v.get('verified'):
        row['coordinates'] = {'lat': v['lat'], 'lon': v['lon'], 'source': v['source']}; miss.discard('verified_venue_coordinates')
    decl = {t['id']: ann['teams'].get(row['sport'] + ':' + t['id']) for t in row['teams']}
    if all(d and d['canonical_name'] == t['name'] for d, t in zip(decl.values(), row['teams'])):
        row['syllables_by_team_id'] = {k: d['words'] for k, d in decl.items()}; miss.discard('frozen_name_syllables')
    row['missing'] = sorted(miss)
    return row


def cmd_predict():
    ann = json.loads(ANN.read_text()); rows, inputs = [], {}
    for c in chunks():
        m = json.loads((c / 'manifest.json').read_text())
        assert digest(c / 'blind_inputs.json') == m['blind_sha256'], f'{c.name}: blind inputs changed'
        inputs[c.name] = {'blind_sha256': m['blind_sha256'], 'outcomes_sha256': m['outcomes_sha256'], 'errors': m['errors']}
        rows += [r for r in (relax(x, ann) for x in json.loads((c / 'blind_inputs.json').read_text())) if r]
    engine = validate_engine()
    records = predict(rows, engine)
    out = {'study_id': A1['study_id'], 'relaxations': A1['relaxations'], 'self_tests': 'passed', 'inputs': inputs, 'records': records}
    save(DATA / 'predictions_a1.json', out)
    save(DATA / 'prediction_lock_a1.json', {'predictions_sha256': digest(DATA / 'predictions_a1.json'), 'annotations_sha256': digest(ANN),
         'study_a1_sha256': digest(ROOT / 'study_a1.json'), 'engine_sha256': digest(ROOT / 'gd_engine.py'),
         'chunks': inputs})
    c = collections.Counter(r['disposition'] for r in records)
    print(json.dumps({'games': len(records), 'dispositions': c}, indent=1))


def cmd_score():
    lock = json.loads((DATA / 'prediction_lock_a1.json').read_text())
    assert digest(DATA / 'predictions_a1.json') == lock['predictions_sha256'], 'Predictions changed after lock'
    assert digest(ANN) == lock['annotations_sha256'], 'Annotations changed after lock'
    assert digest(ROOT / 'study_a1.json') == lock['study_a1_sha256'], 'Study changed after lock'
    outcomes = {}
    for name, info in lock['chunks'].items():
        f = DATA / name / 'outcomes.json'
        assert digest(f) == info['outcomes_sha256'], f'{name}: outcomes changed after collection'
        outcomes.update(json.loads(f.read_text()))
    pred = json.loads((DATA / 'predictions_a1.json').read_text()); records = pred['records']
    picks = [r for r in records if r['disposition'] == 'pick']; scored = []
    for r in picks:
        o = outcomes.get(r['id'], {}); res = settle(r, o)
        base = settle(dict(r, selected_team_id=r['favorite_team_id']), o)
        side_is_fav = r['selected_team_id'] == r['favorite_team_id']
        scored.append({'id': r['id'], 'day': r['day'], 'sport': r['sport'], 'side': 'favorite' if side_is_fav else 'underdog',
                       'result': res, 'market_favorite_result': base, 'ask': r['ask'], 'selected_mid': r['selected_mid'],
                       'gross_price_proxy': (1 - r['ask'] if res == 'HIT' else -r['ask']) if res in ('HIT', 'MISS') else None})

    def block(rows):
        c = collections.Counter(s['result'] for s in rows); n = c['HIT'] + c['MISS']
        settled = [s for s in rows if s['result'] in ('HIT', 'MISS')]
        fb = [s for s in rows if s['market_favorite_result'] in ('HIT', 'MISS')]
        return {'picks': len(rows), 'settled': n, 'hits': c['HIT'], 'misses': c['MISS'], 'pending': c['PENDING'],
                'voids_or_pushes': c['PUSH_OR_VOID'], 'discrepancies': c['DISCREPANCY'],
                'hit_rate': round(c['HIT'] / n, 4) if n else None,
                'wilson95': [round(x, 4) for x in wilson(c['HIT'], n)] if wilson(c['HIT'], n) else None,
                'expected_hits_from_mids': round(sum(s['selected_mid'] for s in settled), 2),
                'market_favorite_hits_same_events': sum(s['market_favorite_result'] == 'HIT' for s in fb),
                'market_favorite_settled': len(fb),
                'gross_price_proxy': round(sum(s['gross_price_proxy'] for s in settled), 2) if settled else None,
                'ask_capital': round(sum(s['ask'] for s in settled), 2) if settled else None}

    disp = collections.Counter(r['disposition'] for r in records)
    missing = collections.Counter(x for r in records for x in r['missing'])
    summary = {'study_id': A1['study_id'], 'APPROXIMATE': True, 'relaxations': A1['relaxations'],
               'coverage': {'games': len(records), 'dispositions': dict(disp), 'missing_or_excluded': dict(missing),
                            'collector_errors': {k: len(v['errors']) for k, v in lock['chunks'].items()}},
               'overall': block(scored),
               'by_sport': {sp: block([s for s in scored if s['sport'] == sp]) for sp in sorted({s['sport'] for s in scored})},
               'by_side': {sd: block([s for s in scored if s['side'] == sd]) for sd in ('favorite', 'underdog')},
               'net_return': None, 'fees': 'not modelled (historical fee schedule unverified)',
               'limitations': ['Approximate cohort; not GD-C1.0 validity evidence and not GPT or Claude performance.',
                               'Prices are one-minute candle-close asks: no depth, no guaranteed fill.',
                               'Mechanical ranking and syllable rule; prospective practice was qualitative.',
                               'Selection is not independent across games on one day (shared slow-planet positions).'],
               'scored': scored}
    save(DATA / 'summary_a1.json', summary)
    print(json.dumps({k: summary[k] for k in ('coverage', 'overall', 'by_sport', 'by_side')}, indent=1))


if __name__ == '__main__':
    {'predict': cmd_predict, 'score': cmd_score}[sys.argv[1]]()
