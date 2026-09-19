"""Read existing BusFlow data without modifying source files or databases.
All timestamps are naive Asia/Seoul local time, matching the existing collectors.
"""
from __future__ import annotations
import ast
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from services.workbook_data_dhs_gpt_commited import WorkbookData

ROOT = Path(__file__).resolve().parents[1]
HIST_ROUTES = {'5001A':'41006433','5001B':'41006248','5003A':'41006409','5003B':'41006064'}
GIHEUNG = '228000682'
SINNON = '121000944'

# Verified against GBIS searchRouteJson on 2026-09-19, using config REALTIME_ROUTES.
# Route-specific stop IDs and orders; never copy opposite-direction IDs.
VERIFIED_DESTINATIONS = {'5001A': [{'id': 'destination:121000944',
            'name': '신논현역',
            'official_name': '신논현역.주류성빌딩',
            'historical_id': None,
            'realtime_id': '121000944',
            'seq': 43},
           {'id': 'destination:121000009',
            'name': '강남역',
            'official_name': '신분당선강남역(중)',
            'historical_id': None,
            'realtime_id': '121000009',
            'seq': 45},
           {'id': 'destination:121000007',
            'name': '래미안아파트.파이낸셜뉴스(중)',
            'official_name': '래미안아파트.파이낸셜뉴스(중)',
            'historical_id': None,
            'realtime_id': '121000007',
            'seq': 47},
           {'id': 'destination:121000005',
            'name': '뱅뱅사거리',
            'official_name': '뱅뱅사거리(중)',
            'historical_id': None,
            'realtime_id': '121000005',
            'seq': 48},
           {'id': 'destination:121000003',
            'name': '양재역',
            'official_name': '양재역.서초문화예술회관(중)',
            'historical_id': None,
            'realtime_id': '121000003',
            'seq': 49},
           {'id': 'destination:121000001',
            'name': '말죽거리공원사거리',
            'official_name': '말죽거리공원사거리(중)',
            'historical_id': None,
            'realtime_id': '121000001',
            'seq': 50},
           {'id': 'destination:121000220',
            'name': '매헌시민의숲.양재꽃시장',
            'official_name': '매헌시민의숲.양재꽃시장',
            'historical_id': None,
            'realtime_id': '121000220',
            'seq': 51}],
 '5003A': [{'id': 'destination:121000944',
            'name': '신논현역',
            'official_name': '신논현역.주류성빌딩',
            'historical_id': None,
            'realtime_id': '121000944',
            'seq': 55},
           {'id': 'destination:121000009',
            'name': '강남역',
            'official_name': '신분당선강남역(중)',
            'historical_id': None,
            'realtime_id': '121000009',
            'seq': 57},
           {'id': 'destination:121000007',
            'name': '래미안아파트.파이낸셜뉴스(중)',
            'official_name': '래미안아파트.파이낸셜뉴스(중)',
            'historical_id': None,
            'realtime_id': '121000007',
            'seq': 59},
           {'id': 'destination:121000005',
            'name': '뱅뱅사거리',
            'official_name': '뱅뱅사거리(중)',
            'historical_id': None,
            'realtime_id': '121000005',
            'seq': 60},
           {'id': 'destination:121000003',
            'name': '양재역',
            'official_name': '양재역.서초문화예술회관(중)',
            'historical_id': None,
            'realtime_id': '121000003',
            'seq': 61},
           {'id': 'destination:121000001',
            'name': '말죽거리공원사거리',
            'official_name': '말죽거리공원사거리(중)',
            'historical_id': None,
            'realtime_id': '121000001',
            'seq': 62},
           {'id': 'destination:121000220',
            'name': '매헌시민의숲.양재꽃시장',
            'official_name': '매헌시민의숲.양재꽃시장',
            'historical_id': None,
            'realtime_id': '121000220',
            'seq': 63}],
 '5001B': [{'id': 'destination:228000696',
            'name': '기흥역8번출구',
            'official_name': '기흥역8번출구',
            'historical_id': None,
            'realtime_id': '228000696',
            'seq': 62},
           {'id': 'destination:228000695',
            'name': '수원컨트리클럽',
            'official_name': '수원컨트리클럽',
            'historical_id': None,
            'realtime_id': '228000695',
            'seq': 63},
           {'id': 'destination:228000694',
            'name': '강남대역.강남대입구',
            'official_name': '강남대역.강남대입구',
            'historical_id': None,
            'realtime_id': '228000694',
            'seq': 64},
           {'id': 'destination:228000693',
            'name': '어정삼거리.강남마을',
            'official_name': '어정삼거리.강남마을',
            'historical_id': None,
            'realtime_id': '228000693',
            'seq': 65},
           {'id': 'destination:228001147',
            'name': '고인돌.하나로마트.현대출고장',
            'official_name': '고인돌.하나로마트.현대출고장',
            'historical_id': None,
            'realtime_id': '228001147',
            'seq': 66},
           {'id': 'destination:228000692',
            'name': '상지석.대우.진흥아파트',
            'official_name': '상지석.대우.진흥아파트',
            'historical_id': None,
            'realtime_id': '228000692',
            'seq': 67},
           {'id': 'destination:228000691',
            'name': '수원동.쌍용아파트',
            'official_name': '수원동.쌍용아파트',
            'historical_id': None,
            'realtime_id': '228000691',
            'seq': 68},
           {'id': 'destination:228000690',
            'name': '인정프린스.흥국생명연수원',
            'official_name': '인정프린스.흥국생명연수원',
            'historical_id': None,
            'realtime_id': '228000690',
            'seq': 69},
           {'id': 'destination:228000782',
            'name': '효자고개',
            'official_name': '효자고개',
            'historical_id': None,
            'realtime_id': '228000782',
            'seq': 70},
           {'id': 'destination:228000781',
            'name': '삼가역.두산위브',
            'official_name': '삼가역.두산위브',
            'historical_id': None,
            'realtime_id': '228000781',
            'seq': 71},
           {'id': 'destination:228000780',
            'name': '진우.늘푸른오스카빌.우남퍼스트빌아파트',
            'official_name': '진우.늘푸른오스카빌.우남퍼스트빌아파트',
            'historical_id': None,
            'realtime_id': '228000780',
            'seq': 72},
           {'id': 'destination:228000779',
            'name': '시청.용인대역',
            'official_name': '시청.용인대역',
            'historical_id': None,
            'realtime_id': '228000779',
            'seq': 73}],
 '5003B': [{'id': 'destination:228000696',
            'name': '기흥역8번출구',
            'official_name': '기흥역8번출구',
            'historical_id': None,
            'realtime_id': '228000696',
            'seq': 75},
           {'id': 'destination:228000695',
            'name': '수원컨트리클럽',
            'official_name': '수원컨트리클럽',
            'historical_id': None,
            'realtime_id': '228000695',
            'seq': 76},
           {'id': 'destination:228000694',
            'name': '강남대역.강남대입구',
            'official_name': '강남대역.강남대입구',
            'historical_id': None,
            'realtime_id': '228000694',
            'seq': 77},
           {'id': 'destination:228002136',
            'name': '지석역',
            'official_name': '지석역',
            'historical_id': None,
            'realtime_id': '228002136',
            'seq': 78},
           {'id': 'destination:228000146',
            'name': '갈천마을.주공아파트',
            'official_name': '갈천마을.주공아파트',
            'historical_id': None,
            'realtime_id': '228000146',
            'seq': 79},
           {'id': 'destination:228000145',
            'name': '어정풍림아파트.강남마을9단지',
            'official_name': '어정풍림아파트.강남마을9단지',
            'historical_id': None,
            'realtime_id': '228000145',
            'seq': 80},
           {'id': 'destination:228000144',
            'name': '어정역',
            'official_name': '어정역',
            'historical_id': None,
            'realtime_id': '228000144',
            'seq': 81},
           {'id': 'destination:228000158',
            'name': '동백이마트',
            'official_name': '동백이마트',
            'historical_id': None,
            'realtime_id': '228000158',
            'seq': 82},
           {'id': 'destination:228001721',
            'name': '호수마을.자연앤데시앙.두산위브더제니스',
            'official_name': '호수마을.자연앤데시앙.두산위브더제니스',
            'historical_id': None,
            'realtime_id': '228001721',
            'seq': 84},
           {'id': 'destination:228000154',
            'name': '동막초등학교.호수마을계룡리슈빌.어울림',
            'official_name': '동막초등학교.호수마을계룡리슈빌.어울림',
            'historical_id': None,
            'realtime_id': '228000154',
            'seq': 86},
           {'id': 'destination:228000153',
            'name': '동백중학교',
            'official_name': '동백중학교',
            'historical_id': None,
            'realtime_id': '228000153',
            'seq': 87},
           {'id': 'destination:228000167',
            'name': '동백고.호수마을서해그랑블.풍림코아루',
            'official_name': '동백고.호수마을서해그랑블.풍림코아루',
            'historical_id': None,
            'realtime_id': '228000167',
            'seq': 88}]}


