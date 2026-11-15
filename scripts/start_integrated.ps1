param([int]$Port = 8000)
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Install requirements into .venv first; see README.md.' }
$member1Dir = Join-Path $projectRoot 'original_modules\person1'
$member2Dir = Join-Path $projectRoot 'original_modules\person2\member2'
$member3Dir = Join-Path $projectRoot 'original_modules\person3\moon_navigation'
$env:LUNA_SITE_URL = 'http://127.0.0.1:8001'
$env:LUNA_VISIBILITY_URL = 'http://127.0.0.1:8002'
$member1 = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','landing_site_analyzer.app:app','--host','127.0.0.1','--port','8001' -WorkingDirectory $member1Dir -WindowStyle Hidden -PassThru
$member2 = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','visibility_planner.api:app','--host','127.0.0.1','--port','8002' -WorkingDirectory $member2Dir -WindowStyle Hidden -PassThru
$member3 = $null
if (Test-Path -LiteralPath (Join-Path $member3Dir 'node_modules')) {
  # 'pnpm start' runs tsx src/server/index.ts; use the project's own tsx when pnpm is not on PATH.
  $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
  $tsx = Join-Path $member3Dir 'node_modules\.bin\tsx.cmd'
  if ($pnpm) { $exe = $pnpm.Source; $args3 = @('start') }
  elseif (Test-Path -LiteralPath $tsx) { $exe = $tsx; $args3 = @('src/server/index.ts') }
  else { $exe = $null }
  if ($exe) {
    $env:LUNA_NAVIGATION_URL = 'http://127.0.0.1:3003'
    $env:PORT = '3003'
    $log = Join-Path $env:TEMP 'luna_person3.log'
    $member3 = Start-Process -FilePath $exe -ArgumentList $args3 -WorkingDirectory $member3Dir -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
    Write-Host "Person 3 routes: starting on :3003 (terrain $(if ($env:LUNA_TERRAIN_GRID_JSON) { $env:LUNA_TERRAIN_GRID_JSON } else { 'MOCK fixture' })); log $log"
  } else { Write-Warning 'Person 3 node_modules present but neither pnpm nor tsx was found; routes are not scored.' }
} else { Write-Warning 'Person 3 dependencies missing; run pnpm install in original_modules\person3\moon_navigation. Navigation remains MOCK.' }
try {
  & $pythonExe -m uvicorn api.main:app --host 127.0.0.1 --port $Port --app-dir $projectRoot
} finally {
  Stop-Process -Id $member1.Id,$member2.Id -ErrorAction SilentlyContinue
  if ($member3) { Stop-Process -Id $member3.Id -ErrorAction SilentlyContinue }
}
