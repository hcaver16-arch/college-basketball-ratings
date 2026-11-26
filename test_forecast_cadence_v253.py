from datetime import datetime, timedelta, timezone
import unittest
from prospective_archive_v97 import event_data, new_forecasts, iso

NOW = datetime(2026,11,25,18,tzinfo=timezone.utc)
def event(state='pre', name='STATUS_SCHEDULED', minutes=90):
    return event_data({'id':'123','date':iso(NOW+timedelta(minutes=minutes)),
      'status':{'type':{'state':state,'name':name,'completed':state=='post'}},
      'competitions':[{'neutralSite':True,'competitors':[
      {'homeAway':'home','team':{'id':'200'}},
      {'homeAway':'away','team':{'id':'201'}}]}]})

MODEL = dict(id='official_saved_v97', asof=NOW-timedelta(hours=2),
             ratings={'200':8,'201':3},file='snapshot',sha256='test',type='official_saved_model')

class ForecastCadence(unittest.TestCase):
    def test_new_matchup_and_immutable_lock(self):
        for division in ('mens','womens'):
            def lock(games, existing=(), now=NOW, lead=30):
                return new_forecasts(games,[MODEL],existing,now,'2026-27',division,lead)
            self.assertEqual(lock({}),[])
            g=event()
            rows=lock({'123':g})
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['predicted_home_margin'],5)
            self.assertEqual(lock({'123':g},rows),[])
            for bad in (event('in','STATUS_IN_PROGRESS'),event('post','STATUS_FINAL'),
                        event('pre','STATUS_POSTPONED'),event('pre','STATUS_CANCELED'),
                        event('', ''),event(minutes=30),event(minutes=-1)):
                self.assertEqual(lock({'123':bad},lead=0),[])
            self.assertEqual(lock({'123':g},now=NOW+timedelta(minutes=60)),[])
if __name__=='__main__':
    unittest.main()
