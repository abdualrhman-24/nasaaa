# LUNA NAV AI: Project Handoff

NASA Space Apps Challenge 2026, challenge **"Lunar Landing Site Navigator"**.
Status as of 2026-11-15 (evening): working end to end on real NASA data. Terrain can now come straight from NASA Moon Trek, Person 3 routes enter the ranking, and a Sky and horizon chart was added. All accuracy checks PASS on both terrain sources.

---

## 1. What the system does

Picks a landing site near the lunar south pole for a chosen mission type and date, then checks whether the mission can continue after landing.

1. **Candidate sites** come from NASA LRO LOLA terrain: local peaks with gentle slope (peaks are where the sunlight is).
2. **Sunlight and Earth visibility** are computed for every site and landing day from NASA/JPL Horizons (live), with the real terrain horizon from LOLA.
3. **Rules** reject sites that break the limits: slope, minimum sunlight, longest Earth blackout.
4. **Ranking**: feasible options are layered by Pareto (sunlight, Earth contact, slope), then selected with MILP.
5. **Safety and continuity simulation** after landing: rover route (A* on LOLA), battery state of charge leg by leg, EVA limits, hazard scenarios. The verdict is GO, GO WITH CONDITIONS or NO-GO.
6. **Explanation** of why the site was chosen, with the source of every number. Gemini can optionally write a plain-language summary, and every number in it is checked against the data.

**Honesty rules.** Follow these in all future work:
- Never fake agent progress or measurements.
- Every measurement carries a provenance badge: MOCK, UNVERIFIED or VERIFIED. Supplier "REAL" data is shown as UNVERIFIED because no independent party has reviewed it.
- Rover speed, battery and EVA limits are editable assumptions, labelled as such.
- Hazard scenarios are labelled as simulated.
- The system is **validated, not trained**. It is deterministic; no model was trained.

---

## 2. Challenge resources and how we use them

| Challenge resource | Used? | How |
| --- | --- | --- |
| **NASA/JPL Horizons** (`ssd.jpl.nasa.gov/horizons`) | Yes, directly | Person 2 calls `https://ssd.jpl.nasa.gov/api/horizons.api` live for Sun and Earth positions (MOON_ME frame). Responses are cached in memory per URL while the server runs (`lru_cache` in `original_modules/person2/member2/visibility_planner/sources.py`). |
| **Moon Trek** (`trek.nasa.gov/moon`) | **Yes, directly (optional terrain source)** | Moon Trek layer `LRO_LOLA_DEM_SPole75_30mp_v04` ("LRO LOLA DEM, 75 deg v4, S Pole", 30 m/pixel, Float32 metres) has a numeric **ArcGIS ImageServer** next to its WMTS image tiles: `https://trek.nasa.gov/moon/trekarcgis/rest/services/LRO_LOLA_DEM_SPole75_30mp_v04/ImageServer`. `scripts/get_moontrek_lola.py` exports it and averages the 30 m pixels onto our 240 m grid. Every module can run on it (`-Terrain moontrek`). PDS stays the default. The "Open in Moon Trek" button stays. |
| **QuickMap** (`quickmap.lroc.asu.edu`) | Cross-check only | QuickMap's WMS (`wms.im-ldi.com`) offers 32-bit TIFF, but its only numeric lunar elevation layer is `luna_wac_dtm_numeric_meters(_absolute)`, documented as **GLD100** (LROC WAC stereo), not LOLA. Sampled at 70-90 S it differs from LOLA by about 1.7 km on average (correlation 0.44 south of 85 S), so we do not use it. The "Open in QuickMap" button stays for visual cross-checks. |
| **NASA PDS** (`pds-geosciences.wustl.edu`) | Yes, default terrain | LOLA `LDEM_75S_240M`, `pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/`. |
| **CSA Moon Exploration** | Context only | Shown in the interface's "Challenge resources" panel. It links the rover simulation to Canada's south-pole rover plans. |

**Terrain from the challenge tools (T1, done):** Moon Trek's LOLA layer gives the same terrain as PDS. Within 76 km of the pole, the mean |difference| is 1.9 m (99th percentile 10 m, correlation 0.999997). Every accuracy check passes on it (section 7). QuickMap has no numeric LOLA layer (table above). Details: section 5, item 14.

