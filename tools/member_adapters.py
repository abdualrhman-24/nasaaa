"""Adapters for the unmodified Person 1 and Person 2 REST contracts."""
import os
from datetime import datetime, timezone
import httpx
from schemas.models import Site, Visibility, Route, Provenance

def mapped_status(value: str) -> str:
    # REAL is a supplier claim. Person 4 cannot independently verify it.
    return 'MOCK' if value=='MOCK' else 'UNVERIFIED'

def observed(value: str | None) -> datetime:
    if not value: raise ValueError('Upstream measurement lacks generation timestamp')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None: raise ValueError('Upstream timestamp lacks timezone')
    return result.astimezone(timezone.utc)

class Member1LandingSiteService:
    def __init__(self,url: str):
        self.url=url.rstrip('/'); self.timeout=float(os.getenv('LUNA_HTTP_TIMEOUT_SECONDS','10'))

    async def candidates(self, req, mission_id: str) -> list[Site]:
        payload={'mission_id':mission_id,'mission_type':req.mission_type,
            'target_region':{'body':'Moon','coordinate_reference':'MEAN_EARTH_POLAR_AXIS','projection':'EQUIRECTANGULAR',
              'bounds':{'min_latitude_deg':float(os.getenv('LUNA_REGION_MIN_LAT','-90')),
                        'max_latitude_deg':float(os.getenv('LUNA_REGION_MAX_LAT','-75')),
                        'min_longitude_deg':float(os.getenv('LUNA_REGION_MIN_LON','-180')),
                        'max_longitude_deg':float(os.getenv('LUNA_REGION_MAX_LON','180'))}},
            'constraints':{'max_slope_deg':max(0.001,req.constraints.get('max_slope_deg',15)),
                           'max_roughness_m':float(os.getenv('LUNA_MAX_ROUGHNESS_M','1000000'))},
            'candidate_count':int(os.getenv('LUNA_CANDIDATE_COUNT','9')),
            'data_mode':os.getenv('LUNA_MEMBER1_DATA_MODE','auto'),
            'start_utc':req.dates_utc[0].isoformat().replace('+00:00','Z'),
            'duration_days':req.duration_hours/24}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response=await client.post(self.url+'/api/v1/landing-sites/candidates',json=payload)
            response.raise_for_status(); data=response.json()
        if data.get('coordinate_reference')!='MEAN_EARTH_POLAR_AXIS': raise ValueError('Member 1 frame mismatch')
        units=data.get('units',{})
        if units.get('coordinates')!='degrees' or units.get('elevation')!='m' or units.get('slope')!='degrees': raise ValueError('Member 1 units mismatch')
        timestamp=observed(data.get('generated_at_utc'))
        sites=[]
        for item in data['candidates']:
            if item['coordinates']['reference_frame']!='MEAN_EARTH_POLAR_AXIS': raise ValueError('Member 1 site frame mismatch')
            status=mapped_status(item['data_status'])
            source=f"Member 1: {item['source']} ({item['data_status']})"
            provenance=Provenance(status=status,source=source,observed_at_utc=timestamp,
                uncertainty='Terrain screening only; elevation relative to supplier product datum')
            c=item['coordinates']; t=item['terrain']
            sites.append(Site(site_id=item['site_id'],name=item['site_id'],latitude_deg=c['latitude_deg'],
                longitude_deg=c['longitude_deg']%360,elevation_m=t['elevation_m'],slope_deg=t['slope_deg'],provenance=provenance))
        return sites

