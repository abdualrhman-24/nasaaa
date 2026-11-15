# Prompt for Claude Code

Copy everything below the line into Claude Code, opened in the project folder `LUNA_NAV_AI_MISSION_COMMAND`.

---

You are continuing work on **LUNA NAV AI**, our NASA Space Apps 2026 project for the "Lunar Landing Site Navigator" challenge. Read `PROJECT_HANDOFF.md` first. It describes the architecture, every change made so far, how to run the system on Windows PowerShell, and the accuracy results.

## Rules you must keep

- **Never fake data or progress.** Every measurement keeps its provenance badge (MOCK / UNVERIFIED / VERIFIED). Assumptions and simulated scenarios stay labelled.
- **Wording.** The system is "validated against NASA data", never "trained".
- **Accuracy.** Do not break it. After any change that touches terrain, visibility or ranking, run `.venv\Scripts\python.exe scripts\accuracy_check.py --quick`. Every check must still PASS. Run the full check (without `--quick`) at the end if time allows; it can take over an hour because each peak needs a lunar year from Horizons.
- **No secrets in commits.** Never commit `GEMINI_API_KEY` or any key. Keep `.gitignore` as is (it excludes `.venv/`, `*.img`, `.env`).
- **Compatibility.** Without the new env vars, existing behaviour stays as it is. Gemini must stay optional: with no key the system runs normally.
- **Environment.** Windows with PowerShell and Python 3.13 in `.venv`. The backend runs with `scripts\start_real_nasa.ps1`; the interface with `py -m http.server 5173` inside `frontend`.

## Tasks, in priority order

### T1. Use terrain data from the challenge's own tools (most important to the team)

The challenge lists these resources:
- QuickMap: https://quickmap.lroc.asu.edu/ (also https://quickmap.lroc.im-ldi.com/)
- Moon Trek: https://trek.nasa.gov/moon/
- Horizons: https://ssd.jpl.nasa.gov/horizons/ (already used live)

Our terrain is NASA LRO LOLA `LDEM_75S_240M` from NASA PDS, the same data QuickMap and Moon Trek display. The team wants it to come from those tools directly.

1. Investigate Moon Trek:
   - The south-pole layer catalogue: the API docs at https://trek.nasa.gov/tiles/apidoc/index.html, and each layer's `WMTSCapabilities.xml`.
   - Find a LOLA elevation (DEM) product for the south pole that offers **numeric** values: a GeoTIFF/raw download, or an elevation or profile query service.
2. Investigate QuickMap the same way: a LOLA elevation layer with export, or any documented API.
3. If a numeric product exists:
   - Download it with a new or extended script (resumable, like `scripts/get_nasa_lola.py`).
   - Convert it to the frontend grid (`scripts/build_lola_terrain.py`) and make Person 1 and Person 2 able to use it.
   - Set provenance to name the tool and URL.
   - Rerun the accuracy check and compare with the PDS version. Report both.
4. If only image tiles (PNG/JPG colours) exist, **do not** compute heights from colours. Write a short note in `PROJECT_HANDOFF.md` explaining what you found, keep PDS LOLA, and keep the "Open in QuickMap / Moon Trek" buttons for cross-checking.

### T2. Horizon visualization for the selected site

The challenge says Horizons Sun/Earth angular positions "form the foundation for your visualizations".

1. Backend:
   - Expose hourly Sun and Earth azimuth/elevation for a site and time window. Person 2 in `original_modules/person2/member2/visibility_planner/` already computes these internally; add an endpoint, or include them in the visibility response behind an option.
   - Expose the LOLA terrain horizon profile (elevation angle per azimuth) for the same site.
2. Frontend:
   - On the landing-site page, add a "Sky and horizon" chart: x = azimuth (0–360°), y = elevation angle.
   - Draw the terrain horizon as a filled silhouette, the Sun path and the Earth path as lines, with the stay window.
   - Mark the hours when each body is below the terrain.
   - Use the existing design tokens in `frontend/styles.css` and label the data source.
3. Test it with real data on the recommended site.

### T3. Person 3 routes service

Run `pnpm install` in `original_modules/person3/moon_navigation`, and make sure `start_real_nasa.ps1` starts it. The warning "Person 3 dependencies missing" must disappear, and traverse access must enter the ranking. If it fails, keep the current fallback (skip route scoring with a warning).

### T4. Explain the alternatives ordering

In the alternatives table, add a "Pareto layer" column, or a one-line note. Ordering is by Pareto layer and then MILP selection, so a lower row can have a higher single score.

### T5. Push to GitHub

Initialise git if needed and commit with a clear message.
- Check `git status` shows no `.venv`, `*.img` or keys.
- Push to the repo the team gives you. Ask for the URL if it is not set.

## When you finish

- Update `PROJECT_HANDOFF.md` (sections 5, 7 and 10) with what you changed and the new accuracy results.
- Give a short summary: what you did, what you found about Moon Trek/QuickMap, and the accuracy check output.
