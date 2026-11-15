"""Download NASA LRO LOLA elevation directly from NASA Moon Trek (a challenge resource) and write it
on the same 240 m south-polar grid as the PDS product LDEM_75S_240M, so Person 1, Person 2, the
frontend and the accuracy check can use it unchanged.

    .venv\\Scripts\\python.exe scripts\\get_moontrek_lola.py                 # about 70 MB from Moon Trek, resumable
    .venv\\Scripts\\python.exe scripts\\get_moontrek_lola.py --native-km 0   # fast: server-resampled 240 m only

Source (numeric values, not image colours):
  Moon Trek layer  LRO_LOLA_DEM_SPole75_30mp_v04  "LRO LOLA DEM, 75 deg v4, S Pole"  (Float32, 30 m/pixel,
  heights in metres relative to the 1737.4 km sphere, south polar stereographic, same extent as LDEM_75S_240M)
  Catalogue: https://trek.nasa.gov/moon/TrekServices/ws/index/getLayerServices?uuid=975eb591-9d09-4cc5-9ab3-b6f85f338944
  Raster service (ArcGIS ImageServer, listed by that catalogue entry):
     https://trek.nasa.gov/moon/trekarcgis/rest/services/LRO_LOLA_DEM_SPole75_30mp_v04/ImageServer
  The WMTS tiles of the same layer are coloured images and are NOT used.

How the 240 m grid is built (both parts come from Moon Trek only; no PDS values are mixed in):
  * inner square (|x|, |y| <= --native-km, default 92 km, which covers 90 S to about 87 S and the whole
    frontend grid): native 30 m pixels exported with exportImage, then averaged in 8 x 8 blocks onto each
    240 m cell. Tested against PDS LDEM_75S_240M: mean |difference| 2-3 m.
  * everything else (used by Person 2 for distant horizon terrain): 240 m values resampled by the Moon Trek
    server itself (exportImage at 240 m). The server point-samples its pyramid, so these cells differ from
    PDS by about 25-30 m on steep crater walls; far terrain moves the horizon by under 0.03 degree.

Output (same format as the PDS product: LSB int16, height = DN * 0.5 m):
  original_modules/person2/member2/data/lola/moontrek_ldem_75s_240m.img / .lbl / .json (provenance + PDS comparison)
Resumable: every exported tile is kept in data/lola/moontrek_cache/; run again after a network drop.
Standard library + numpy only (TIFF LZW decoder included).
"""
import argparse, datetime, json, math, struct, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LOLA = ROOT / "original_modules" / "person2" / "member2" / "data" / "lola"
LAYER = "LRO_LOLA_DEM_SPole75_30mp_v04"
LAYER_TITLE = "LRO LOLA DEM, 75 deg v4, S Pole"
LAYER_UUID = "975eb591-9d09-4cc5-9ab3-b6f85f338944"
SERVICE = f"https://trek.nasa.gov/moon/trekarcgis/rest/services/{LAYER}/ImageServer"
CATALOGUE = f"https://trek.nasa.gov/moon/TrekServices/ws/index/getLayerServices?uuid={LAYER_UUID}"
PRODUCT = "moontrek_ldem_75s_240m"
N, S, NATIVE = 3812, 240.0, 30.0           # output grid = PDS LDEM_75S_240M; Moon Trek native pixel
F = int(S / NATIVE)                        # 8 native pixels per output cell
HALF = N * S / 2                           # 457 440 m, identical to the Moon Trek layer extent
TILE = 64                                  # output cells per inner tile side (512 native pixels, 15.36 km)
STRIP = 128                                # output rows per server-resampled strip
UA = {"User-Agent": "luna-nav-ai/terrain-download"}

try:                                       # some machines need the OS certificate store
    import truststore; truststore.inject_into_ssl()
except ImportError:
    pass

