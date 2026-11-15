import os, traceback
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from schemas.models import Requirements, ReplanRequest, CompareRequest, CompareResponse
from orchestration.engine import plan

app=FastAPI(title='LUNA NAV Person 4 Mission Optimizer',version='1.0.0')
ORIGINS=[x.strip() for x in os.getenv('LUNA_CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=ORIGINS,
                   allow_methods=['GET','POST'],allow_headers=['Content-Type'])

@app.exception_handler(Exception)
async def failure(request, exc):
    # This handler runs outside the CORS middleware, so add the CORS header here; without it the
    # browser hides the real error and the interface reports the planner as unreachable.
    origin=request.headers.get('origin'); headers={'Access-Control-Allow-Origin':origin,'Vary':'Origin'} if origin in ORIGINS else {}
    if isinstance(exc, HTTPException): return JSONResponse(status_code=exc.status_code,content={'error':{'code':'HTTP_ERROR','message':str(exc.detail)}},headers=headers)
    traceback.print_exception(exc)
    return JSONResponse(status_code=502,content={'error':{'code':'UPSTREAM_OR_PLANNING_ERROR','message':f'{type(exc).__name__}: {exc}'}},headers=headers)

@app.get('/health')
async def health(): return {'status':'ok','mode':'standalone'}

@app.post('/mission/plan')
async def create_plan(req: Requirements): return await plan(req)

@app.post('/mission/replan')
async def replan(req: ReplanRequest): return await plan(req.requirements,req.previous)

class SkyRequest(BaseModel):
    latitude_deg: float = Field(ge=-90, le=-75)
    longitude_deg: float = Field(ge=-180, le=360)
    start_utc: datetime
    duration_hours: float = Field(gt=0, le=720)
    step_minutes: float = Field(60, ge=5, le=240)

@app.post('/mission/sky')
async def sky(req: SkyRequest):
    """Sun and Earth azimuth/elevation hour by hour (NASA/JPL Horizons, via Person 2) and the LOLA terrain horizon
    profile for one site and stay window. Needs the real visibility service; never returns invented values."""
    url=os.getenv('LUNA_VISIBILITY_URL')
    if not url:
        raise HTTPException(503,'Sky view needs the visibility service (Person 2). Start the backend with scripts/start_real_nasa.ps1; '
                                'mock mode has no Sun/Earth positions to show.')
    if req.start_utc.tzinfo is None: raise HTTPException(422,'start_utc must include a timezone (Z)')
    from tools.member_adapters import Member2VisibilityService
    return await Member2VisibilityService(url).sky(req.latitude_deg,req.longitude_deg,req.start_utc.astimezone(timezone.utc),req.duration_hours,req.step_minutes)

@app.post('/mission/compare',response_model=CompareResponse)
async def compare(req: CompareRequest):
    baseline=await plan(req.requirements,baseline=True)
    hybrid=await plan(req.requirements)
    return CompareResponse(baseline=baseline,hybrid=hybrid,metrics={'baseline':baseline.metrics,'hybrid':hybrid.metrics})