Other NASA references:
- `LDSM_75S_240M`: NASA's official slope map, used only to validate our slopes.
- NASA Artemis III candidate regions: drawn on the map, and used for site names and an independent check.

---

## 3. Architecture

```
NASA LOLA (PDS)  ──► Person 1: sites (FastAPI, :8001)  ──┐
NASA LOLA (PDS)  ──► Person 2: visibility (FastAPI, :8002) ◄── NASA/JPL Horizons API (live)
Person 3: routes (Express, :3003, optional) ─ ─ ─ ─ ─ ─ ─ ┤
                                                          ▼
                 Person 4: planner (FastAPI + LangGraph, :8000) ◄──► Google Gemini (optional, language only)
                                                          │
                                                          ▼
                 Browser interface (static, :5173): 3D LOLA explorer, safety simulation, LUNA WALK
```

**Person 4 LangGraph nodes (7):** supervisor → site_analysis → visibility_analysis → navigation (conditional) → validation → optimization → explanation.

**Endpoints:** `POST /mission/plan`, `POST /mission/replan`, `POST /mission/compare`, `GET /health`.

---

## 4. Main files

| Path | Role |
| --- | --- |
| `frontend/index.html`, `frontend/styles.css` | Interface. Five phases: cabin, mission setup, agents, landing site, safety simulation; plus the explorer. |
| `frontend/js/app.js` | Main flow, dossier, explorer, readable site names, QuickMap/Moon Trek buttons, English date/time selects. |
| `frontend/js/terrain.js` | `Terrain` class: slope, features, A* port of Person 3, masks. Loads `data/lola_south_pole.json`. |
| `frontend/js/safety.js` | Safety simulation: state-of-charge battery model, `snapToTraversable`, scenarios. |
| `frontend/js/gl3d.js` | Hand-written WebGL 3D view (orbit and walk). No Three.js; works offline. |
| `frontend/data/lola_south_pole.json` | 666×666 cells at 240 m (±79.8 km), built from the real LOLA file, plus named features. |
| `orchestration/engine.py` | Person 4 graph. Gemini hooks, route-service fallback, UNVERIFIED handling. |
| `orchestration/gemini.py` | Gemini REST client: structured JSON, retries, fallback models, number-grounding check. |
| `api/main.py` | FastAPI app. Error responses carry CORS headers, so the browser shows the real error. |
| `tools/services.py` | Service adapters. `MockNavigationService.FIXTURE` knows only demo sites A, B and C. |
| `schemas/models.py` | Pydantic models. `PlanResponse` has `ai_summary` and `llm_provider`. |
| `original_modules/person1/...` | Polar stereographic support and the `elevated` candidate strategy. |
| `scripts/get_nasa_lola.py` | Downloads LOLA products: `ldem_75s_240m` (default), `ldsm_75s_240m`, `ldem_16`. |
| `scripts/get_moontrek_lola.py` | Exports LOLA from NASA Moon Trek's ImageServer onto the same 240 m grid (`moontrek_ldem_75s_240m.img/.lbl/.json`). Resumable tile cache in `data/lola/moontrek_cache/`. |
| `scripts/build_lola_terrain.py` | Builds `frontend/data/lola_south_pole.json`; `--source moontrek` builds `lola_south_pole_moontrek.json`. |
| `scripts/start_real_nasa.ps1` | Starts every service in real-NASA mode, including Person 3 routes on LOLA. Options `-Terrain pds` or `moontrek`, `-NavTargetLat`, `-NavTargetLon`. Prints Gemini ON or OFF. |
| `scripts/accuracy_check.py` | Accuracy report against NASA references. `--quick` skips the four slow peak checks; `--terrain moontrek` checks the Moon Trek grid (reports `accuracy_report*_moontrek.*`). Service URLs via `LUNA_ACCURACY_P1/P2/P4`. |
| `scripts/check_gemini.py` | Checks the Gemini key and model before a demo. |
| `README_AR.md` | Arabic run guide for teammates. |
| `.gitignore` | Excludes `.venv/`, `*.img`, `*.lbl`, `.env`, `node_modules/`, `*.zip`, `Claude outputs/`. |

---

## 5. Work done (chronological summary)