def literal_config(root=ROOT):
    values = {}
    for node in ast.parse((Path(root)/'config.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name): values[target.id] = value
    return values


def canon(name):
    name = str(name or '').replace('컨트리크럽','컨트리클럽')
    for key in ['신논현','강남대','강남역','양재역','기흥역','뱅뱅','우성','교육개발원','매헌','말죽거리']:
        if key in name: return key
    return name.replace(' ', '').replace('(중)', '')


def catalog(root=ROOT):
    c = literal_config(root)
    seed = json.loads((Path(root)/'services/stations_dhs_gpt_commited.json').read_text(encoding='utf-8'))
    result = {}
    for route in HIST_ROUTES:
        family = route[:4]
        if route.endswith('A'):
            historical = seed[family]['yongin']
            realtime = c['REALTIME_STATIONS_'+route]
            rows = [dict(id=str(h[0]), name=h[1], historical_id=str(h[0]), realtime_id=str(r['id']), seq=h[2])
                    for h,r in zip(historical,realtime)]
            dest = [dict(id=str(h[0]),name=h[1],historical_id=str(h[0]),
                         realtime_id=SINNON if '신논현' in h[1] else None,seq=None)
                    for h in seed[family]['seoul']]
        else:
            history = {canon(h[1]):str(h[0]) for h in seed[family]['seoul']}
            rows = [dict(id=str(r['id']),name=r['name'],realtime_id=str(r['id']),
                         historical_id=history.get(canon(r['name'])),seq=None)
                    for r in c['REALTIME_STATIONS_B']]
            # Opposite-side stop IDs cannot be copied from A. Resolve by observed B data.
            dest = [dict(id='destination:'+str(h[0]),name=h[1],historical_id=None,realtime_id=None,seq=None)
                    for h in seed[family]['yongin']]
        dest = [dict(stop) for stop in VERIFIED_DESTINATIONS[route]]
        result[route] = dict(route=route,route_id=c['REALTIME_ROUTES'][route],
                             direction='to_seoul' if route.endswith('A') else 'to_yongin',
                             variant=route[-1],boarding=rows,destinations=dest)
    return result


def dt(value):
    if isinstance(value, datetime): return value
    text = str(value)
    return datetime.strptime(text[:8], '%Y%m%d') if len(text)==8 else datetime.fromisoformat(text)


def number(value):
    try:
        n=float(value)
        return n if math.isfinite(n) and n>=0 else None
    except (TypeError,ValueError): return None


def q75(values):
    values=sorted(values)
    if not values: return None
    pos=(len(values)-1)*.75; low=int(pos); high=min(low+1,len(values)-1)
    return values[low]+(values[high]-values[low])*(pos-low)


def holiday_kind(day):
    try:
        import holidays
        return 'holiday' if day.weekday()>=5 or day in holidays.country_holidays('KR',years=[day.year]) else 'weekday'
    except ImportError:
        return 'holiday' if day.weekday()>=5 else 'weekday'


def seasonal(month):
    return 'winter' if month in (12,1,2) else 'spring' if month in (3,4,5) else 'summer' if month in (6,7,8) else 'fall'


class DataStore:
    def __init__(self, root=ROOT):
        self.root=Path(root); self.catalog=catalog(root); self._rows={}; self._runs={}; self._profiles={}; self._trips={}; self._congestions={}; self._location_cache={}
        self.config=literal_config(root)
        self.workbooks=WorkbookData(root)

    def read(self, filename, table):
        key=(filename,table)
        if key in self._rows: return self._rows[key]
        path=self.root/'data'/filename
        if not path.is_file(): self._rows[key]=[]; return []
        try:
            with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as conn:
                conn.row_factory=sqlite3.Row
                rows=[dict(r) for r in conn.execute('SELECT * FROM "'+table+'"')]
        except sqlite3.Error: rows=[]
        self._rows[key]=rows
        return rows

    def health(self):
        return {name:dict(exists=(self.root/'data'/name).is_file()) for name in ['busflow.db','busflow_5003.db','realtime.db']}

    def locations(self,route):
        if route not in self._location_cache:
            self._location_cache[route]=[r for r in self.read('realtime.db','realtime_location') if r.get('route_name')==route]
        return self._location_cache[route]

    def resolve_destination(self,route,dest):
        # Only accept a destination present in our server-side catalog.
        matches=[s for s in self.catalog[route]['destinations'] if str(s['id'])==str(dest) or canon(s['name'])==canon(dest)]
        if not matches: return None
        s=dict(matches[0])
        if s.get('realtime_id'): return s
        ids=set()
        names=self.config.get('REALTIME_STATION_NAMES',{})
        for row in self.locations(route):
            rid=str(row.get('station_id',''))
            name=row.get('station_name') or names.get(rid,'')
            if name and canon(name)==canon(s['name']): ids.add(rid)
        if len(ids)==1: s['realtime_id']=ids.pop(); return s
        return None

    def runs(self,route):
        if route in self._runs: return self._runs[route]
        groups=defaultdict(list)
        for row in self.locations(route):
            try:
                t=dt(row['collected_at']); seq=int(row['station_seq']); vehicle=str(row['veh_id'])
            except (KeyError,ValueError,TypeError): continue
            if not vehicle or vehicle=='None': continue
            groups[vehicle].append(dict(time=t,seq=seq,id=str(row['station_id']),seats=number(row.get('remain_seat_cnt'))))
        runs=[]
        for vehicle, points in groups.items():
            current=[]; prev=None
            for point in sorted(points,key=lambda r:r['time']):
                if prev and (point['time'].date()!=prev['time'].date() or point['seq']<prev['seq'] or (point['time']-prev['time']).total_seconds()>7200):
                    if current: runs.append(current)
                    current=[]
                if current and current[-1]['id']==point['id']:
                    current[-1]['last']=point['time']
                else: current.append(dict(point,last=point['time'],vehicle=vehicle))
                prev=point
            if current: runs.append(current)
        self._runs[route]=runs
        return runs

    @staticmethod
    def comparable(samples,target,time_key='time'):
        past=[s for s in samples if s[time_key].date()<target.date() and s[time_key].hour==target.hour]
        same_kind=[s for s in past if holiday_kind(s[time_key].date())==holiday_kind(target.date())]
        exact=[s for s in same_kind if s[time_key].weekday()==target.weekday()]
        season=[s for s in exact if seasonal(s[time_key].month)==seasonal(target.month)]
        for rows,label in [(season,'동일 계절·요일·시간'),(exact,'동일 요일·시간'),(same_kind,'동일 평일/휴일·시간')]:
            if rows: return rows,label
        return [],'해당 시간대 기록 없음'

    def segment_samples(self,route,start,end):
        key=(route,start,end)
        if key in self._trips: return self._trips[key]
        samples=[]
        for run in self.runs(route):
            starts=[i for i,p in enumerate(run) if p['id']==start]
            ends=[i for i,p in enumerate(run) if p['id']==end]
            if len(starts)!=1 or len(ends)!=1 or starts[0]>=ends[0]: continue
            a,b=starts[0],ends[0]
            begin=run[a]['last']; finish=run[b]['time']; total=(finish-begin).total_seconds()/60
            if not 0<total<=180: continue
            pre=total; core=0.; after=0.; scope=False; core_hour=None
            if route.endswith('A'):
                gi=next((i for i,p in enumerate(run) if p['id']==GIHEUNG),None)
                si=next((i for i,p in enumerate(run) if p['id']==SINNON),None)
                if gi is not None and si is not None and gi<si:
                    lo=max(a,gi); hi=min(b,si)
                    if lo<hi:
                        # Additive partition; no second insertion of the highway's full time.
                        left=begin if lo==a else run[lo]['time']
                        right=finish if hi==b else run[hi]['time']
                        pre=(left-begin).total_seconds()/60
                        core=(right-left).total_seconds()/60
                        after=total-pre-core
                        core_hour=(left-begin).total_seconds()/60
                        scope=core>0
            samples.append(dict(time=begin,total=total,pre=pre,core=core,after=after,scope=scope,core_offset=core_hour or 0))
        self._trips[key]=samples
        return samples

    def travel(self,route,start,end,target):
        samples,label=self.comparable(self.segment_samples(route,start,end),target)
        if samples:
            # Use one observed trip at the p75 rank to preserve additive segment partition.
            chosen=sorted(samples,key=lambda x:x['total'])[math.ceil((len(samples)-1)*.75)]
            return {**chosen,'sample_count':len(samples),'basis':label,'source':'observed_vehicle_trips'}
        # Legacy statistics are valid only for their explicitly defined core segment.
        if route.endswith('A') and start==GIHEUNG and end==SINNON:
            for r in self.read('realtime.db','travel_time_stats'):
                # Old stats used an incorrect Sinnonhyeon ID (Anter entrance).
                # Only use legacy stats with explicit, verified segment endpoints.
                if str(r.get('start_station_id')) != start or str(r.get('end_station_id')) != end: continue
                if r.get('route_name')!=route or int(r.get('departure_hour',-1))!=target.hour: continue
                try:
                    if dt(r['updated_at']).date()>=target.date(): continue
                except (KeyError,ValueError,TypeError): continue
                total=number(r.get('p75_minutes')); count=number(r.get('sample_count'))
                if total is not None and total>0 and count:
                    return dict(total=total,pre=0.,core=total,after=0.,scope=True,core_offset=0,
                                sample_count=int(count),basis='기존 노선·시간대 p75 (요일 미분리)',source='legacy_core_stats')
        return None

    def profile(self,route,station,target):
        key=(route,station,target.date(),target.hour)
        if key in self._profiles: return self._profiles[key]
        # First prefer observed station passages; otherwise deduplicate arrival predictions.
        passages=[]
        for run in self.runs(route):
            for p in run:
                if p['id']==station:
                    passages.append(dict(time=p['time'],vehicle=p['vehicle'],seats=p['seats'],estimated=False))
        if not passages:
            groups=defaultdict(list)
            for table in ['realtime_arrival_a','realtime_arrival_b','realtime_arrival']:
                for r in self.read('realtime.db',table):
                    if r.get('route_name')!=route or str(r.get('station_id'))!=station: continue
                    try: collected=dt(r['collected_at'])
                    except (KeyError,ValueError,TypeError): continue
                    if collected.date()>=target.date(): continue
                    for n in [1,2]:
                        vid=r.get(f'veh_id_{n}'); eta=number(r.get(f'predict_time_sec_{n}')); seats=number(r.get(f'remain_seat_cnt_{n}'))
                        if vid and eta is not None and eta<=7200:
                            groups[(collected.date(),str(vid))].append((collected,eta,seats))
            for (_,vehicle), rows in groups.items():
                episodes=[]; current=[]; prev=None
                for row in sorted(set(rows),key=lambda p:p[0]):
                    arrival=row[0]+timedelta(seconds=row[1])
                    if prev and (row[0]-prev[0]>timedelta(minutes=20) or abs((arrival-(prev[0]+timedelta(seconds=prev[1]))).total_seconds())>1800):
                        episodes.append(current); current=[]
                    current.append(row); prev=row
                if current: episodes.append(current)
                for episode in episodes:
                    closest=min(episode,key=lambda p:p[1])
                    passages.append(dict(time=closest[0]+timedelta(seconds=closest[1]),vehicle=vehicle,seats=closest[2],estimated=True))
        selected,label=self.comparable(passages,target)
        by_day=defaultdict(list)
        for p in selected: by_day[p['time'].date()].append(p)
        intervals=[]
        for day,rows in by_day.items():
            rows=sorted(rows,key=lambda p:p['time'])
            for a,b in zip(rows,rows[1:]):
                gap=(b['time']-a['time']).total_seconds()/60
                if a['vehicle']!=b['vehicle'] and 1<=gap<=120: intervals.append(gap)
        seats=[p['seats'] for p in selected if p['seats'] is not None]
        result=None
        if intervals and seats:
            result=dict(headway_minutes=median(intervals),headway_p75=q75(intervals),seat_median=median(seats),
                        full_rate=sum(s==0 for s in seats)/len(seats),seat_samples=len(seats),
                        headway_samples=len(intervals),days=len(by_day),basis=label,
                        source='historical_arrival_estimates' if any(p['estimated'] for p in selected) else 'historical_station_passages')
        if result is None:
            stop=next((s for s in self.catalog[route]['boarding'] if s['realtime_id']==station),None)
            if stop: result=self.workbooks.headway(route,stop['name'],target,canon)
        self._profiles[key]=result
        return result

    def congestion(self,route,historical_id,target):
        if not historical_id: return None
        key=(route,historical_id,target.date(),target.hour)
        if key in self._congestions: return self._congestions[key]
        file='busflow_5003.db' if route.startswith('5003') else 'busflow.db'
        samples=[]
        for r in self.read(file,'congestion'):
            if str(r.get('route_id'))!=HIST_ROUTES[route] or str(r.get('station_id'))!=str(historical_id): continue
            try:
                hour=int(str(r['time_zone'])[:2]); t=dt(r['opr_ymd'])+timedelta(hours=hour)
            except (ValueError,TypeError,KeyError): continue
            n=number(r.get('congestion'))
            if n is not None: samples.append(dict(time=t,value=n))
        rows,label=self.comparable(samples,target)
        result=dict(value=round(sum(r['value'] for r in rows)/len(rows),1),sample_count=len(rows),basis=label,source='data/'+file+' / congestion') if rows else None
        if result is None: result=self.workbooks.congestion(route,historical_id,target,self.comparable)
        self._congestions[key]=result
        return result
