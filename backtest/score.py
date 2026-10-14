"""Settlement stage: verifies prediction lock before revealing outcomes."""
import argparse
import collections
import html
import json
import math
from pathlib import Path
from common import STUDY, ROOT, save, digest

def wilson(hits,n):
    if n<5: return None
    z=1.95996398454; p=hits/n; d=1+z*z/n
    center=(p+z*z/(2*n))/d; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [center-half,center+half]

def settle(record,outcome):
    side=record['selected_team_id']; k=outcome.get('kalshi',{}).get(side,{})
    if not outcome.get('espn_final') or k.get('status')!='finalized': return 'PENDING'
    value=k.get('settlement_value_dollars')
    if value is not None and float(value) not in (0,1): return 'PUSH_OR_VOID'
    result=k.get('result'); winner=outcome.get('teams',{}).get(side,{}).get('winner')
    if result not in ('yes','no') or winner is None: return 'PENDING'
    if (result=='yes')!=bool(winner): return 'DISCREPANCY'
    return 'HIT' if result=='yes' else 'MISS'

def expansion_gate(records,manifest):
    g=STUDY['expansion_gate']; structural=set(g['structural_exclusions'])
    gaps=collections.Counter(x for r in records for x in r['missing'] if x not in structural)
    excluded=sum(bool(set(r['missing'])&structural) for r in records)
    charted=sum('t0' in r for r in records)
    frac=excluded/len(records) if records else 1.0
    passed=(not manifest['errors'] and bool(records) and sum(gaps.values())<=g['evidence_gaps_allowed']
            and frac<=g['max_structural_exclusion_fraction'] and charted>=g['min_games_reaching_charts'])
    return {'version':g['version'],'passed':passed,'evidence_gaps':dict(gaps),'structural_exclusions':excluded,
            'structural_fraction':round(frac,4),'games_reaching_charts':charted,'collector_errors':len(manifest['errors'])}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('folder'); args=ap.parse_args(); folder=Path(args.folder)
    lock=json.loads((folder/'prediction_lock.json').read_text())
    assert digest(folder/'predictions.json')==lock['predictions_sha256'], 'Predictions changed after lock'
    assert digest(folder/'outcomes.json')==lock['outcomes_sha256'], 'Outcomes changed after collection'
    assert digest(ROOT/'study.json')==lock['study_sha256'], 'Study changed after prediction lock'
    prediction=json.loads((folder/'predictions.json').read_text()); outcomes=json.loads((folder/'outcomes.json').read_text()); manifest=json.loads((folder/'manifest.json').read_text())
    records=prediction['records']; picks=[r for r in records if r['disposition']=='pick']; counts=collections.Counter(); scored=[]
    for r in picks:
        result=settle(r,outcomes.get(r['id'],{})); counts[result]+=1
        baseline=dict(r,selected_team_id=r['favorite_team_id']); baseline_result=settle(baseline,outcomes.get(r['id'],{}))
        scored.append({'id':r['id'],'sport':r['sport'],'result':result,'market_favorite_result':baseline_result,'ask':r['ask'],'gross_price_proxy':(1 if result=='HIT' else 0)-r['ask'] if result in ('HIT','MISS') else None,'net_return':None})
    n=counts['HIT']+counts['MISS']; missing=collections.Counter(x for r in records for x in r['missing']); dispositions=collections.Counter(r['disposition'] for r in records)
    gate=expansion_gate(records,manifest)
    summary={'study_id':STUDY['study_id'],'period':[manifest['start'],manifest['end']],'self_tests':prediction['self_tests'],'games':len(records),'paired_quotes':manifest['counts'].get('paired_quotes',0),'dispositions':dict(dispositions),'missing_inputs':dict(missing),'collector_errors':manifest['errors'],'published_backtest_picks':len(picks),'settled':n,'hits':counts['HIT'],'misses':counts['MISS'],'pending':counts['PENDING'],'voids_or_pushes':counts['PUSH_OR_VOID'],'discrepancies':counts['DISCREPANCY'],'hit_rate':counts['HIT']/n if n else None,'wilson95':wilson(counts['HIT'],n),'favorite_baseline_hits':sum(s['market_favorite_result']=='HIT' for s in scored),'favorite_baseline_settled':sum(s['market_favorite_result'] in ('HIT','MISS') for s in scored),'gross_price_proxy':sum(s['gross_price_proxy'] for s in scored if s['gross_price_proxy'] is not None) if n else None,'verified_net_return':None,'gpt_performance':None,'claude_performance':None,'full_period_ready':gate['passed'],'expansion_gate':gate,'bt10_gate_would_pass':not manifest['errors'] and bool(records) and not missing,'prediction_lock':lock,'scored':scored,'limitations':[STUDY['scope'],'Missing-input counts can overlap timing exclusions. Missing-data days are not successful full-method abstentions.','Current historical schedules may incorporate post-event corrections. Final scores are held separately; this does not erase historical hindsight in metadata.','GPT/Claude comparison requires separately locked outcome-hidden model selections; none have been generated.','Candle-close quotes cannot establish historical executable depth or fees. Gross figures, when present, are price-proxy simulations only.']}
    save(folder/'summary.json',summary)
    def table(mapping):
        return '<table>'+''.join('<tr><th>'+html.escape(str(k))+'</th><td>'+html.escape(str(v))+'</td></tr>' for k,v in mapping.items())+'</table>'
    page='<!doctype html><html><meta charset="utf-8"><title>GD-C1.0 retrospective pilot</title><style>body{font:16px system-ui;max-width:960px;margin:40px auto;padding:0 20px;color:#172b3a}table{border-collapse:collapse;margin:20px 0}th,td{border:1px solid #ccd4dc;padding:8px;text-align:left}h1{color:#14334a}li{margin:10px 0}.status{padding:16px;background:#fff1d5}</style><h1>GD-C1.0 retrospective pilot</h1><p>'+html.escape(' to '.join(summary['period']))+'</p><p class="status">'+('Pilot coverage passed.' if summary['full_period_ready'] else 'Pilot coverage incomplete. Six-month scoring is withheld.')+'</p>'+table({k:summary[k] for k in ('games','paired_quotes','published_backtest_picks','settled','hits','misses','hit_rate','gross_price_proxy','verified_net_return','self_tests')})+'<h2>Disposition</h2>'+table(summary['dispositions'])+'<h2>Missing inputs</h2>'+table(summary['missing_inputs'])+'<h2>Collector errors</h2><pre>'+html.escape(json.dumps(summary['collector_errors'],indent=2))+'</pre><h2>Limits</h2><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in summary['limitations'])+'</ul></html>'
    (folder/'report.html').write_text(page)
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