1. **Interface built** from scratch:
   - Spacecraft cabin.
   - Four mission types.
   - Honest agent pipeline.
   - 3D Moon explorer.
   - Safety and continuity simulation.
   - LUNA WALK.
   - Provenance on every number.
2. **Real NASA terrain** replaced the synthetic and mock terrain (LOLA `LDEM_75S_240M`). Mock Person 3 sites are hidden when LOLA is loaded.
3. **Person 1** gained polar stereographic support and the `elevated` strategy (`LUNA_P1_CANDIDATE_STRATEGY=elevated`). Sunlight at candidates rose from about 40% to 85–94%.
4. **Person 4** gained these fixes:
   - UNVERIFIED recommendations are opt-in (`LUNA_ALLOW_UNVERIFIED_RECOMMENDATION=1`) and come with a warning.
   - The explanation status label was fixed.
5. **Safety model** recalibrated:
   - State-of-charge battery.
   - Destination placed on traversable ground toward the nearest named crater.
6. **Accuracy check** written; all checks PASS (section 7).
7. **Gemini integrated**:
   - Supervisor: interprets the mission type when the request doesn't state it.
   - Explanation agent: writes a plain-language summary.
   - The summary is rejected if any number in it doesn't match the evidence.
   - Retries and fallback models, so a busy model doesn't block the plan.
   - Default model `gemini-3.5-flash-lite` with thinking off (fast). Fallbacks: `gemini-3.1-flash-lite`, `gemini-flash-lite-latest`, `gemini-3.8-flash`.
8. **Interface simplified** for judges:
   - Visible: mission type, date, time, stay length, place.
   - Everything else in a collapsed "Advanced settings".
9. **Bugs fixed**:
   - "Planner unreachable": error responses had no CORS header.
   - `KeyError: 'site_…'`: Person 3 was not running and the mock route fixture only knew sites A/B/C. Now the planner skips route scoring with a clear warning instead of inventing routes.
10. **Readable site names** from NASA references:
    - Inside an Artemis III region (≤ 7.5 km from its centre): the region name.
    - Near the Shackleton rim: "Shackleton rim".
    - On the Connecting ridge: "On Connecting ridge".
    - Otherwise: "Near <IAU feature>, N km".
11. **Challenge resources** added:
    - QuickMap and Moon Trek buttons.
    - "Challenge resources and how we use them" panel, including CSA.
12. **English date/time**: native inputs showed Arabic-Indic digits on an Arabic Windows, so they were replaced with selects. Script and stylesheet are cache-busted (`?v=9`).
13. **Accuracy script**:
    - Timeout raised to 1800 s (`LUNA_ACCURACY_TIMEOUT`).
    - `--quick` mode writes `accuracy_report_quick.*` and never overwrites the full report.
14. **Terrain from NASA Moon Trek (T1)**:
    - Where the numbers are: the Moon Trek catalogue (`TrekServices/ws/index/getLayerServices?uuid=975eb591-9d09-4cc5-9ab3-b6f85f338944`) lists two services for `LRO_LOLA_DEM_SPole75_30mp_v04`: a WMTS (colour tiles) and an **ArcGIS ImageServer** (`exportImage`, Float32). The API doc page hides DEM layers by default (its search filter excludes `DEM`), which is why Moon Trek looked tile-only.
    - `scripts/get_moontrek_lola.py`: 144 native 30 m tiles (inner ±92 km), averaged 8×8 onto each 240 m cell. The rest of the 75 S grid comes from 30 strips resampled by Moon Trek itself; they are used only for distant horizon terrain. TIFF/LZW is decoded with the standard library. About 70 MB, 19 min with 16 connections, resumable.
    - Why averaging: on two 24 km test blocks, Moon Trek's own 240 m resampling point-samples and differs from PDS by 24-31 m on average. 8×8 averaging of the native pixels differs by 2-3 m.
    - The output uses the PDS format (int16, DN × 0.5 m), so Person 1 and Person 2 read it unchanged. The label carries `LUNA_SOURCE*` keys: Person 1 reports provider "NASA Moon Trek" with the ImageServer URL, and Person 2's horizon source names the layer and URL.
    - Selection: Person 2 uses `LUNA_LOLA_PRODUCT`, the frontend `?terrain=moontrek` (remembered; `?terrain=pds` switches back). The default everywhere is still PDS.
    - Moon Trek minus PDS within 76 km of the pole: mean +0.08 m, mean |diff| 1.86 m, 99th percentile 10.1 m, correlation 0.999997. Over the whole 75 S grid: mean |diff| 15.7 m (the server-resampled outer part).
    - QuickMap was checked too: no numeric LOLA layer (section 2).
