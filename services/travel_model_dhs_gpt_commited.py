"""Explicit uncalibrated travel estimates, separate from observed trip records."""
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import median

@lru_cache(maxsize=4)
def highway_hours(path,mtime,start,end,min_points):
    groups=defaultdict(lambda:defaultdict(list))
    with open(path,encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['route_no']!='0010' or row['direction']!='E': continue
            try: speed=float(row['avg_speed']); km=float(row['km']);hour=int(row['hour']);day=datetime.fromisoformat(row['date'])
            except (ValueError,KeyError): continue
            if math.isfinite(speed) and 0<speed<=150 and start<=km<=end and 0<=hour<24:
                groups[day.replace(hour=hour)][km].append(speed)
    result=[]
    for time,locations in groups.items():
        xs=sorted(locations)
        if len(xs)<min_points or xs[0]>start+1.5 or xs[-1]<end-1.5: continue
        # Duplicate detectors at one kilometre count as one location. Integrate
        # reciprocal speed in space; do not average speeds then divide distance.
        speeds={x:median(locations[x]) for x in xs}
        minutes=(xs[0]-start)/speeds[xs[0]]*60+(end-xs[-1])/speeds[xs[-1]]*60
        minutes+=sum((b-a)*30*(1/speeds[a]+1/speeds[b]) for a,b in zip(xs,xs[1:]))
        result.append(dict(time=time,minutes=minutes,locations=len(xs)))
    return tuple(result)

class TravelModel:
    def __init__(self,root):
        self.root=Path(root);p=self.root/'services/travel_assumptions_dhs_gpt_commited.json'
        self.config=json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}
        self.enabled=self.config.get('enabled',False)
        self._highways={}
        if self.enabled:
            for key in ('local_adjacent_distance_km','local_speed_kmh','seoul_speed_kmh','stop_dwell_minutes','access_road_distance_km','northbound_fallback_speed_kmh','southbound_assumed_speed_kmh'):
                if not isinstance(self.config[key],(int,float)) or not math.isfinite(self.config[key]) or self.config[key]<=0: raise ValueError('이동시간 가정값은 양수여야 합니다.')

    def highway(self,target,comparable):
        key=(target.date(),target.hour)
        if key in self._highways:return self._highways[key]
        c=self.config;p=self.root/'data/highway_speed.csv';selected=[];basis=''
        if p.is_file():
            rows=highway_hours(str(p.resolve()),p.stat().st_mtime_ns,c['highway_start_km'],c['highway_end_km'],c['minimum_vds_locations'])
            selected,basis=comparable(rows,target)
        if selected:
            # Empirical p75 of hour-level road travel proxies, not bus trip p75.
            chosen=sorted(selected,key=lambda r:r['minutes'])[math.ceil((len(selected)-1)*.75)]
            result=(chosen['minutes'],dict(source='data/highway_speed.csv',basis=basis+' VDS 도로시간 p75',sample_count=len(selected),direction='E',speed_kmh=(c['highway_end_km']-c['highway_start_km'])*60/chosen['minutes']))
        else:
            speed=c['northbound_fallback_speed_kmh']
            result=((c['highway_end_km']-c['highway_start_km'])*60/speed,dict(source='assumed_speed',basis='해당 시간대 VDS 표본 없음 · 속도 가정',sample_count=0,direction='E',speed_kmh=speed))
        self._highways[key]=result;return result

    def estimate(self,route,station,dest,target,catalog,comparable,local_sections=()):
        if not self.enabled:return None
        c=self.config;family=route[:4];north=route.endswith('A');spec=catalog[route]
        if not any(s['id']==station['id'] for s in spec['boarding']) or not any(s['id']==dest['id'] for s in spec['destinations']):return None
        notes=[c['note']];dwell=c['stop_dwell_minutes'];local=c['local_adjacent_distance_km']*60/c['local_speed_kmh']+dwell
        access=c['access_road_distance_km']*60/c['local_speed_kmh']
        offsets=c['seoul_stop_offset_km'];seoul=list(offsets)
        if north:
            idx=next(i for i,s in enumerate(spec['boarding']) if s['id']==station['id'])
            pre=(len(spec['boarding'])-1-idx)*local
            destidx=seoul.index(dest['name'])
            highway,road=self.highway(target+timedelta(minutes=pre),comparable)
            city=offsets[dest['name']]*60/c['seoul_speed_kmh']+(destidx+1)*dwell
            core=access+highway+city;after=0
            distance=(len(spec['boarding'])-1-idx)*c['local_adjacent_distance_km']+c['access_road_distance_km']+c['highway_end_km']-c['highway_start_km']+offsets[dest['name']]
            notes.append('출근 고속도로는 '+road['basis']+' 사용. 고속도로 진입·진출 및 서울 시내 구간은 가정값입니다.')
            if road['sample_count']:notes.append('VDS 자료에서 비 오는 날을 분리하지 못했으므로 날씨 가중치와 강수 영향이 중복될 수 있습니다.')
        else:
            idx=next(i for i,s in enumerate(spec['boarding']) if s['id']==station['id'])
            # B names differ from A. Existing B order has six stops up to Sinnon.
            b_offsets=[offsets['말죽거리공원사거리'],offsets['양재역'],offsets['뱅뱅사거리'],offsets['우성아파트'],offsets['강남역'],offsets['신논현역']]
            city_km=offsets['신논현역']-b_offsets[idx]+offsets['신논현역']
            city_stops=len(spec['boarding'])-1-idx
            city=city_km*60/c['seoul_speed_kmh']+city_stops*dwell
            section_lookup={r['section']:r for r in local_sections}
            for j in range(idx,len(spec['boarding'])-1):
                section=spec['boarding'][j]['name']+' → '+spec['boarding'][j+1]['name']
                record=section_lookup.get(section)
                if record:
                    assumed=(b_offsets[j+1]-b_offsets[j])*60/c['seoul_speed_kmh']+dwell
                    city+=record['mean_minutes']-assumed
                    notes.append(f'{section}: 기존 서울 구간 기록 평균 {record["mean_minutes"]}분 ({record["samples"]}건, 동일 시간·요일 미분리) 사용.')
            destidx=next(i for i,s in enumerate(spec['destinations']) if s['id']==dest['id'])
            local_count=len(spec['destinations'])-1-destidx
            highway=(c['highway_end_km']-c['highway_start_km'])*60/c['southbound_assumed_speed_kmh']
            pre=city+highway+access+local_count*local;core=0;after=0
            distance=city_km+c['highway_end_km']-c['highway_start_km']+c['access_road_distance_km']+local_count*c['local_adjacent_distance_km']
            road=dict(source='southbound_assumption',basis='퇴근 방향 별도 속도 가정',sample_count=0,direction='S_assumed',speed_kmh=c['southbound_assumed_speed_kmh'])
            notes.extend(['퇴근은 서울 방향 CSV를 재사용하지 않고 별도 속도를 가정했습니다.',c['reverse_yongin_geometry'],c['reverse_seoul_geometry']])
        total=pre+core+after
        notes.append(f'시내 인접 정류장 거리 {c["local_adjacent_distance_km"]}km, 시내 속도 {c["local_speed_kmh"]}km/h·서울 {c["seoul_speed_kmh"]}km/h, 정차 {dwell}분/회 가정.')
        return dict(total=total,pre=pre,core=core,after=after,scope=north,core_offset=pre,
                    source='distance_speed_model',estimated=True,sample_count=0,basis='거리·속도·정차시간 가정 모델',
                    highway_evidence=road,assumed_distance_km=round(distance,2),notes=notes,
                    scenario_factors=[c['scenario_low_factor'],c['scenario_high_factor']])
