# Start the whole team stack on NASA data for an accuracy test.
#   Person 1: NASA LOLA LDEM_75S_240M (polar, 240 m), candidates on local high ground near the pole,
#             region 90 S to 87.5 S. Use -Person1Dem cylindrical for the original LDEM_16 grid pattern.
#   Person 2: live NASA/JPL Horizons + horizon computed from NASA LOLA LDEM_75S_240M
#   Person 4: accepts supplier REAL data (shown as UNVERIFIED) with a warning, for testing only
# Prerequisites (once):
#   .venv\Scripts\python.exe -m pip install spiceypy truststore
#   .venv\Scripts\python.exe scripts\get_nasa_lola.py
#   (optional) .venv\Scripts\python.exe scripts\get_nasa_lola.py --product ldem_16
# Optional Gemini (language only, never measurements):
#   $env:GEMINI_API_KEY = '<key from Google AI Studio>'   then run this script
#   -GeminiModel <name> to change the model, -GeminiLang ar for an Arabic summary
# Terrain source (Person 1, Person 2 and the Person 3 route grid):
#   -Terrain pds       NASA PDS LDEM_75S_240M (default, unchanged behaviour)
#   -Terrain moontrek  the same LOLA data exported from NASA Moon Trek (scripts\get_moontrek_lola.py, then
#                      scripts\build_lola_terrain.py --source moontrek for the route grid)
# Person 3 routes (traverse access in the ranking) start when original_modules\person3\moon_navigation\node_modules
# exists (pnpm install). The traverse target is an editable assumption: -NavTargetLat/-NavTargetLon, default the
# south pole point on the rim of Shackleton (-89.97, 0), at the edge of its permanently shadowed floor. Every
# Person 1 candidate reaches it within 15 deg on LOLA, and none sits on it (tested 2026-11-15).
param([int]$Port = 8000, [ValidateSet('polar', 'cylindrical')][string]$Person1Dem = 'polar',
      [string]$GeminiModel = '', [ValidateSet('en', 'ar')][string]$GeminiLang = 'en',
      [ValidateSet('pds', 'moontrek')][string]$Terrain = 'pds',
      [double]$NavTargetLat = -89.97, [double]$NavTargetLon = 0)
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$lolaDir = Join-Path $root 'original_modules\person2\member2\data\lola'
if ($Terrain -eq 'moontrek') {
  $lola = Join-Path $lolaDir 'moontrek_ldem_75s_240m.img'
  if (-not (Test-Path -LiteralPath $lola)) { throw 'Missing the Moon Trek grid. Run: .venv\Scripts\python.exe scripts\get_moontrek_lola.py' }
  $env:LUNA_LOLA_PRODUCT = 'moontrek_ldem_75s_240m'
  $grid = Join-Path $root 'frontend\data\lola_south_pole_moontrek.json'
  if (-not (Test-Path -LiteralPath $grid)) { Write-Warning 'frontend\data\lola_south_pole_moontrek.json missing (build_lola_terrain.py --source moontrek); Person 3 routes use the PDS grid.'; $grid = Join-Path $root 'frontend\data\lola_south_pole.json' }
} else {
  $lola = Join-Path $lolaDir 'ldem_75s_240m.img'
  if (-not (Test-Path -LiteralPath $lola)) { throw 'Missing LDEM_75S_240M. Run: .venv\Scripts\python.exe scripts\get_nasa_lola.py' }
  Remove-Item Env:LUNA_LOLA_PRODUCT -ErrorAction SilentlyContinue
  $grid = Join-Path $root 'frontend\data\lola_south_pole.json'
}
if (Test-Path -LiteralPath $grid) { $env:LUNA_TERRAIN_GRID_JSON = $grid }   # Person 3 routes on real LOLA terrain
$env:LUNA_NAV_TARGET_LAT = "$NavTargetLat"; $env:LUNA_NAV_TARGET_LON = "$NavTargetLon"
Write-Host "Terrain: $Terrain ($([IO.Path]::GetFileName($lola))). Route target (assumption): $NavTargetLat, $NavTargetLon"
if ($Person1Dem -eq 'polar') {
  $dem = $lola
  $env:LUNA_P1_CANDIDATE_STRATEGY = 'elevated'
} else {
  $dem = Join-Path $root 'original_modules\person1\data\ldem_16.img'
  if (-not (Test-Path -LiteralPath $dem)) { throw 'Missing LDEM_16. Run: .venv\Scripts\python.exe scripts\get_nasa_lola.py --product ldem_16' }
  $env:LUNA_P1_CANDIDATE_STRATEGY = 'grid'
}
$env:LUNA_DEM_PATH = $dem
$env:LUNA_DEM_LABEL_PATH = [IO.Path]::ChangeExtension($dem, '.lbl')
$env:LUNA_MEMBER1_DATA_MODE = 'real'
$env:LUNA_REGION_MIN_LAT = '-90'; $env:LUNA_REGION_MAX_LAT = '-87.5'
$env:LUNA_REGION_MIN_LON = '-180'; $env:LUNA_REGION_MAX_LON = '180'
$env:LUNA_CANDIDATE_COUNT = '6'
$env:LUNA_MEMBER2_HORIZON = 'lola'
# Live Horizons with Person 2's own retries (60 s x 3). 'auto' tries Horizons once for 15 s, then needs SPICE kernels,
# which are not installed by default, so a slow Horizons answer used to fail the whole plan.
$env:LUNA_MEMBER2_ENGINE = 'horizons'
$env:LUNA_HTTP_TIMEOUT_SECONDS = '60'
$env:LUNA_VISIBILITY_TIMEOUT_SECONDS = '300'
$env:LUNA_ALLOW_UNVERIFIED_RECOMMENDATION = '1'
Write-Host "NASA data mode: Person 1 $Person1Dem DEM ($env:LUNA_P1_CANDIDATE_STRATEGY candidates), Person 2 Horizons + LOLA horizon. Planning can take minutes per request."
if ($GeminiModel) { $env:GEMINI_MODEL = $GeminiModel }
$env:LUNA_GEMINI_LANG = $GeminiLang
if ($env:GEMINI_API_KEY -and $env:GEMINI_API_KEY -match '^[\x21-\x7E]+$') { Write-Host "Gemini: ON (model $(if ($env:GEMINI_MODEL) { $env:GEMINI_MODEL } else { 'gemini-3.5-flash-lite' }), summary language $GeminiLang)" }
elseif ($env:GEMINI_API_KEY) { Write-Host 'Gemini: OFF (GEMINI_API_KEY is not a real key; paste the key from Google AI Studio)' }
else { Write-Host 'Gemini: OFF (set $env:GEMINI_API_KEY to enable)' }
& (Join-Path $PSScriptRoot 'start_integrated.ps1') -Port $Port