15. **Sky and horizon chart (T2)**:
    - `POST /mission/sky` on the planner returns hourly Sun and Earth azimuth/elevation from NASA/JPL Horizons (Person 2 `include_time_series`) and the LOLA horizon profile (Person 2 `GET /horizon-profiles/lola`). It fetches both in parallel and passes the values through unchanged. In mock mode it returns 503 instead of inventing values.
    - The landing-site page has a new panel, "Sky and horizon at the landing site": azimuth 0-360 on x, elevation on y. The LOLA horizon is a filled silhouette. The Sun path (solid, `--sun`) and Earth path (dashed, `--link`) cover the stay window. Hollow points and an hour strip mark the hours a body is behind terrain. An hourly table sits under "Hourly values". Data sources and the UNVERIFIED badge are shown.
    - Tested at the recommended site (−88.807°, 123.6°E, 2030-01-01, 96 h): the Sun is above terrain in all 97 samples and the Earth is hidden in 22, consistent with the 74-96 h Earth totals. Also checked in the browser on Moon Trek terrain.
16. **Person 3 routes (T3)**:
    - `pnpm install` is done (pnpm 10.18.0 through `npx`, because pnpm is not installed globally). `start_integrated.ps1` runs `pnpm start` when pnpm is on PATH, otherwise the project's own `node_modules\.bin\tsx.cmd`, and logs to `%TEMP%\luna_person3.log`. The warning "Person 3 dependencies missing" is gone.
    - Person 3 ran on a synthetic MOCK terrain, which would have marked every option MOCK. Its `terrain.ts` now loads a real grid from `LUNA_TERRAIN_GRID_JSON` (the frontend LOLA JSON, in the same layout as its `/terrain/grid`). Without the variable it keeps the fixture, and all 30 of its tests still pass.
    - The traverse target is an editable assumption: `-NavTargetLat/-NavTargetLon`, default the south pole point on Shackleton's rim (−89.97, 0). Every Person 1 candidate reaches it within 15°, and none sits on it. The plan warnings state the target.
    - Adapter: a 422 from Person 3 (no route within the slope limit, or off the grid) marks that site "route inaccessible" instead of failing the plan. One route per site serves every landing day.
    - Routes change the ranking. Test run (2 days, 96 h, target then at the Connecting ridge): the recommendation moved to −89.31°, 245.9°E, 10.5 km from the target. The choice now depends on the target you set.
17. **Pareto layer (T4)**: each option carries `pareto_layer` (1 = non-dominated). The alternatives table shows a "Pareto layer" column and a one-line note on why a lower row can have a higher score.
19. **Hosted demo (GitHub Pages)**:
    - Root `index.html` opens `frontend/?v=14`, so visitors skip pages cached by GitHub Pages (10 min).
    - On any host other than localhost, the planner **replays one recorded real run**: `frontend/data/recorded_run.json`, saved unchanged from `start_real_nasa.ps1 -Terrain moontrek` with the interface defaults, plus its sky data. A banner, the status line and the first plan warning say it is recorded. Re-planning, the baseline comparison and other sites' sky charts refuse with a message instead of inventing values. `?replay=1` or `?replay=0` overrides.
    - Autoplay: the hosted page loads the recorded run and opens the safety simulation once the terrain has loaded. `?autoplay=0` keeps the normal start.
    - Terrain, 3D explorer, browser routes, LUNA WALK and the safety simulation run live in the visitor's browser on the Moon Trek LOLA grid.
    - To refresh the recording after a backend change: run the stack, POST the interface defaults to `/mission/plan` and the recommended site to `/mission/sky`, and rebuild `recorded_run.json` the same way.