class Member2VisibilityService:
    def __init__(self,url: str):
        self.url=url.rstrip('/'); self.timeout=float(os.getenv('LUNA_VISIBILITY_TIMEOUT_SECONDS','30'))

    async def analyze(self, site: Site, date_utc: datetime, duration_hours: float) -> Visibility:
        payload={'site':{'site_id':site.site_id,'lat_deg':site.latitude_deg,
                         'lon_deg_east':site.longitude_deg if site.longitude_deg<=180 else site.longitude_deg-360},
                 'start_utc':date_utc.isoformat().replace('+00:00','Z'),'duration_days':duration_hours/24,
                 'include_time_series':False,'horizon_profile_id':os.getenv('LUNA_MEMBER2_HORIZON','lola')}
        if os.getenv('LUNA_MEMBER2_ENGINE'): payload['engine']=os.environ['LUNA_MEMBER2_ENGINE']  # e.g. 'horizons': 60 s x 3 tries instead of auto's one 15 s try
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response=await client.post(self.url+'/api/v1/visibility/analyze',json=payload)
            response.raise_for_status(); data=response.json()
        if data.get('body_frame')!='MOON_ME': raise ValueError('Member 2 frame mismatch')
        if data.get('site_id')!=site.site_id or observed(data.get('start_utc'))!=date_utc: raise ValueError('Member 2 site/date mismatch')
        location=data.get('location',{})
        if abs(location.get('lat_deg',999)-site.latitude_deg)>1e-6 or abs(((location.get('lon_deg_east',999)-site.longitude_deg+180)%360)-180)>1e-6:
            raise ValueError('Member 2 coordinates mismatch')
        end=observed(data.get('end_utc'))
        if abs((end-date_utc).total_seconds()-duration_hours*3600)>1: raise ValueError('Member 2 duration mismatch')
        status=data['data_status']; horizon=data.get('horizon',{})
        if horizon.get('data_status')=='MOCK': status='MOCK'
        summary=data['summary']; sun=summary.get('sun_visible_fraction_terrain'); earth=summary.get('earth_visible_fraction_terrain')
        blackout=summary.get('longest_no_contact_hours_terrain')
        if sun is None or earth is None or blackout is None: raise ValueError('Member 2 terrain visibility metrics missing')
        provenance=Provenance(status=mapped_status(status),source=f"Member 2: {data['source']} ({status})",
            observed_at_utc=observed(data.get('generated_utc')),
            uncertainty='Supplier status retained in source; REAL requires independent verification')
        return Visibility(site_id=site.site_id,date_utc=date_utc,sunlight_hours=sun*duration_hours,
                          earth_visible_hours=earth*duration_hours,max_blackout_hours=blackout,provenance=provenance)

    async def sky(self, lat_deg: float, lon_deg: float, start_utc: datetime, duration_hours: float,
                  step_minutes: float = 60, observer_height_m: float = 2.0) -> dict:
        """Hour-by-hour Sun/Earth azimuth+elevation (NASA/JPL Horizons via Person 2) plus the LOLA terrain
        horizon profile at the same site, for the 'Sky and horizon' chart. Values are passed through unchanged."""
        import asyncio
        lon=lon_deg if lon_deg<=180 else lon_deg-360
        payload={'site':{'site_id':'sky','lat_deg':lat_deg,'lon_deg_east':lon},'start_utc':start_utc.isoformat().replace('+00:00','Z'),
                 'duration_days':duration_hours/24,'step_minutes':step_minutes,'include_time_series':True,
                 'horizon_profile_id':'lola','observer_height_m':observer_height_m}
        if os.getenv('LUNA_MEMBER2_ENGINE'): payload['engine']=os.environ['LUNA_MEMBER2_ENGINE']
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            vis,hor=await asyncio.gather(client.post(self.url+'/api/v1/visibility/analyze',json=payload),
                client.get(self.url+'/api/v1/visibility/horizon-profiles/lola',params={'site_id':'sky','lat':lat_deg,'lon':lon,'observer_height_m':observer_height_m}))
            vis.raise_for_status(); hor.raise_for_status(); v=vis.json(); h=hor.json()
        if v.get('body_frame')!='MOON_ME': raise ValueError('Member 2 frame mismatch')
        status=v['data_status'] if h.get('data_status')!='MOCK' else 'MOCK'
        keys=('utc','sun_az_deg','sun_el_deg','earth_az_deg','earth_el_deg','sun_visible_terrain','earth_visible_terrain','sun_horizon_el_deg','earth_horizon_el_deg')
        return {'site':{'latitude_deg':lat_deg,'longitude_deg':lon},'start_utc':v['start_utc'],'end_utc':v['end_utc'],'step_minutes':step_minutes,
                'observer_height_m':observer_height_m,
                'horizon':{'azimuth_deg':h['azimuth_deg'],'elevation_deg':h['elevation_deg'],'source':h['source'],'data_status':h['data_status'],
                           'details':(v.get('horizon') or {}).get('details')},
                'series':[{k:p.get(k) for k in keys} for p in v['time_series']],
                'summary':v['summary'],'windows':[w for w in v['windows'] if w.get('kind')=='terrain'],
                'conventions':{'azimuth':'degrees clockwise from local north, 0..360','elevation':'degrees above the local horizontal plane',
                               'visibility_definition':v.get('visibility_definition')},
                'provenance':{'status':mapped_status(status),'supplier_status':status,'source':f"Member 2: {v['source']}",
                              'ephemeris':v.get('data_source'),'observed_at_utc':v.get('generated_utc')}}