# ------------------------------------------------------------------ minimal TIFF reader (LZW, float32)
def _lzw(data: bytes) -> bytes:
    """TIFF LZW (MSB-first codes, 9-12 bits, early change)."""
    out, table, bits, pos, prev = bytearray(), [bytes([i]) for i in range(256)] + [b"", b""], 9, 0, b""
    pad, end = data + b"\0\0\0", len(data) * 8
    while pos + bits <= end:
        b = pos >> 3; code = (int.from_bytes(pad[b:b + 3], "big") >> (24 - (pos & 7) - bits)) & ((1 << bits) - 1); pos += bits
        if code == 257: break
        if code == 256:
            del table[258:]; bits = 9; prev = b""; continue
        if not prev:
            prev = table[code]; out += prev; continue
        entry = table[code] if code < len(table) else prev + prev[:1]
        table.append(prev + entry[:1]); out += entry; prev = entry
        if len(table) >= (1 << bits) - 1 and bits < 12: bits += 1
    return bytes(out)

def read_tiff_f32(buf: bytes) -> np.ndarray:
    if buf[:4] != b"II*\0": raise ValueError("not a little-endian TIFF: " + buf[:200].decode("latin-1", "replace"))
    off = struct.unpack_from("<I", buf, 4)[0]; tags = {}
    for k in range(struct.unpack_from("<H", buf, off)[0]):
        tag, typ, cnt, val = struct.unpack_from("<HHII", buf, off + 2 + 12 * k)
        size = {3: 2, 4: 4}.get(typ, 1) * cnt; fmt = {3: "H", 4: "I"}.get(typ)
        if not fmt: continue
        raw = buf[off + 10 + 12 * k: off + 10 + 12 * k + size] if size <= 4 else buf[val:val + size]
        tags[tag] = struct.unpack(f"<{cnt}{fmt}", raw)
    w, h = tags[256][0], tags[257][0]; comp = tags.get(259, (1,))[0]
    if tags.get(258, (32,))[0] != 32 or tags.get(339, (3,))[0] != 3: raise ValueError("expected float32 samples")
    if tags.get(317, (1,))[0] != 1: raise ValueError("TIFF predictor not supported")
    dec = (lambda b: b) if comp == 1 else _lzw if comp == 5 else None
    if dec is None: raise ValueError(f"TIFF compression {comp} not supported")
    img = np.empty((h, w), np.float32)
    if 322 in tags:                                        # tiled
        tw, th = tags[322][0], tags[323][0]; across = math.ceil(w / tw)
        for t, (o, c) in enumerate(zip(tags[324], tags[325])):
            r, q = divmod(t, across); a = np.frombuffer(dec(buf[o:o + c])[:tw * th * 4], "<f4").reshape(th, tw)
            hh, ww = min(th, h - r * th), min(tw, w - q * tw); img[r * th:r * th + hh, q * tw:q * tw + ww] = a[:hh, :ww]
    else:                                                  # stripped
        rps = tags.get(278, (h,))[0]
        for t, (o, c) in enumerate(zip(tags[273], tags[279])):
            rows = min(rps, h - t * rps); img[t * rps:t * rps + rows] = np.frombuffer(dec(buf[o:o + c])[:rows * w * 4], "<f4").reshape(rows, w)
    return img

def export(x0, y0, x1, y1, w, h, attempts=12):
    url = (f"{SERVICE}/exportImage?bbox={x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}&size={w},{h}&format=tiff&pixelType=F32"
           f"&compression=LZ77&interpolation=RSP_NearestNeighbor&f=image")
    for k in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=900) as r: return read_tiff_f32(r.read())
        except Exception as e:  # network drop or server busy: back off and retry
            if k == attempts - 1: raise RuntimeError(f"Moon Trek export failed after {attempts} tries: {e}")
            time.sleep(min(60, 5 * (k + 1)))

# ------------------------------------------------------------------ jobs
def inner_jobs(native_km):
    k = math.ceil(native_km * 1000 / (TILE * S)) if native_km > 0 else 0
    for j in range(-k, k):
        for i in range(-k, k):
            yield ("inner", i, j)

def outer_jobs():
    for r0 in range(0, N, STRIP):
        yield ("outer", r0, min(STRIP, N - r0))