20. **Safety simulation, reachable survey points**: automatic survey and sample points now snap only to ground the rover can reach from the landing site (flood fill under the slope limit, the same rule as the A* port). For a site on Shackleton's rim, "5 km toward Shackleton" had fallen on an isolated patch inside the crater, giving a false NO-GO. It now uses the closest reachable ground toward that target (up to 15 km away) and says how far it moved. Points the user picks are unchanged.
21. **Landing-site page**: redraws when the terrain arrives after the plan, so sites get readable names on slow connections.
18. **Robustness and housekeeping**:
    - `LUNA_MEMBER2_ENGINE=horizons`, set by `start_real_nasa.ps1`, gives Horizons Person 2's own 60 s × 3 retries. The default "auto" engine tries once for 15 s and then needs SPICE kernels, which are not installed, so one slow Horizons answer failed the whole plan.
    - Frontend modules are cache-busted with `?v=10`.
    - A planner test that called the async explanation node synchronously was fixed (22/22 pass).

---

## 6. How to run (Windows PowerShell)

**Window 1, backend** (project root):
```powershell
$env:GEMINI_API_KEY = "<optional key>"   # omit to run without Gemini
powershell -ExecutionPolicy Bypass -File scripts\start_real_nasa.ps1
```
Wait for `Uvicorn running on http://127.0.0.1:8000`.

**Window 2, interface:**
```powershell
cd frontend
py -m http.server 5173
```
Open `http://localhost:5173`, not port 8000.

**Terrain from NASA Moon Trek (optional):**
```powershell
.venv\Scripts\python.exe scripts\get_moontrek_lola.py                      # once, ~70 MB, resumable
.venv\Scripts\python.exe scripts\build_lola_terrain.py --source moontrek    # frontend and route grid
powershell -ExecutionPolicy Bypass -File scripts\start_real_nasa.ps1 -Terrain moontrek
```
Then open `http://localhost:5173/?terrain=moontrek` (`?terrain=pds` switches back).

**Person 3 routes (once):** in `original_modules\person3\moon_navigation` run `npx pnpm@10.18.0 install` (or `pnpm install`). `start_real_nasa.ps1` then starts it on :3003 with the LOLA grid.

**Accuracy:**
```powershell
.venv\Scripts\python.exe scripts\accuracy_check.py           # full, slow (Horizons, lunar year per peak)
.venv\Scripts\python.exe scripts\accuracy_check.py --quick   # skips peaks A-D
.venv\Scripts\python.exe scripts\accuracy_check.py --quick --terrain moontrek   # stack started with -Terrain moontrek
```
If you pipe the output on an Arabic Windows console, set `$env:PYTHONIOENCODING = 'utf-8'` first, or the `≥` sign stops the script.

**Free the ports:**
```powershell
foreach ($p in 8000,8001,8002,3003) { Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }
```

**First-time setup** (Python 3.13):
```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r original_modules\person1\requirements.txt -r original_modules\person2\member2\requirements.txt
.venv\Scripts\python.exe scripts\get_nasa_lola.py
.venv\Scripts\python.exe scripts\get_nasa_lola.py --product ldsm_75s_240m
.venv\Scripts\python.exe scripts\build_lola_terrain.py
```

---

## 7. Accuracy results

Two terrain sources, same checks. PDS full run 2026-11-14, PDS quick run 2026-11-15 (identical). Moon Trek full run 2026-11-15 (`accuracy_report_moontrek.md`) and quick run (`accuracy_report_quick_moontrek.md`).

| Check | PDS `LDEM_75S_240M` | Moon Trek export | Reference | Result (both) |
| --- | --- | --- | --- | --- |
| Shackleton depth | 4.10 km | 4.10 km | 4.1 km | PASS |
| Shackleton diameter | 20.6 km | 20.6 km | 21 km | PASS |
| Slope vs NASA LDSM | corr 0.94, mean −0.7°, \|diff\| 1.0°, 96.8% same 15° decision | corr 0.94, mean −0.7°, \|diff\| 1.0°, 96.7% | NASA LDSM_75S_240M | PASS |
| Shackleton floor sunlight | 0% | 0% | 0% | PASS |
| Sunlight A / B / C / D (local peak) | 88.9 / 93.8 / 85.3 / 88.3% | 88.9 / 93.8 / 86.5 / 88.3% | 81 / 82 / 85 / 86% | PASS |
| Sites vs Artemis III | 1 of 6 inside, 0.4 km from "Peak Near Shackleton" | same 6 sites | ≥ 1 inside | PASS |
| End-to-end | no MOCK, 6 candidates | no MOCK, 6 candidates | no MOCK | PASS |