class Member3NavigationService:
    """Contract adapter only; supplied archive is truncated before server source."""
    def __init__(self,url: str):
        self.url=url.rstrip('/'); self.timeout=float(os.getenv('LUNA_NAVIGATION_TIMEOUT_SECONDS','20'))
        self._cache: dict = {}   # one plan = one service object: the same route serves every landing day of a site

    async def route(self,site: Site,max_slope_deg: float) -> Route:
        lat=os.getenv('LUNA_NAV_TARGET_LAT'); lon=os.getenv('LUNA_NAV_TARGET_LON')
        if lat is None or lon is None: raise ValueError('Set LUNA_NAV_TARGET_LAT and LUNA_NAV_TARGET_LON for required navigation')
        key=(self.url,site.site_id,site.latitude_deg,site.longitude_deg,lat,lon,max_slope_deg)
        if key in self._cache: return self._cache[key]
        base=self.url if self.url.endswith('/api/v1') else self.url+'/api/v1'
        payload={'start':{'lat_deg':site.latitude_deg,'lon_deg':site.longitude_deg if site.longitude_deg<=180 else site.longitude_deg-360},
                 'target':{'lat_deg':float(lat),'lon_deg':float(lon)},
                 'constraints':{'max_slope_deg':min(45,max_slope_deg)},
                 'algorithm':'astar','strategies':['shortest','balanced','gentle']}
        target_text=f"traverse target ({float(lat):.3f}, {float(lon):.2f}) from LUNA_NAV_TARGET_LAT/LON, an editable assumption"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response=await client.post(base+'/routes',json=payload)
            if response.status_code==422:
                # Person 3 answered, but found no route within the slope limit, or a point is off its terrain.
                # Record the site as not reachable (it is then rejected as 'route inaccessible'); never invent a route.
                err=(response.json().get('error') or {}) if response.headers.get('content-type','').startswith('application/json') else {}
                code=err.get('code','HTTP_422')
                provenance=Provenance(status='UNVERIFIED',source=f"Member 3: {code}: {err.get('message','')} ; {target_text}",
                    observed_at_utc=datetime.now(timezone.utc),uncertainty='No route returned; distance is not measured')
                result=Route(site_id=site.site_id,distance_m=0,accessible=False,provenance=provenance)
                self._cache[key]=result; return result
            response.raise_for_status(); data=response.json()
        if data.get('frame')!='IAU_MOON_ME': raise ValueError('Member 3 route frame mismatch')
        start=data.get('start',{})
        if abs(start.get('lat_deg',999)-site.latitude_deg)>1e-5 or abs(((start.get('lon_deg',999)-site.longitude_deg+180)%360)-180)>1e-5:
            raise ValueError('Member 3 route start mismatch')
        if not data.get('alternatives'): raise ValueError('Member 3 returned no route alternatives')
        shortest=next((x for x in data['alternatives'] if x.get('strategy')=='shortest'),data['alternatives'][0])
        status=mapped_status(data['data_status'])
        terrain=data.get('terrain_source',{})
        provenance=Provenance(status=status,source=f"Member 3: {terrain.get('name','route service')} ({data['data_status']}); operational_validity={data.get('operational_validity','UNKNOWN')}; {target_text}",
            observed_at_utc=observed(data.get('generated_at_utc')),
            uncertainty='Slope-only route; operational validity not validated')
        result=Route(site_id=site.site_id,distance_m=shortest['distance_m'],accessible=True,provenance=provenance)
        self._cache[key]=result; return result
