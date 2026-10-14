"""Outcome-blind prediction stage. Never opens outcomes.json or raw responses."""
import argparse
import json
import statistics
from pathlib import Path
from common import STUDY, ROOT, utc, save, digest, validate_engine

def syllable_score(syllable, words_by_side):
    variants=set(syllable.split('/'))
    matches=[sum(bool(variants.intersection(candidates)) for candidates in words.values()) for words in words_by_side]
    if all(matches) or not any(matches): return 0
    index=0 if matches[0] else 1
    return (1 if index==0 else -1)*(18 if matches[index]>=2 else 16)

def evidence_families(evidence, sign, syllable):
    groups=[evidence['vh'],evidence['sky'],evidence['d1'],evidence['d9']+evidence['combo'],evidence['sub']+evidence['arr'],evidence['star'],syllable]
    return sum(sign*x>0 for x in groups)

def predict(rows, engine):
    records=[]
    for row in rows:
        r={'id':row['id'],'day':row['day'],'sport':row['sport'],'cutoff_utc':row['cutoff_utc'],'missing':list(row['missing']),'selected_team_id':None,'ask':None,'disposition':'missing_data'}
        t=utc(row['start_utc']); jd=engine.swe.julday(t.year,t.month,t.day,t.hour+t.minute/60+t.second/3600)
        flags=engine.timing_flags(jd); r['timing_flags']=flags
        if any('error' in x.casefold() for x in flags):
            r['missing'].append('timing_calculation_error'); records.append(r); continue
        if flags:
            r['disposition']='timing_exclusion'; records.append(r); continue
        if row['missing']: records.append(r); continue
        quotes=row['quotes']; ids=sorted(quotes,key=lambda k:quotes[k]['mid'],reverse=True)
        if len(ids)!=2:
            r['missing'].append('paired_quotes'); records.append(r); continue
        favorite,dog=ids
        if quotes[favorite]['mid']<STUDY['favorite_min_mid'] or quotes[favorite]['mid']==quotes[dog]['mid']:
            r['disposition']='favorite_below_threshold'; records.append(r); continue
        if favorite!=row['sportsbook_favorite_team_id']:
            r['disposition']='favorite_disagreement'; records.append(r); continue
        # Defense in depth: malformed annotations/quote timestamps cannot bypass causality.
        if t<=utc(row['cutoff_utc']) or any(utc(q['as_of_utc'])>utc(row['cutoff_utc']) or (utc(row['cutoff_utc'])-utc(q['as_of_utc'])).total_seconds()>STUDY['quote_max_age_seconds'] for q in quotes.values()):
            r['missing'].append('causality_violation'); records.append(r); continue
        c=row['coordinates']; totals={}; base={}
        for offset in range(-10,11):
            e=engine.evaluate(jd+offset/1440,c['lat'],c['lon']); base[offset]=e
            name=syllable_score(e['syl'][0],[row['syllables_by_team_id'][favorite],row['syllables_by_team_id'][dog]])
            totals[offset]=e['total']+name
        t0=totals[0]; sign=1 if t0>0 else -1
        r.update({'t0':t0,'minute_totals':totals,'agree5':sum(sign*totals[i]>3 for i in range(-5,6)),'agree10':sum(sign*totals[i]>3 for i in range(-10,11)),'favorite_team_id':favorite,'fav_mid':quotes[favorite]['mid']})
        if abs(t0)<=3 or r['agree5']<9 or r['agree10']<15:
            r['disposition']='no_call_or_unstable'; records.append(r); continue
        side=favorite if sign>0 else dog; q=quotes[side]
        if q['ask']-q['bid']>STUDY['max_spread']:
            r['disposition']='spread_exception_not_predeclared'; records.append(r); continue
        sy=totals[0]-base[0]['total']
        r.update({'disposition':'eligible_reserve','selected_team_id':side,'market_ticker':q['market_ticker'],'ask':q['ask'],'quote_as_of_utc':q['as_of_utc'],'selected_mid':q['mid'],'supporting_families':evidence_families(base[0],sign,sy),'abs_median5':abs(statistics.median(totals[i] for i in range(-5,6))),'engine_modules':{k:base[0][k] for k in ('vh','sky','d1','d9','combo','sub','arr','star')},'syllable_score':sy,'price_limitation':'candle-close ask proxy; historical depth and fill unavailable','cohort':'frozen-engine replay, not GPT or Claude'})
        records.append(r)
    for day in sorted({r['day'] for r in records}):
        eligible=[r for r in records if r['day']==day and r['disposition']=='eligible_reserve']
        eligible.sort(key=lambda r:(-r['supporting_families'],-r['agree5'],-r['agree10'],-r['abs_median5'],r['id']))
        for rank,r in enumerate(eligible,1):
            r['rank']=rank
            if rank<=STUDY['daily_pick_limit']: r['disposition']='pick'
    return records

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('folder'); args=ap.parse_args(); folder=Path(args.folder)
    manifest=json.loads((folder/'manifest.json').read_text())
    assert digest(folder/'blind_inputs.json')==manifest['blind_sha256'], 'Blind inputs changed'
    assert digest(ROOT/'study.json')==manifest['study_sha256'], 'Study changed after collection'
    assert digest(ROOT/'annotations.json')==manifest['annotations_sha256'], 'Annotations changed after collection'
    engine=validate_engine()
    records=predict(json.loads((folder/'blind_inputs.json').read_text()),engine)
    save(folder/'predictions.json',{'study_id':STUDY['study_id'],'blind_sha256':manifest['blind_sha256'],'study_sha256':manifest['study_sha256'],'self_tests':'passed','records':records})
    save(folder/'prediction_lock.json',{'predictions_sha256':digest(folder/'predictions.json'),'outcomes_sha256':manifest['outcomes_sha256'],'study_sha256':manifest['study_sha256']})
    print('Predictions saved and locked before scoring:', len(records))

if __name__=='__main__': main()