Moon Trek grid against PDS, cell by cell, within 76 km of the pole: mean +0.08 m, mean |diff| 1.86 m, 99th percentile 10.1 m, correlation 0.999997.

**Recommended site** (depends on settings and, with routes, on the traverse target):
- Without routes (earlier runs): −88.807°, 123.6°E, elevation about 1646 m. Sunlight 96 of 96 h; Earth in view 74-96 h depending on the day. Slope 0.6-0.7°. Safety verdict GO.
- Interface defaults with Person 3 routes (target at the pole, traverse limit 10 km, recorded for the hosted demo): "Shackleton rim, 10.5 km from centre", −89.779°, 204.27°E, 3 Jan 2030. Sun above the terrain all 97 hourly samples, Earth too. Safety verdict GO WITH CONDITIONS (16.4 km rover loop).

## 8. Problems solved (for reference)

| Problem | Fix |
| --- | --- |
| Candidate sites on peak flanks (≈ 40% sun) | `elevated` peak strategy (85–94%) |
| Published peak coordinates fail on 240 m grid | Snap to nearest LOLA peak within 1.4 km |
| Unrealistic NO-GO | State-of-charge battery; traversable destination |
| Gemini 503 / timeouts / `gemini-2.5-flash` retired | `flash-lite`, thinking off, retries, fallback models, model name from env |
| "Planner unreachable" hid real errors | CORS headers on error responses |
| `KeyError` without Person 3 | Skip route scoring with a warning; never invent routes |
| Supervisor read "exploration" instead of "science" | Request text changed |
| Arabic digits in date/time | English selects |
| Stale `app.js` in browser | `?v=9` cache-busting |
| `site_…` names meaningless | NASA-reference names |

---

## 9. Known limits

- The grid is 240 m, so boulders and small craters are not visible. Our slopes read about 0.7° gentler than NASA's 30–120 m baseline.
- Data status is UNVERIFIED: real NASA data, not independently reviewed. The recommendation is for planning, not flight.
- Traverse access is scored against one target point (default the pole on Shackleton's rim). That target is an assumption, and changing it can change the recommended site. Routes are slope-only and not operationally validated.
- The Moon Trek grid averages native 30 m pixels only within ±92 km of the pole. Farther out (used only for distant horizon terrain), it uses Moon Trek's own 240 m resampling, which differs from PDS by about 16 m on average.
- The Sky and horizon chart samples every hour. The visibility totals use 10-minute samples with rise and set refined to about 1 s, so hour counts can differ by one.
- Person 2's offline SPICE fallback needs kernels (`scripts/fetch_kernels.py`), which are not installed. Without them, plans depend on Horizons being reachable. `LUNA_MEMBER2_ENGINE=horizons` adds retries.

---

## 10. Remaining tasks (priority order)

Done on 2026-11-15: T1 (Moon Trek terrain), T2 (Sky and horizon chart), T3 (Person 3 routes), T4 (Pareto layer). See section 5, items 14-18.

**T5. GitHub (done).** Repository https://github.com/abdualrhman-24/nasaaa, branch `main`. `.gitignore` also excludes the Moon Trek tile cache (`moontrek_cache/`, `*.npy`, about 200 MB). Checked before every commit: no `.venv`, `*.img`, `*.lbl`, `.env`, `node_modules` or keys. Commits use the GitHub noreply address.

**Demo link for judges:** https://abdualrhman-24.github.io/nasaaa/ (GitHub Pages from `main`, root; the team also added `.github/workflows/jekyll-gh-pages.yml`, and both deployments succeed). See section 5, item 19.

**Next, if time allows:**
- Choose the traverse target with the team (a science target such as a permanently shadowed crater edge), and show it on the map.
- Run the full accuracy check again on PDS after any terrain change. The last full PDS run is 2026-11-14; the code paths it covers did not change.
- Optionally download the SPICE kernels so Person 2 can work offline when Horizons is slow.
- `README_AR.md`: add the Moon Trek commands from section 6.
