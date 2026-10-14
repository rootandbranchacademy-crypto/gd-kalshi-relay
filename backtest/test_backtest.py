import unittest
import json,os,tempfile,shutil
from datetime import datetime,timezone
from pathlib import Path
from collect import quote,ticker_day,match_market,mlb_ticker_start,codes
from collect_odds import evidence_for
from syllables import declare,engine_index
from replay import syllable_score,predict
from score import settle,wilson

class IntegrityTests(unittest.TestCase):
    def test_future_quote_cannot_be_used(self):
        candles=[{'end_period_ts':101,'yes_bid':{'close':'0.6'},'yes_ask':{'close':'0.62'}},{'end_period_ts':99,'yes_bid':{'close':'0.4'},'yes_ask':{'close':'0.42'}}]
        self.assertEqual(quote(candles,100)['ask'],0.42)
        self.assertIsNone(quote(candles,20000))
    def test_live_cents_and_historical_dollars(self):
        a={'end_period_ts':99,'yes_bid':{'close':40},'yes_ask':{'close':42}}
        b={'end_period_ts':99,'yes_bid':{'close_dollars':'0.4000'},'yes_ask':{'close_dollars':'0.4200'}}
        self.assertEqual(quote([a],100)['ask'],quote([b],100)['ask'])
    def test_crossed_quote_rejected(self):
        self.assertIsNone(quote([{'end_period_ts':99,'yes_bid':{'close':'0.9'},'yes_ask':{'close':'0.1'}}],100))
    def test_double_name_match_and_both_sides(self):
        self.assertEqual(syllable_score('pa/pha',[{'a':['pa'],'b':['pha']},{}]),18)
        self.assertEqual(syllable_score('pa/pha',[{'a':['pa']},{'b':['pha']}]),0)
    def test_disagreement_is_not_hit(self):
        record={'selected_team_id':'1'}; outcome={'espn_final':True,'kalshi':{'1':{'result':'yes','status':'finalized'}},'teams':{'1':{'winner':False}}}
        self.assertEqual(settle(record,outcome),'DISCREPANCY')
        outcome['kalshi']['1']['settlement_value_dollars']='0.50'
        self.assertEqual(settle(record,outcome),'PUSH_OR_VOID')
    def test_nfl_ticker_date_is_not_start(self):
        self.assertEqual(str(ticker_day('KXNFLGAME-26OCT11BALATL')),'2026-10-11')
        self.assertIsNone(ticker_day('unknown'))
    def test_wilson_reporting_gate(self):
        self.assertIsNone(wilson(1,4)); self.assertLess(wilson(1,5)[0],0.2)
    def test_market_suffix_resolves_truncated_label(self):
        teams=[{'team':{'id':'1','displayName':'Los Angeles Dodgers','abbreviation':'LAD'}},{'team':{'id':'2','displayName':'Milwaukee Brewers','abbreviation':'MIL'}}]
        self.assertEqual(match_market({'ticker':'KXMLBGAME-26APR142000MILLAD-LAD','yes_sub_title':'Los Angeles D'},teams),'1')
    def test_missing_inputs_cannot_create_pick(self):
        class Swe:
            @staticmethod
            def julday(*a): return 1
        class Engine:
            swe=Swe()
            @staticmethod
            def timing_flags(jd): return []
            @staticmethod
            def evaluate(*a): raise AssertionError('Missing data must not reach chart scoring')
        r=predict([{'id':'fixture','day':'2026-04-14','sport':'mlb','cutoff_utc':'2026-04-14T13:00Z','start_utc':'2026-04-14T23:00Z','missing':['verified_venue_coordinates']}],Engine())[0]
        self.assertEqual(r['disposition'],'missing_data'); self.assertIsNone(r['selected_team_id'])

