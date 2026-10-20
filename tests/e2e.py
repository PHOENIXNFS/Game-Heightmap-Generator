"""Black-box end-to-end tests. Run: python tests\\e2e.py  (server must run on :8765)."""

import io
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

BASE = "http://127.0.0.1:8765"
CHECKS = [0, 0]


def req(path, body=None, method=None, timeout=180):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = method or "POST"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=timeout)
        return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def check(name, cond, detail=""):
    CHECKS[1] += 1
    if cond:
        CHECKS[0] += 1
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")


ISLANDS = [
    {"cx": 0.32, "cy": 0.35, "radius": 0.26, "angle": 0.7},
    {"cx": 0.62, "cy": 0.58, "radius": 0.22, "angle": 2.1},
    {"cx": 0.82, "cy": 0.22, "radius": 0.11, "angle": 5.0},
]

CONFIG = {
    "width": 505,
    "height": 505,
    "seed": 42,
    "sea_level": 0.15,
    "noise": {"scale": 6, "octaves": 6, "persistence": 0.5, "lacunarity": 2,
              "detail_amp": 0.6, "coast_warp": 0.35, "edge_margin": 0.04},
    "islands": ISLANDS,
    "erosion": {"enabled": True, "droplets": 40000, "max_steps": 30},
}


def main():
    print("== static + meta ==")
    st, h, raw = req("/")
    check("index.html served", st == 200 and b"Terrain Heightmap" in raw)
    for asset in ("/style.css", "/app.js", "/preview2d.js", "/preview3d.js"):
        st, _, raw = req(asset)
        check(f"{asset} served", st == 200 and len(raw) > 500)
    st, _, raw = req("/api/defaults")
    defaults = json.loads(raw)
    isl0 = defaults["config"]["islands"][0] if defaults.get("config", {}).get("islands") else {}
    check("defaults", st == 200 and "config" in defaults and "islands" in defaults["config"])
    check("defaults island angle is a number", isinstance(isl0.get("angle"), (int, float)))
    check("defaults has no elevation field", "elevation" not in isl0)

    print("== preview ==")
    t0 = time.time()
    st, _, raw = req("/api/preview", {"config": CONFIG}, timeout=240)
    prev = json.loads(raw)
    check("preview ok", st == 200 and prev["status"] == "done", str(prev))
    print(f"       preview {prev['width']}x{prev['height']} in {prev['ms']}ms")
    st, hds, raw = req(f"/api/heights/{prev['id']}")
    w, hh = int(hds.get("X-Width")), int(hds.get("X-Height"))
    heights_prev = np.frombuffer(raw, "<f4").reshape(hh, w)
    check("preview heights size", w * hh * 4 == len(raw))
    check("preview heights finite", bool(np.isfinite(heights_prev).all()))
    check("preview range [0,1]", heights_prev.min() >= 0 and heights_prev.max() <= 1.0001)
    check("preview has land", float((heights_prev > CONFIG["sea_level"]).mean()) > 0.05)
    check("preview borders are ocean", float(max(
        heights_prev[0].max(), heights_prev[-1].max(),
        heights_prev[:, 0].max(), heights_prev[:, -1].max())) < 1e-6)
    check("preview island slopes to sea (not a slab)",
          float(heights_prev[heights_prev > CONFIG["sea_level"]].min()) < 0.6,
          f"min land {heights_prev[heights_prev > CONFIG['sea_level']].min():.3f}")

    st, _, raw2 = req("/api/preview", {"config": CONFIG}, timeout=240)
    prev2 = json.loads(raw2)
    st, _, raw_b = req(f"/api/heights/{prev2['id']}")
    check("deterministic seeds", raw_b == raw)

    print("== island controls ==")
    # rotation changes shape
    base = dict(ISLANDS[0])
    cfg_a0 = dict(CONFIG, islands=[dict(base, angle=0.0)])
    cfg_a90 = dict(CONFIG, islands=[dict(base, angle=np.pi / 2)])
    st, _, r0 = req("/api/preview", {"config": cfg_a0}, timeout=240)
    p0 = json.loads(r0)
    st, _, h0 = req(f"/api/heights/{p0['id']}")
    st, _, r90 = req("/api/preview", {"config": cfg_a90}, timeout=240)
    p90 = json.loads(r90)
    st, _, h90 = req(f"/api/heights/{p90['id']}")
    check("rotation changes shape", p0["status"] == "done" and p90["status"] == "done" and h0 != h90)

    # rigid rotation: with relief off + edge margin off, 90 deg == np.rot90
    from core.compose import compose_islands
    ctr = 127.5 / 256
    rigid_isl = {"cx": ctr, "cy": ctr, "radius": 0.28, "angle": 0.0}
    kw = dict(width=256, height=256, seed=7, noise_scale=2.5,
              detail_amp=0.0, coast_warp=0.4, edge_margin=0.0)
    r0m = compose_islands(islands=[dict(rigid_isl, angle=0.0)], **kw)
    r90m = compose_islands(islands=[dict(rigid_isl, angle=np.pi / 2)], **kw)
    r180m = compose_islands(islands=[dict(rigid_isl, angle=np.pi)], **kw)
    check("rotation is rigid (90 deg)",
          float(np.abs(np.rot90(r0m, -1) - r90m).max()) < 1e-6)
    check("rotation is rigid (180 deg)",
          float(np.abs(np.rot90(r0m, 2) - r180m).max()) < 1e-6)

    # aspect (elongation) changes the island planform
    e1 = compose_islands(
        width=256, height=256,
        islands=[{"cx": ctr, "cy": ctr, "radius": 0.28, "aspect": 1.0, "angle": 0.4}],
        seed=7, noise_scale=2.5, detail_amp=0.4, coast_warp=0.35,
        sea_level=0.15, edge_margin=0.0)
    e2 = compose_islands(
        width=256, height=256,
        islands=[{"cx": ctr, "cy": ctr, "radius": 0.28, "aspect": 1.8, "angle": 0.4}],
        seed=7, noise_scale=2.5, detail_amp=0.4, coast_warp=0.35,
        sea_level=0.15, edge_margin=0.0)
    check("aspect changes shape", float(np.abs(e1 - e2).max()) > 1e-3)

    # size control changes land area
    cfg_small = dict(CONFIG, islands=[dict(base, radius=0.12)])
    cfg_big = dict(CONFIG, islands=[dict(base, radius=0.4)])
    st, _, rs = req("/api/preview", {"config": cfg_small}, timeout=240)
    ps = json.loads(rs)
    st, _, hs_raw = req(f"/api/heights/{ps['id']}")
    st, _, rb = req("/api/preview", {"config": cfg_big}, timeout=240)
    pb = json.loads(rb)
    st, _, hb_raw = req(f"/api/heights/{pb['id']}")
    hs_arr = np.frombuffer(hs_raw, "<f4")
    hb_arr = np.frombuffer(hb_raw, "<f4")
    check("size control changes land",
          float((hb_arr > CONFIG["sea_level"]).mean()) > float((hs_arr > CONFIG["sea_level"]).mean()))

    # island count: 1 island vs 3 islands
    cfg_one = dict(CONFIG, islands=[ISLANDS[0]])
    st, _, r1 = req("/api/preview", {"config": cfg_one}, timeout=240)
    p1 = json.loads(r1)
    st, _, h1 = req(f"/api/heights/{p1['id']}")
    check("island count changes shape", h1 != raw)

    # same coords must sample identically (sample == rows)
    from core.noise import fbm
    xs = np.arange(64, 128, dtype=np.float64)[None, :] * np.ones((64, 1))
    ys = np.arange(64, 128, dtype=np.float64)[:, None] * np.ones((1, 64))
    check("fbm deterministic", float(np.abs(fbm(xs, ys, 4242) - fbm(xs, ys, 4242)).max()) == 0.0)

    print("== full generation (505, UE preset) ==")
    t0 = time.time()
    st, _, raw = req("/api/generate", {"config": CONFIG})
    gen = json.loads(raw)
    check("generate queued", st == 200 and "id" in gen)
    jid = gen["id"]
    status = None
    while True:
        st, _, raw = req(f"/api/status/{jid}")
        status = json.loads(raw)
        if status["status"] in ("done", "error"):
            break
        time.sleep(0.3)
        if time.time() - t0 > 180:
            break
    print(f"       full gen took {time.time() - t0:.1f}s (job ms={status['ms']})")
    check("full done", status["status"] == "done", str(status))
    check("full stats present", status.get("stats") is not None)
    st, hds, raw = req(f"/api/heights/{jid}")
    w, hh = int(hds.get("X-Width")), int(hds.get("X-Height"))
    check("full sizes match config", w == CONFIG["width"] and hh == CONFIG["height"])
    arr = np.frombuffer(raw, "<f4").reshape(hh, w)
    s = status["stats"]
    check("full stats match data",
          abs(s["min"] - float(arr.min())) < 1e-6
          and abs(s["max"] - float(arr.max())) < 1e-6
          and abs(s["land_frac"] - float((arr > CONFIG["sea_level"]).mean())) < 1e-6)
    check("stride decimation", w * hh * 4 == len(raw))

    print("== exports ==")
    st, hds, raw = req(f"/api/export/{jid}?format=png16&sea_mode=keep")
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    check("png16 mode/size", st == 200 and img.mode in ("I;16", "I") and img.size == (w, hh))
    parr = np.array(img).astype(np.float64)
    check("png16 values exact", int(np.abs(parr - np.round(np.clip(arr, 0, 1) * 65535)).max()) <= 1)
    check("png16 filename", "png16" in (hds.get("Content-Disposition") or ""))

    st, hds, raw = req(f"/api/export/{jid}?format=raw16&sea_mode=keep")
    check("raw size", st == 200 and len(raw) == w * hh * 2)
    ra = np.frombuffer(raw, "<u2").astype(np.float64).reshape(hh, w)
    check("raw values match", int(np.abs(ra - np.round(np.clip(arr, 0, 1) * 65535)).max()) <= 1)

    st, hds, raw = req(f"/api/export/{jid}?format=exr&sea_mode=keep")
    check("exr magic", st == 200 and raw[:4] == b"v/1\x01")
    import OpenEXR
    exr = OpenEXR.File(io.BytesIO(raw), separate_channels=True)
    back = np.asarray(exr.parts[0].channels["Y"].pixels)
    check("exr read by official lib, exact values",
          back.shape == (hh, w) and float(np.abs(back - arr).max()) == 0.0)

    st, _, raw = req(f"/api/export/{jid}?format=bogus&sea_mode=keep")
    check("bad format rejected", st == 400)
    st, _, raw = req(f"/api/export/{jid}?format=png16&sea_mode=bogus")
    check("bad sea_mode rejected", st == 400)

    # sea modes
    st, _, raw = req(f"/api/export/{jid}?format=raw16&sea_mode=flatten")
    fa = np.frombuffer(raw, "<u2").astype(np.float64).reshape(hh, w) / 65535.0
    check("flatten: underwater -> 0",
          float(fa[arr < CONFIG["sea_level"]].max()) == 0.0 if (arr < CONFIG["sea_level"]).any() else True)
    check("flatten: land unchanged",
          float(np.abs(fa[arr >= CONFIG["sea_level"]] - arr[arr >= CONFIG["sea_level"]]).max()) < 1e-3)
    st, _, raw = req(f"/api/export/{jid}?format=raw16&sea_mode=remap")
    ma = np.frombuffer(raw, "<u2").astype(np.float64).reshape(hh, w) / 65535.0
    check("remap: land spread to full range", float(ma.max()) > 0.995 and float(ma.min()) == 0.0)
    check("remap: underwater flattened", float(ma[arr < CONFIG["sea_level"]].max()) == 0.0
          if (arr < CONFIG["sea_level"]).any() else True)

    print("== landscape mode ==")
    cfg_land = dict(CONFIG, mode="landscape", sea_level=0.0, islands=[])
    st, _, raw = req("/api/preview", {"config": cfg_land}, timeout=240)
    pl = json.loads(raw)
    check("landscape preview ok", st == 200 and pl["status"] == "done", str(pl))
    st, hds, raw = req(f"/api/heights/{pl['id']}")
    w2, h2 = int(hds.get("X-Width")), int(hds.get("X-Height"))
    la = np.frombuffer(raw, "<f4").reshape(h2, w2)
    check("landscape terrain runs off edges",
          float(max(la[0].max(), la[-1].max(), la[:, 0].max(), la[:, -1].max())) > 0.2)
    check("landscape range sane", float(la.min()) >= 0 and float(la.max()) <= 1.0001)

    st, _, raw = req("/api/preview", {"config": dict(CONFIG, mode="bogus")}, timeout=240)
    pb2 = json.loads(raw)
    check("bad mode falls back to islands", pb2["status"] == "done")

    print("== error handling ==")
    st, _, _ = req("/api/heights/deadbeef")
    check("missing status 404", st == 404)
    st, _, _ = req("/api/export/deadbeef?format=png16")
    check("missing export 404", st == 404)
    st, _, _ = req("/api/status/deadbeef")
    check("missing status endpoint 404", st == 404)

    # clamped config runs (huge sea, negative radius, etc.)
    bad = {"width": 10, "height": 10, "seed": -5, "sea_level": 9.0,
           "islands": [{"cx": "x", "radius": -3, "angle": "zzz"}],
           "noise": {"scale": "abc"}, "erosion": {"droplets": -100}}
    st, _, raw = req("/api/preview", {"config": bad}, timeout=120)
    pc = json.loads(raw)
    check("clamped preview runs", st == 200 and pc["status"] == "done", str(pc))

    print(f"\n{CHECKS[0]} passed, {CHECKS[1] - CHECKS[0]} failed")
    return 0 if CHECKS[0] == CHECKS[1] else 1


if __name__ == "__main__":
    sys.exit(main())
