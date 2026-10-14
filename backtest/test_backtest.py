import unittest
from collect import quote,ticker_day,match_market
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

if __name__=='__main__': unittest.main()