def run(job, cache):
    path = cache / (f"{job[0]}_{job[1]}_{job[2]}.npy")
    if path.exists(): return job, np.load(path)
    if job[0] == "inner":
        i, j = job[1], job[2]; x0, y0 = i * TILE * S, j * TILE * S
        a = export(x0, y0, x0 + TILE * S, y0 + TILE * S, TILE * F, TILE * F)
    else:
        r0, rows = job[1], job[2]; top = HALF - r0 * S
        a = export(-HALF, top - rows * S, HALF, top, N, rows)
    tmp = path.with_suffix(".tmp.npy"); np.save(tmp, a); tmp.replace(path)
    return job, a

def bad(a):
    return ~np.isfinite(a) | (np.abs(a) > 20000)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--native-km", type=float, default=92.0)
    ap.add_argument("--workers", type=int, default=16); a = ap.parse_args()
    cache = LOLA / "moontrek_cache"; cache.mkdir(parents=True, exist_ok=True)
    jobs = list(outer_jobs()) + list(inner_jobs(a.native_km))
    todo = [jb for jb in jobs if not (cache / f"{jb[0]}_{jb[1]}_{jb[2]}.npy").exists()]
    print(f"Moon Trek {LAYER}: {len(jobs)} exports ({len(jobs) - len(todo)} already cached), {a.workers} parallel connections")
    t0, done, lock = time.time(), [len(jobs) - len(todo)], threading.Lock()
    with ThreadPoolExecutor(a.workers) as ex:
        for f in as_completed([ex.submit(run, jb, cache) for jb in todo]):
            f.result()
            with lock: done[0] += 1
            print(f"\r  {done[0]} / {len(jobs)} exports, {time.time() - t0:.0f} s   ", end="", flush=True)
    print()
    grid = np.empty((N, N), np.float32)
    for jb in outer_jobs():
        _, arr = run(jb, cache); grid[jb[1]:jb[1] + jb[2]] = arr
    n_outer_bad = int(bad(grid).sum()); inner_cells = 0; n_inner_bad = 0
    c = N // 2                                               # column of x = 0 edge (1906)
    for jb in inner_jobs(a.native_km):
        _, arr = run(jb, cache); i, j = jb[1], jb[2]
        blk = arr.reshape(TILE, F, TILE, F); ok = ~bad(blk)
        mean = np.where(ok.all(axis=(1, 3)), np.where(ok, blk, 0).sum(axis=(1, 3)) / F / F, np.nan)
        col0, row0 = c + i * TILE, c - (j + 1) * TILE       # top row of the tile = highest y
        sub = grid[row0:row0 + TILE, col0:col0 + TILE]
        n_inner_bad += int(np.isnan(mean).sum())
        grid[row0:row0 + TILE, col0:col0 + TILE] = np.where(np.isnan(mean), sub, mean)  # incomplete block: keep server value
        inner_cells += TILE * TILE
    if bad(grid).any():
        sys.exit(f"Moon Trek returned no data for {int(bad(grid).sum())} cells; not writing a grid with gaps.")
    dn = np.clip(np.round(grid / 0.5), -32767, 32767).astype("<i2")
    img = LOLA / f"{PRODUCT}.img"; dn.tofile(img)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    half_native = math.ceil(a.native_km * 1000 / (TILE * S)) * TILE * S / 1000 if a.native_km > 0 else 0
    source = (f"NASA Moon Trek layer {LAYER} ({LAYER_TITLE}), LRO LOLA, via {SERVICE}; "
              + (f"30 m pixels averaged to 240 m within {half_native:.2f} km of the pole, Moon Trek 240 m resampling beyond" if half_native else "Moon Trek 240 m resampling"))
    (LOLA / f"{PRODUCT}.lbl").write_text(f"""PDS_VERSION_ID            = PDS3
/* Written by scripts/get_moontrek_lola.py. Not an official PDS product: a resampling of a NASA Moon Trek */
/* LOLA layer onto the grid of LDEM_75S_240M so the project readers can open it.                       */
LUNA_SOURCE               = "{source}"
LUNA_SOURCE_TOOL          = "NASA Moon Trek"
LUNA_SOURCE_URL           = "{SERVICE}"
LUNA_SOURCE_CATALOGUE     = "{CATALOGUE}"
PRODUCT_ID                = "{PRODUCT.upper()}"
PRODUCT_VERSION_ID        = "MOONTREK_{LAYER}"
PRODUCT_CREATION_TIME     = {now}
START_TIME                = 2009-07-13T00:00:00
STOP_TIME                 = 2011-09-30T00:00:00
/* Observation span: Moon Trek abstract, "altimetry data acquired through September 2011"; the start is */
/* the start of LRO LOLA science mapping.                                                              */
OBJECT                    = UNCOMPRESSED_FILE
FILE_NAME                 = "{PRODUCT.upper()}.IMG"
RECORD_TYPE               = FIXED_LENGTH
FILE_RECORDS              = {N}
RECORD_BYTES              = {N * 2}
  OBJECT                  = IMAGE
    NAME                  = HEIGHT
    LINES                 = {N}
    LINE_SAMPLES          = {N}
    SAMPLE_TYPE           = LSB_INTEGER
    SAMPLE_BITS           = 16
    UNIT                  = METER
    SCALING_FACTOR        = 0.5
    OFFSET                = 1737400.
  END_OBJECT              = IMAGE
END_OBJECT                = UNCOMPRESSED_FILE
OBJECT                    = IMAGE_MAP_PROJECTION
 MAP_PROJECTION_TYPE          = "POLAR STEREOGRAPHIC"
 A_AXIS_RADIUS                = 1737.4 <km>
 CENTER_LATITUDE              = -90 <deg>
 CENTER_LONGITUDE             = 0 <deg>
 MAP_SCALE                    = 240 <m/pix>
 MAXIMUM_LATITUDE             = -75 <deg>
 MINIMUM_LATITUDE             = -90 <deg>
 MAP_RESOLUTION               = 126.347 <pix/deg>
 LINE_PROJECTION_OFFSET       = 1905.5 <pix>
 SAMPLE_PROJECTION_OFFSET     = 1905.5 <pix>
 COORDINATE_SYSTEM_NAME       = "MEAN EARTH/POLAR AXIS OF DE421"
/* LOLA products use the mean Earth/polar axis frame; the .json sidecar records the cell-by-cell        */
/* agreement with PDS LDEM_75S_240M, which confirms the same frame, orientation and pixel registration.  */
END_OBJECT                    = IMAGE_MAP_PROJECTION
END
""", encoding="latin-1")
    meta = {"product": PRODUCT, "source_tool": "NASA Moon Trek", "layer": LAYER, "layer_title": LAYER_TITLE, "service": SERVICE,
            "catalogue": CATALOGUE, "downloaded_utc": now, "native_resolution_m": NATIVE, "output_resolution_m": S,
            "native_average_half_width_km": half_native, "inner_cells_incomplete_kept_server_value": n_inner_bad,
            "outer_nodata_cells": n_outer_bad, "description": source}
    pds = LOLA / "ldem_75s_240m.img"
    if pds.exists() and pds.stat().st_size == N * N * 2:   # independent comparison with the PDS product
        ref = np.memmap(pds, dtype="<i2", mode="r", shape=(N, N)).astype(np.float32) * 0.5
        def stats(sl):
            d = grid[sl] - ref[sl]
            return {"mean_m": round(float(d.mean()), 2), "mean_abs_m": round(float(np.abs(d).mean()), 2),
                    "p99_abs_m": round(float(np.percentile(np.abs(d), 99)), 1), "corr": round(float(np.corrcoef(grid[sl].ravel(), ref[sl].ravel())[0, 1]), 6)}
        k = int(76000 / S); mid = slice(c - k, c + k)
        meta["vs_pds_ldem_75s_240m"] = {"within_76_km_of_pole": stats((mid, mid)), "whole_grid": stats((slice(None), slice(None)))}
        print("Moon Trek minus PDS LDEM_75S_240M:", json.dumps(meta["vs_pds_ldem_75s_240m"]))
    (LOLA / f"{PRODUCT}.json").write_text(json.dumps(meta, indent=1))
    print(f"Done: {img} ({img.stat().st_size:,} bytes), heights {grid.min():.0f}..{grid.max():.0f} m")
    print("Use it: powershell -ExecutionPolicy Bypass -File scripts\\start_real_nasa.ps1 -Terrain moontrek")

if __name__ == "__main__":
    main()
