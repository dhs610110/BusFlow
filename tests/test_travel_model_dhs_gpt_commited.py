"""Model mechanics and real repository integration, not prediction accuracy."""
import csv, tempfile, unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from services.integrated_data_dhs_gpt_commited import DataStore
from services.integrated_recommendation_dhs_gpt_commited import recommend, adjusted_travel
from services.travel_model_dhs_gpt_commited import highway_hours

class NoWeather:
    def weather(self,*args):return dict(available=False)

class ModelTests(unittest.TestCase):
    def setUp(self):self.s=DataStore();self.t=datetime(2026,9,21,7)
    def journey(self,route='5003A',idx=-1,destidx=-1):
        spec=self.s.catalog[route];stop=spec['boarding'][idx]
        dest=self.s.resolve_destination(route,spec['destinations'][destidx]['id'],allow_model=True)
        return self.s.journey(route,stop,dest,self.t)
    def test_model_provenance_and_csv_evidence(self):
        x=self.journey();self.assertTrue(x['estimated']);self.assertEqual(x['sample_count'],0)
        self.assertEqual(x['highway_evidence']['source'],'data/highway_speed.csv')
        self.assertGreater(x['highway_evidence']['sample_count'],0)
        self.assertAlmostEqual(x['total'],x['pre']+x['core']+x['after'])
    def test_farther_stop_adds_only_local_time(self):
        a=self.journey(idx=-1);b=self.journey(idx=-2)
        self.assertGreater(b['pre'],a['pre']);self.assertEqual(b['core'],a['core'])
    def test_earlier_seoul_destination_shorter(self):
        self.assertLess(self.journey(destidx=2)['core'],self.journey()['core'])
    def test_rain_only_changes_core(self):
        x=self.journey(idx=-2);r=adjusted_travel(x,'5003A',self.t,dict(available=True,rainfall_mm_per_hour=3))
        self.assertEqual(r['pre_minutes'],x['pre']);self.assertAlmostEqual(r['minutes'],x['pre']+x['core']*r['weight'])
    def test_reverse_does_not_copy_direction_or_ids(self):
        dest=self.s.resolve_destination('5003B','기흥역6번출구',allow_model=True)
        self.assertIsNone(dest['realtime_id']);x=self.journey('5003B')
        self.assertEqual(x['highway_evidence']['source'],'southbound_assumption');self.assertEqual(x['core'],0)
        r=adjusted_travel(x,'5003B',self.t,dict(available=True,rainfall_mm_per_hour=10))
        self.assertEqual(r['minutes'],x['total']);self.assertFalse(r['weather_applied'])
    def test_observed_whole_trip_wins(self):
        obs={'total':31,'source':'observed_vehicle_trips'}
        with patch.object(self.s,'travel',return_value=obs):self.assertIs(self.journey(),obs)
    def test_four_routes_work_without_realtime_db(self):
        for route in ['5001A','5003A','5001B','5003B']:
            spec=self.s.catalog[route];evening=route.endswith('B')
            payload=dict(date='2026-09-21',commute_mode='evening' if evening else 'morning',departure_time='17:00' if evening else '07:00',arrival_time='20:00' if evening else '10:00',selected_boarding_stations=[dict(route_name=route,id=spec['boarding'][-1]['id'])],destination=spec['destinations'][-1]['name'])
            r=recommend(self.s,NoWeather(),payload,now=datetime(2026,9,18));self.assertEqual(r['status'],'ok',route)
            self.assertTrue(all(c['travel_estimated'] and '추정' in c['stability_grade'] for c in r['candidates']))
            self.assertTrue(all(c['travel_scenario_minutes'][0]<c['travel_time_minutes']<c['travel_scenario_minutes'][1] for c in r['candidates']))
    def test_short_deadline_still_excludes_modeled_late_trip(self):
        spec=self.s.catalog['5003A'];p=dict(date='2026-09-21',departure_time='07:00',arrival_time='07:15',commute_mode='morning',selected_boarding_stations=[dict(route_name='5003A',id=spec['boarding'][-1]['id'])],destination='신논현역')
        self.assertFalse(recommend(self.s,NoWeather(),p,now=datetime(2026,9,18))['candidates'])
    def test_constant_speed_space_integration_and_direction_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'speed.csv'
            with p.open('w') as f:
                w=csv.DictWriter(f,fieldnames=['route_no','direction','date','hour','km','avg_speed']);w.writeheader()
                for km in [392.5,394,395,399,401,404,407,410,415.3]:
                    w.writerow(dict(route_no='0010',direction='E',date='2026-09-01',hour=7,km=km,avg_speed=60))
                    w.writerow(dict(route_no='0010',direction='S',date='2026-09-01',hour=7,km=km,avg_speed=10))
            rows=highway_hours(str(p),p.stat().st_mtime_ns,392.5,415.3,9)
            self.assertEqual(len(rows),1);self.assertAlmostEqual(rows[0]['minutes'],22.8)
    def test_highway_does_not_use_future_records(self):
        minutes,source=self.s.travel_model.highway(datetime(2025,1,1,7),self.s.comparable)
        self.assertEqual(source['source'],'assumed_speed');self.assertEqual(source['sample_count'],0)
    def test_reverse_existing_local_sections_are_preserved(self):
        self.t=datetime(2026,9,21,20);x=self.journey('5001B',idx=0)
        self.assertTrue(any('기존 서울 구간 기록 평균' in n for n in x['notes']))

if __name__=='__main__':unittest.main()
