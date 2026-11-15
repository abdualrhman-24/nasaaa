import { CONFIG } from "./config.js?v=14";

/** kind: "network" | "validation" (422) | "upstream" (502) | "http" | "nav" */
export class ApiError extends Error {
  constructor(kind, status, message, details) {
    super(message);
    this.kind = kind; this.status = status; this.details = details;
  }
}

function formatValidation(detail) {
  if (!Array.isArray(detail)) return String(detail ?? "Invalid request");
  return detail.map((d) => {
    const loc = (d.loc || []).filter((x) => x !== "body").join(".");
    return loc ? `${loc}: ${d.msg}` : d.msg;
  }).join("; ");
}

async function call(base, path, body, { signal, service = "planner" } = {}) {
  let res;
  try {
    res = await fetch(base + path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError("network", 0, service === "planner"
      ? `Cannot reach the mission planner at ${CONFIG.apiBase}. Start it with: python -m uvicorn api.main:app --port 8000`
      : `Cannot reach Moon navigation at ${CONFIG.navBase}. Start it with: pnpm start (in original_modules/person3/moon_navigation)`);
  }
  const data = await res.json().catch(() => null);
  if (res.ok) return data;
  if (service === "nav") {
    const e = data?.error;
    throw new ApiError("nav", res.status, e ? `${e.code}: ${e.message}` : `HTTP ${res.status}`, e?.details);
  }
  if (res.status === 422) throw new ApiError("validation", 422, formatValidation(data?.detail), data?.detail);
  if (res.status === 502) throw new ApiError("upstream", 502, data?.error?.message || "Upstream or planning error", data?.error);
  throw new ApiError("http", res.status, data?.error?.message || `HTTP ${res.status}`, data);
}

/** Person 4 public API — contracts from API_CONTRACT.md / openapi.json */
const live = {
  health: () => call(CONFIG.apiBase, "/health"),
  plan: (requirements, opts) => call(CONFIG.apiBase, "/mission/plan", requirements, opts),
  replan: (previous, requirements, opts) => call(CONFIG.apiBase, "/mission/replan", { previous, requirements }, opts),
  compare: (requirements, opts) => call(CONFIG.apiBase, "/mission/compare", { requirements }, opts),
  /** Sun/Earth hourly azimuth+elevation (NASA/JPL Horizons via Person 2) and the LOLA terrain horizon for one site */
  sky: (body, opts) => call(CONFIG.apiBase, "/mission/sky", body, opts),
};

/** Recorded demo (hosted page, no backend): replays ONE real run saved in data/recorded_run.json, unchanged,
 *  and says so. It never computes or invents a result for other settings. */
let recordedP = null;
export const recordedRun = () => (recordedP ??= fetch("data/recorded_run.json", { cache: "no-cache" }).then((r) => {
  if (!r.ok) throw new ApiError("network", r.status, "Recorded run file data/recorded_run.json is missing.");
  return r.json();
}));
const notLive = (what) => () => Promise.reject(new ApiError("http", 0,
  `Recorded demo: ${what} needs the live backend (scripts/start_real_nasa.ps1 on your computer). This page replays one real run.`));
const replay = {
  health: async () => ({ status: "ok", mode: "recorded" }),
  plan: async () => {
    const R = await recordedRun(), P = structuredClone(R.plan);
    P.warnings = [`Recorded run, replayed: computed on ${R.recorded_at_utc.slice(0, 16).replace("T", " ")} UTC by the real backend on NASA data (${R.terrain.split(";")[0]}). `
      + `It is the default science mission (landing 1 to 3 Jan 2030, 96 h stay). Settings changed on this page are not re-planned here.`, ...P.warnings];
    return P;
  },
  replan: notLive("re-planning"),
  compare: notLive("the baseline comparison"),
  sky: async (body) => {
    const R = await recordedRun(), q = R.sky.request;
    const same = Math.abs(body.latitude_deg - q.latitude_deg) < 1e-5 && Math.abs(((body.longitude_deg - q.longitude_deg + 540) % 360) - 180) < 1e-5
      && new Date(body.start_utc).getTime() === new Date(q.start_utc).getTime() && body.duration_hours === q.duration_hours;
    if (!same) throw new ApiError("http", 0, "Recorded demo: the sky chart was recorded for the recommended site only. Other sites need the live backend.");
    return R.sky.response;
  },
};
export const planner = CONFIG.replay ? replay : live;

/** Person 3 moon_navigation API — contract from its API_CONTRACT.md (same calls as its apiClient.ts) */
const nav = (path, body) => call(CONFIG.navBase, path, body, { service: "nav" });
export const moonNav = {
  health: () => nav("/health"),
  sites: () => nav("/sites"),
  grid: (step = 2) => nav(`/terrain/grid?step=${step}`),
  sample: (lat, lon) => nav(`/terrain/sample?lat_deg=${lat}&lon_deg=${lon}`),
  routes: (start, target, maxSlopeDeg, algorithm = "astar") => nav("/routes", {
    start: { lat_deg: start.lat_deg, lon_deg: start.lon_deg },
    target: { lat_deg: target.lat_deg, lon_deg: target.lon_deg },
    constraints: { max_slope_deg: maxSlopeDeg },
    algorithm,
  }),
};
