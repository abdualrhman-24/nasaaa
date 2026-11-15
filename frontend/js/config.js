// Backend locations. Override with ?api=...&nav=... (saved to localStorage) when ports differ.
const q = new URLSearchParams(location.search);
function pick(key, fallback) {
  const fromQuery = q.get(key);
  try {
    if (fromQuery) localStorage.setItem(`luna.${key}`, fromQuery);
    return fromQuery || localStorage.getItem(`luna.${key}`) || fallback;
  } catch { return fromQuery || fallback; }
}
const REPLAY = q.has("replay") ? q.get("replay") === "1" : !/^(localhost|127\.0\.0\.1|\[::1\]|)$/.test(location.hostname);
export const CONFIG = {
  // Person 4 Mission Optimizer (FastAPI). Default CORS allows http://localhost:5173.
  apiBase: pick("api", "http://127.0.0.1:8000").replace(/\/$/, ""),
  // Person 3 moon_navigation (Express, CORS open). Optional: terrain layer + rover routes.
  navBase: pick("nav", "http://localhost:3003/api/v1").replace(/\/$/, ""),
  // Terrain grid: "pds" (NASA PDS LDEM_75S_240M, default) or "moontrek" (the same LOLA data exported from
  // NASA Moon Trek). ?terrain=moontrek is remembered like ?api; ?terrain=pds switches back.
  // The recorded demo defaults to Moon Trek, the terrain its recorded run used.
  terrain: pick("terrain", REPLAY ? "moontrek" : "pds"),
  // Recorded demo: on a hosted copy (e.g. GitHub Pages) there is no backend, so the planner replays one real
  // recorded run (data/recorded_run.json) and labels it. Local use stays live. ?replay=1 / ?replay=0 overrides.
  replay: REPLAY,
};