class FailurePathTests(unittest.TestCase):
    """BT1.1 additions: each test names a way the pipeline could leak or misread data."""
    def test_ambiguous_float_units_rejected(self):
        # 0.42 as a JSON number could be dollars or cents; it must not become 0.0042.
        self.assertIsNone(quote([{'end_period_ts':99,'yes_bid':{'close':0.40},'yes_ask':{'close':0.42}}],100))
        self.assertEqual(quote([{'end_period_ts':99,'yes_bid':{'close':40.0},'yes_ask':{'close':42.0}}],100)['ask'],0.42)
    def test_stale_quote_rejected(self):
        c=[{'end_period_ts':100-10801,'yes_bid':{'close':'0.4'},'yes_ask':{'close':'0.42'}}]
        self.assertIsNone(quote(c,100))
    def test_quote_exactly_at_cutoff_allowed(self):
        self.assertEqual(quote([{'end_period_ts':100,'yes_bid':{'close':'0.4'},'yes_ask':{'close':'0.42'}}],100)['ask'],0.42)
    def test_verified_alias_only(self):
        teams=[{'team':{'id':'1','displayName':'Chicago White Sox','abbreviation':'CHW'}},{'team':{'id':'2','displayName':'Tampa Bay Rays','abbreviation':'TB'}}]
        self.assertEqual(match_market({'ticker':'KXMLBGAME-26APR141840CWSTB-CWS','yes_sub_title':'Chicago WS'},teams,'mlb'),'1')
        self.assertEqual(codes('mlb',{'abbreviation':'XYZ'}),{'XYZ'})  # unlisted code: no guess
    def test_mlb_ticker_start_is_eastern_and_dst_aware(self):
        self.assertEqual(mlb_ticker_start('KXMLBGAME-26APR141840CHCPHI'),datetime(2026,4,14,22,40,tzinfo=timezone.utc))
        self.assertEqual(mlb_ticker_start('KXMLBGAME-26NOV031840CHCPHI'),datetime(2026,11,3,23,40,tzinfo=timezone.utc))
        self.assertIsNone(mlb_ticker_start('KXNHLGAME-26APR14DALBUF'))
    def test_odds_snapshot_after_cutoff_rejected(self):
        game={'competitions':[{'competitors':[{'team':{'id':'1','displayName':'A A'}},{'team':{'id':'2','displayName':'B B'}}]}]}
        cutoff=datetime(2026,4,14,13,0,tzinfo=timezone.utc)
        snap={'timestamp':'2026-04-14T13:05:00Z','data':[]}
        self.assertEqual(evidence_for(game,snap,cutoff)[1],'snapshot_after_cutoff_or_missing')
        book=lambda upd,pa,pb:[{'key':'draftkings','markets':[{'key':'h2h','last_update':upd,'outcomes':[{'name':'A A','price':pa},{'name':'B B','price':pb}]}]}]
        ev={'home_team':'A A','away_team':'B B','commence_time':'2026-04-14T23:05:00Z'}
        snap={'timestamp':'2026-04-14T12:55:00Z','data':[dict(ev,bookmakers=book('2026-04-14T12:50:00Z',-150,130))]}
        got,why=evidence_for(game,snap,cutoff); self.assertIsNone(why); self.assertEqual(got['sportsbook_favorite_team_id'],'1')
        snap['data'][0]['bookmakers']=book('2026-04-14T13:01:00Z',-150,130)
        self.assertEqual(evidence_for(game,snap,cutoff)[1],'line_after_cutoff')
        snap['data'][0]['bookmakers']=book('2026-04-14T12:50:00Z',-110,-110)
        self.assertEqual(evidence_for(game,snap,cutoff)[1],'pick_em')
        snap['data'].append(dict(ev,bookmakers=book('2026-04-14T12:50:00Z',-150,130)))
        self.assertEqual(evidence_for(game,snap,cutoff)[1],'duplicate_odds_events')
    def test_missing_annotation_each_gate_blocks_charting(self):
        class Swe:
            @staticmethod
            def julday(*a): return 1
        class Engine:
            swe=Swe()
            @staticmethod
            def timing_flags(jd): return []
            @staticmethod
            def evaluate(*a): raise AssertionError('chart reached despite missing evidence')
        for gap in ('timestamped_scheduled_start','timestamped_sportsbook_favorite','frozen_name_syllables','duplicate_matchup','doubleheader','schedule_conflict'):
            r=predict([{'id':'x','day':'2026-04-14','sport':'mlb','cutoff_utc':'2026-04-14T13:00Z','start_utc':'2026-04-14T23:00Z','missing':[gap]}],Engine())[0]
            self.assertEqual(r['disposition'],'missing_data',gap)
    def test_timing_flag_error_never_passes(self):
        class Swe:
            @staticmethod
            def julday(*a): return 1
        class Engine:
            swe=Swe()
            @staticmethod
            def timing_flags(jd): return ['eclipse check error solar: boom']
        r=predict([{'id':'x','day':'2026-04-14','sport':'mlb','cutoff_utc':'2026-04-14T13:00Z','start_utc':'2026-04-14T23:00Z','missing':[]}],Engine())[0]
        self.assertIn('timing_calculation_error',r['missing']); self.assertIsNone(r['selected_team_id'])
    def test_settlement_requires_both_sources(self):
        self.assertEqual(settle({'selected_team_id':'1'},{'espn_final':False,'kalshi':{'1':{'result':'yes','status':'finalized'}},'teams':{'1':{'winner':True}}}),'PENDING')
        self.assertEqual(settle({'selected_team_id':'1'},{'espn_final':True,'kalshi':{'1':{'result':'yes','status':'active'}},'teams':{'1':{'winner':True}}}),'PENDING')
    def test_tampered_lock_stops_scoring(self):
        import score
        d=Path(tempfile.mkdtemp())
        try:
            for name,obj in (('predictions.json',{'records':[],'self_tests':'passed'}),('outcomes.json',{}),('manifest.json',{'start':'a','end':'b','counts':{},'errors':[]})):
                (d/name).write_text(json.dumps(obj))
            from common import digest,ROOT
            (d/'prediction_lock.json').write_text(json.dumps({'predictions_sha256':digest(d/'predictions.json'),'outcomes_sha256':digest(d/'outcomes.json'),'study_sha256':digest(ROOT/'study.json')}))
            (d/'predictions.json').write_text(json.dumps({'records':[{'disposition':'pick'}],'self_tests':'passed'}))
            import sys; argv=sys.argv; sys.argv=['score',str(d)]
            try:
                with self.assertRaisesRegex(AssertionError,'Predictions changed'): score.main()
            finally: sys.argv=argv
        finally: shutil.rmtree(d)
    def test_syllable_rule_is_name_only_and_deterministic(self):
        table={'Lib':['ra','ri','ru','re','ro','ta','ti','tu','te'],'Leo':['ta(r)','ti(r)'],'Vir':['pa','pi'],'Gem':['nga/pha']}
        cmu={'flyers':[['F','L','AY1','ER0','Z']],'titans':[['T','AY1','T','AH0','N','Z']]}
        a=declare('Philadelphia Flyers',table,cmu); b=declare('Philadelphia Flyers',table,cmu)
        self.assertEqual(a,b)
        self.assertIn('pha',a['words']['Flyers']); self.assertIn('pa',a['words']['Flyers'])
        self.assertEqual(declare('Philadelphia 76ers',table,cmu)['words'].get('76ers'),None)
        self.assertIn('ta(r)',declare('Tennessee Titans',table,cmu)['words']['Titans'])

if __name__=='__main__': unittest.main()
