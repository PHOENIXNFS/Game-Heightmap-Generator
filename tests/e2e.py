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
    {"cx": 0.32, "cy": 0.35, "radius": 0.26, "angle": 0.7, "land_height": 0.30},
    {"cx": 0.62, "cy": 0.58, "radius": 0.22, "angle": 2.1, "land_height": 0.30},
    {"cx": 0.82, "cy": 0.22, "radius": 0.11, "angle": 5.0, "land_height": 0.30},
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
    check("full-res dropdown present",
          b'id="full-res"' in raw and b'id="preview-res"' in raw
          and b'id="custom-w"' in raw and b'id="custom-h"' in raw)
    check("landscape panel present",
          b'id="landscape-panel"' in raw
          and all((b'id="' + k + b'"') in raw for k in
                  (b"land-height", b"land-peak", b"land-cover", b"land-msize")))
    for asset in ("/style.css", "/app.js", "/preview2d.js", "/preview3d.js"):
        st, _, raw = req(asset)
        check(f"{asset} served", st == 200 and len(raw) > 500)
    st, _, raw = req("/api/defaults")
    defaults = json.loads(raw)
    isl0 = defaults["config"]["islands"][0] if defaults.get("config", {}).get("islands") else {}
    check("defaults", st == 200 and "config" in defaults and "islands" in defaults["config"])
    check("defaults island angle is a number", isinstance(isl0.get("angle"), (int, float)))
    check("defaults island has its own seed", isinstance(isl0.get("seed"), int) and isl0["seed"] >= 0)
    check("defaults island has elevation fields",
          all(isinstance(isl0.get(k), (int, float))
              for k in ("land_height", "mountain_height", "mountain_coverage")))
    check("defaults island has its own shape variety",
          isinstance(isl0.get("shape_variety"), (int, float)))
    check("defaults island has its own coast slope",
          isinstance(isl0.get("coast_slope"), (int, float)))
    # The central defaults file must be exactly what the server serves:
    # defaults.json is the single source of truth for the whole tool.
    central = json.loads(
        (Path(__file__).resolve().parent.parent / "defaults.json").read_text(encoding="utf-8"))
    served = defaults["config"]
    scalars_ok = all(served.get(k) == v for k, v in central.items()
                     if not isinstance(v, (dict, list)))
    blocks_ok = all(served.get(k) == v for k, v in central.items() if isinstance(v, dict))
    island_ok = all(served["islands"][0].get(k) == v
                    for k, v in central["islands"][0].items() if v is not None)
    check("defaults.json drives /api/defaults",
          scalars_ok and blocks_ok and island_ok,
          f"scalars {scalars_ok} blocks {blocks_ok} island {island_ok}")
    check("defaults has no elevation field", "elevation" not in isl0)
    dc = defaults["config"]
    check("defaults smoothing block", isinstance(dc.get("smoothing"), dict)
          and all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0
                  for v in dc["smoothing"].values()))
    check("defaults landscape block", isinstance(dc.get("landscape"), dict)
          and all(isinstance(dc["landscape"].get(k), (int, float))
                  for k in ("land_height", "mountain_height",
                            "mountain_coverage", "mountain_size")))
    st, _, raw = req("/api/preview", {"config": {"smoothing": "junk"}}, timeout=120)
    check("malformed smoothing no crash", st == 200 and json.loads(raw)["status"] == "done")

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

    st, _, _ = req("/api/preview?size=2048", {"config": CONFIG}, timeout=240)
    check("preview capped at 1024", st == 422, f"status {st}")

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

    # per-island seeds: rerolling one island must not touch the others
    def preview_arr(cfg):
        st_, _, r_ = req("/api/preview", {"config": cfg}, timeout=240)
        p_ = json.loads(r_)
        st_, hd, data = req(f"/api/heights/{p_['id']}")
        w_, h_ = int(hd.get("X-Width")), int(hd.get("X-Height"))
        return np.frombuffer(data, "<f4").reshape(h_, w_)

    no_post = {"thermal": 0.0, "blur": 0.0}
    no_ero = {"enabled": False, "droplets": 0, "max_steps": 0}
    pair_a = [dict(ISLANDS[0], seed=1111), dict(ISLANDS[1], seed=2222)]
    pair_b = [dict(ISLANDS[0], seed=9999), dict(ISLANDS[1], seed=2222)]
    ia = preview_arr(dict(CONFIG, islands=pair_a, smoothing=no_post, erosion=no_ero))
    ib = preview_arr(dict(CONFIG, islands=pair_b, smoothing=no_post, erosion=no_ero))
    delta = np.abs(ia - ib)
    # island 2 (cx 0.62 -> x >= 313 px) sits beyond island 1's compute box (x < 343)
    far = (slice(200, 350), slice(350, 424))
    check("rerolling island 1 leaves island 2 identical", float(delta[far].max()) == 0.0)
    check("rerolling island 1 changes island 1", float(delta.max()) > 1e-4)
    ig = preview_arr(dict(CONFIG, islands=pair_a, seed=4321,
                          smoothing=no_post, erosion=no_ero))
    check("islands ignore the global seed", bool(np.array_equal(ig, ia)))

    # erosion is a whole-map pass: it folds the island seeds together
    from core.generate import post_seed
    ea = post_seed({"mode": "islands", "seed": 1, "islands": pair_a})
    eb = post_seed({"mode": "islands", "seed": 1, "islands": pair_b})
    check("erosion seed folds island seeds", isinstance(ea, int) and ea != eb)
    check("landscape still uses the global seed",
          post_seed({"mode": "landscape", "seed": 4321, "islands": []}) == 4321)
    # ...so the hidden global seed must not move an islands-mode render
    g1 = preview_arr(dict(CONFIG, islands=pair_a))
    g2 = preview_arr(dict(CONFIG, islands=pair_a, seed=4321))
    check("global seed ignored with erosion on", bool(np.array_equal(g1, g2)))
    # ...but islands saved without a seed still fall back to it
    legacy0 = preview_arr(CONFIG)
    legacy1 = preview_arr(dict(CONFIG, seed=4321))
    check("seedless islands fall back to the global seed",
          not np.array_equal(legacy0, legacy1))
    # same coords must sample identically (sample == rows)
    from core.noise import fbm
    xs = np.arange(64, 128, dtype=np.float64)[None, :] * np.ones((64, 1))
    ys = np.arange(64, 128, dtype=np.float64)[:, None] * np.ones((1, 64))
    check("fbm deterministic", float(np.abs(fbm(xs, ys, 4242) - fbm(xs, ys, 4242)).max()) == 0.0)

    # coast slider: 0 = sharp drop at the waterline, 1 = gentle slope,
    # and each island carries its own.
    def shore_p50(arr, sea):
        min_dim = float(min(arr.shape))
        gy, gx = np.gradient(arr.astype(np.float64))
        g = np.hypot(gx, gy) * min_dim
        land = arr > sea

        def dil(m):
            o = m.copy()
            o[1:, :] |= m[:-1, :]
            o[:-1, :] |= m[1:, :]
            o[:, 1:] |= m[:, :-1]
            o[:, :-1] |= m[:, 1:]
            return o

        ring = dil(land) & dil(~land)
        vals = g[ring & land]
        return float(np.median(vals)) if vals.size else 0.0

    sea = CONFIG["sea_level"]
    g_sharp = shore_p50(preview_arr(dict(
        CONFIG, islands=[dict(ISLANDS[0], coast_slope=0.0)],
        smoothing=no_post, erosion=no_ero)), sea)
    g_slope = shore_p50(preview_arr(dict(
        CONFIG, islands=[dict(ISLANDS[0], coast_slope=1.0)],
        smoothing=no_post, erosion=no_ero)), sea)
    check("coast slider: slope is gentler than sharp",
          g_slope < g_sharp * 0.75, f"sharp {g_sharp:.2f} -> slope {g_slope:.2f}")

    # same map, two settings: island 0 sharp, island 1 gentle
    mixed = preview_arr(dict(
        CONFIG,
        islands=[dict(ISLANDS[0], coast_slope=0.0),
                 dict(ISLANDS[1], coast_slope=1.0),
                 dict(ISLANDS[2], coast_slope=1.0)],
        smoothing=no_post, erosion=no_ero))
    box_a = (slice(80, 300), slice(60, 250))
    box_b = (slice(220, 400), slice(280, 470))  # island 1 only: island 0's
    # compute box ends at x 256, so this region is untouched by it
    check("one map, sharp island and gentle island coexist",
          shore_p50(mixed[box_a[0], box_a[1]], sea)
          > 2.0 * shore_p50(mixed[box_b[0], box_b[1]], sea),
          f"A {shore_p50(mixed[box_a[0], box_a[1]], sea):.2f} "
          f"B {shore_p50(mixed[box_b[0], box_b[1]], sea):.2f}")

    # changing island 0's coast must not touch island 1
    other = preview_arr(dict(
        CONFIG,
        islands=[dict(ISLANDS[0], coast_slope=1.0),
                 dict(ISLANDS[1], coast_slope=1.0),
                 dict(ISLANDS[2], coast_slope=1.0)],
        smoothing=no_post, erosion=no_ero))
    check("coast slider is per island (neighbour untouched)",
          float(np.abs(mixed[box_b[0], box_b[1]]
                       - other[box_b[0], box_b[1]]).max()) == 0.0)
    check("coast slider changes its own island",
          float(np.abs(mixed[box_a[0], box_a[1]]
                       - other[box_a[0], box_a[1]]).max()) > 1e-4)

    # shape variety: 0 = round footprint, 1 = strongly lobed — and it too
    # belongs to the island it sits on.
    def radius_cv(arr, sea_, cx, cy, rad):
        land = arr > sea_
        ys, xs = np.nonzero(land)
        dx = xs - cx * arr.shape[1]
        dy = ys - cy * arr.shape[0]
        keep = dx * dx + dy * dy <= (rad * min(arr.shape) * 2.2) ** 2
        th = np.arctan2(dy[keep], dx[keep])
        r = np.hypot(dx[keep], dy[keep])
        bins = np.linspace(-np.pi, np.pi, 33)
        idx = np.clip(np.digitize(th, bins) - 1, 0, 31)
        prof = np.array([r[idx == b].max() if (idx == b).any() else 0.0
                         for b in range(32)])
        nz = prof[prof > 0]
        if nz.size < 24:
            return 0.0
        prof[prof == 0] = nz.mean()
        prof = prof / prof.mean()
        return float(prof.std())

    no_roll = {**CONFIG["noise"], "detail_amp": 0.0}
    isl = dict(ISLANDS[0], mountain_height=0.0, mountain_coverage=0.0)
    cv_round = radius_cv(preview_arr(dict(
        CONFIG, noise=no_roll, islands=[dict(isl, shape_variety=0.0)],
        smoothing=no_post, erosion=no_ero)), sea,
        isl["cx"], isl["cy"], isl["radius"])
    cv_lobed = radius_cv(preview_arr(dict(
        CONFIG, noise=no_roll, islands=[dict(isl, shape_variety=1.0)],
        smoothing=no_post, erosion=no_ero)), sea,
        isl["cx"], isl["cy"], isl["radius"])
    check("shape variety: 0 is round, 1 is lobed",
          cv_lobed > cv_round * 1.15, f"cv {cv_round:.3f} -> {cv_lobed:.3f}")

    # two islands far apart: editing one's shape must not move the other
    far_pair = [dict(ISLANDS[0], cx=0.16, cy=0.50, radius=0.16, shape_variety=0.0),
                dict(ISLANDS[1], cx=0.84, cy=0.50, radius=0.16, shape_variety=1.0)]
    va = preview_arr(dict(CONFIG, islands=far_pair,
                          smoothing=no_post, erosion=no_ero))
    vb = preview_arr(dict(CONFIG,
                          islands=[dict(far_pair[0], shape_variety=1.0), far_pair[1]],
                          smoothing=no_post, erosion=no_ero))
    box_b = (slice(180, 330), slice(350, 480))
    box_a = (slice(180, 330), slice(25, 160))
    check("shape variety is per island (neighbour untouched)",
          float(np.abs(va[box_b] - vb[box_b]).max()) == 0.0)
    check("shape variety changes its own island",
          float(np.abs(va[box_a] - vb[box_a]).max()) > 1e-4)

    print("== shape / terrain seeds ==")
    st, _, appjs = req("/app.js")
    check("island card has separate shape + terrain seed controls",
          st == 200 and b"isl-shape-seed" in appjs and b"isl-terrain-seed" in appjs)
    st, _, raw = req("/api/defaults")
    d0 = json.loads(raw)["config"]["islands"][0]
    check("defaults expose shape + terrain seeds",
          isinstance(d0.get("shape_seed"), int) and isinstance(d0.get("terrain_seed"), int)
          and d0["shape_seed"] >= 0 and d0["terrain_seed"] >= 0)

    # An island that omits the split seeds must render exactly like one
    # carrying seed/seed explicitly — that is every pre-split config's path.
    no_ripple = {**CONFIG["noise"], "detail_amp": 0.0}
    flat_isl = dict(ISLANDS[0], seed=4242, mountain_height=0.0, mountain_coverage=0.0)
    a = preview_arr(dict(CONFIG, noise=no_ripple, islands=[flat_isl],
                         smoothing=no_post, erosion=no_ero))
    b = preview_arr(dict(CONFIG, noise=no_ripple,
                         islands=[dict(flat_isl, shape_seed=4242, terrain_seed=4242)],
                         smoothing=no_post, erosion=no_ero))
    check("split seeds fall back to the island seed", bool(np.array_equal(a, b)))

    # Lock: with no mountains and no relief the coast is drawn entirely from
    # the shape seed, so rerolling terrain must not move a single pixel.
    at = preview_arr(dict(CONFIG, noise=no_ripple,
                          islands=[dict(flat_isl, terrain_seed=998877)],
                          smoothing=no_post, erosion=no_ero))
    check("terrain reroll keeps a flat island's coast bit-identical",
          bool(np.array_equal(a, at)))
    as_ = preview_arr(dict(CONFIG, noise=no_ripple,
                           islands=[dict(flat_isl, shape_seed=998877)],
                           smoothing=no_post, erosion=no_ero))
    check("shape reroll changes the outline",
          float(np.abs(a - as_).max()) > 1e-4)

    # On a real island the terrain seed must actually drive the surface...
    r0 = preview_arr(dict(CONFIG, islands=[ISLANDS[0]],
                          smoothing=no_post, erosion=no_ero))
    r1 = preview_arr(dict(CONFIG, islands=[dict(ISLANDS[0], terrain_seed=1234)],
                          smoothing=no_post, erosion=no_ero))
    r2 = preview_arr(dict(CONFIG, islands=[dict(ISLANDS[0], terrain_seed=7777)],
                          smoothing=no_post, erosion=no_ero))
    check("terrain reroll reshapes a mountainous island",
          float(np.abs(r1 - r2).max()) > 1e-4)
    # ...while the outline it sits on stays put: a terrain-only reroll must
    # disturb far less of the waterline than a shape-only one.
    rs = preview_arr(dict(CONFIG, islands=[dict(ISLANDS[0], shape_seed=4321)],
                          smoothing=no_post, erosion=no_ero))
    land0, landt, lands = (r0 > sea), (r1 > sea), (rs > sea)
    xor_terr = float(np.logical_xor(land0, landt).mean())
    xor_shape = float(np.logical_xor(land0, lands).mean())
    check("shape reroll moves the waterline far more than terrain reroll",
          xor_shape > 2.0 * xor_terr,
          f"shape {xor_shape:.5f} vs terrain {xor_terr:.5f}")

    print("== flat land + sparse mountains ==")

    def land_stats(**overrides):
        cfg = dict(CONFIG, smoothing=no_post, erosion=no_ero)
        cfg.update(overrides)
        arr = preview_arr(cfg)
        land = arr[arr > cfg.get("sea_level", CONFIG["sea_level"])]
        if land.size == 0:
            return 0.0, 0.0, 0.0
        return (float(land.size) / arr.size,
                float((land > 0.45).mean()),
                float(land.max()))

    isl1 = ISLANDS[0]
    # plain: with no mountains and no ripple the lowland sits at land_height
    flat = preview_arr(dict(CONFIG, smoothing=no_post, erosion=no_ero,
                            noise={**CONFIG["noise"], "detail_amp": 0.0},
                            islands=[dict(isl1, mountain_height=0.0,
                                          mountain_coverage=0.0)]))
    flat_land = flat[flat > CONFIG["sea_level"]]
    on_plain = (float((np.abs(flat_land - isl1["land_height"]) < 1e-3).mean())
                if flat_land.size else 0.0)
    check("lowland is flat (no mountains, no ripple)", on_plain >= 0.6,
          f"{on_plain:.2f} of land on the plain")

    # default map: high ground is a minority of the land, not a dome
    frac_def, hi_def, max_def = land_stats()
    check("mountains are localized", 0.005 < hi_def < 0.45,
          f"land {frac_def:.3f}, high {hi_def:.3f}")
    check("peaks rise well above the plain", max_def > isl1["land_height"] + 0.15,
          f"max {max_def:.3f}")

    # coverage: more of the island clears the mountain threshold
    _, hi_sparse, _ = land_stats(islands=[dict(isl1, mountain_coverage=0.15)])
    _, hi_dense, _ = land_stats(islands=[dict(isl1, mountain_coverage=0.60)])
    check("coverage widens high ground", hi_dense > hi_sparse,
          f"0.15 -> {hi_sparse:.3f}, 0.60 -> {hi_dense:.3f}")

    # peak height: taller mountains, same footprint
    _, _, max_low = land_stats(islands=[dict(isl1, mountain_height=0.05)])
    _, _, max_tall = land_stats(islands=[dict(isl1, mountain_height=0.55)])
    check("mountain height raises peaks", max_tall > max_low + 0.2,
          f"{max_low:.3f} -> {max_tall:.3f}")

    # absolute heights: water above the plain drowns it
    flooded, _, _ = land_stats(sea_level=0.7,
                               islands=[dict(isl1, mountain_height=0.0,
                                             mountain_coverage=0.0)])
    check("sea level above the plain floods it", flooded == 0.0, f"land {flooded}")

    # the plain rolls and falls toward the coast instead of being a plate
    rolled = preview_arr(dict(CONFIG, smoothing=no_post, erosion=no_ero,
                              islands=[dict(isl1, mountain_height=0.0,
                                            mountain_coverage=0.0)]))
    rh, rw = rolled.shape
    gy, gx = np.mgrid[0:rh, 0:rw]
    rr = np.hypot(gx - isl1["cx"] * rw, gy - isl1["cy"] * rh)
    rr /= isl1["radius"] * min(rw, rh)
    rland = rolled > CONFIG["sea_level"]
    # mid-slope vs the outermost plain: the very centre is not compared
    # because the rolling noise can put a hollow there
    mid = rland & (rr > 0.30) & (rr < 0.55)
    outer = rland & (rr > 0.75) & (rr < 0.88)
    d_in = float(rolled[mid].mean()) if mid.any() else 0.0
    d_out = float(rolled[outer].mean()) if outer.any() else 0.0
    check("plain falls gently toward the coast", d_in > d_out + 0.005,
          f"mid {d_in:.3f} -> outer {d_out:.3f}")
    check("plain still reads flat", abs(d_out - isl1["land_height"]) < 0.30 * isl1["land_height"],
          f"outer {d_out:.3f} vs plain {isl1['land_height']:.3f}")

    # mountain size: same coverage and peak height, broader massifs.
    # Averaged over a few seeds: with one huge massif a single island
    # may sit mostly on a flank, so one seed is not representative.
    def patch_stats(size, seed):
        arr = preview_arr(dict(CONFIG, seed=seed, smoothing=no_post,
                               erosion=no_ero,
                               islands=[dict(isl1, mountain_coverage=0.30,
                                             mountain_size=size)]))
        land = arr > CONFIG["sea_level"]
        high = arr > isl1["land_height"] + 0.10
        per = sum(int((high != np.roll(high, s, ax)).sum())
                  for s, ax in ((1, 0), (-1, 0), (1, 1), (-1, 1)))
        return (per / max(int(high.sum()), 1),
                float(high.sum()) / max(int(land.sum()), 1),
                float(arr.max()))

    def mean_stats(size):
        rows = np.array([patch_stats(size, s) for s in (1000, 1001, 1002)])
        return tuple(float(v) for v in rows.mean(axis=0))

    r_small, f_small, m_small = mean_stats(0.6)
    r_big, f_big, m_big = mean_stats(2.0)
    check("mountain size makes broader massifs", r_big < r_small * 0.7,
          f"perimeter/area {r_small:.3f} -> {r_big:.3f}")
    check("mountain size keeps coverage and peak height",
          abs(f_big - f_small) < 0.06 and abs(m_big - m_small) < 0.08,
          f"high {f_small:.3f} -> {f_big:.3f}, max {m_small:.3f} -> {m_big:.3f}")


    base_cfg = dict(CONFIG)
    base_cfg["erosion"] = {"enabled": False, "droplets": 0, "max_steps": 0}

    def preview_for(cfg, timeout=240):
        st, _, raw = req("/api/preview", {"config": cfg}, timeout=timeout)
        p = json.loads(raw)
        st, hds, data = req(f"/api/heights/{p['id']}")
        w, hh = int(hds.get("X-Width")), int(hds.get("X-Height"))
        return np.frombuffer(data, "<f4").reshape(hh, w), p

    def ridge_metric(a):
        c = a[1:-1, 1:-1]
        lap = np.abs(a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4.0 * c)
        land = c > CONFIG["sea_level"]
        return float(lap[land].mean()) if land.any() else 0.0

    cfg_off = dict(base_cfg, smoothing={"thermal": 0.0, "blur": 0.0})
    cfg_on = dict(base_cfg, smoothing={"thermal": 0.5, "blur": 0.5})
    ao, po = preview_for(cfg_off)
    an, pn = preview_for(cfg_on)
    check("preview with smoothing", pn["status"] == "done")
    mo, mn = ridge_metric(ao), ridge_metric(an)
    check("smoothing lowers ridge metric", mn < mo * 0.9, f"off={mo:.5f} on={mn:.5f}")
    check("borders ocean with smoothing",
          float(max(an[0].max(), an[-1].max(), an[:, 0].max(), an[:, -1].max())) < 1e-6)

    cfg_p = dict(base_cfg, smoothing={"thermal": 0.0, "blur": 0.0},
                 noise={**base_cfg["noise"], "persistence": 0.2})
    ap_, _ = preview_for(cfg_p)
    check("persistence changes shape", not np.array_equal(ap_, ao))

    cfg_o = dict(base_cfg, smoothing={"thermal": 0.0, "blur": 0.0},
                 noise={**base_cfg["noise"], "octaves": 99})
    cfg_t = dict(base_cfg, smoothing={"thermal": 0.0, "blur": 0.0},
                 noise={**base_cfg["noise"], "octaves": 10})
    at2, _ = preview_for(cfg_o)
    at10, _ = preview_for(cfg_t)
    check("octaves clamped (99 == 10)", np.array_equal(at2, at10))

    print("== coastline realism ==")

    # Coastline fractal dimension from boundary crossings at k=1,2,4,8.
    # A smooth ellipse scores ~1.0; this coast must keep fine crenulation.
    def coast_dim(arr, sea):
        def boundary(m):
            e = m.astype(np.int8)
            return int((e[:, 1:] != e[:, :-1]).sum() + (e[1:, :] != e[:-1, :]).sum())
        land = arr > sea
        ks = np.array([1.0, 2.0, 4.0, 8.0])
        L = np.array([boundary(land[::int(k), ::int(k)]) for k in ks])
        return float(-np.polyfit(np.log(ks), np.log(L), 1)[0])

    coast_cfg = dict(base_cfg, width=505, height=505,
                     smoothing={"thermal": 0.0, "blur": 0.0},
                     erosion={"enabled": False, "droplets": 0, "max_steps": 0},
                     islands=[dict(ISLANDS[0], radius=0.30, angle=0.27,
                                   land_height=0.30, mountain_height=0.0,
                                   mountain_coverage=0.0)])
    coast_arr, _ = preview_for(coast_cfg)
    d_coast = coast_dim(coast_arr, base_cfg["sea_level"])
    check("coastline is fractal (not a smooth ellipse)", d_coast > 1.05,
          f"D={d_coast:.3f}")
    coast_sm, _ = preview_for(dict(coast_cfg,
                                   smoothing={"thermal": 0.5, "blur": 0.5}))
    d_sm = coast_dim(coast_sm, base_cfg["sea_level"])
    check("coast stays crenellated after smoothing", d_sm > 1.01,
          f"D={d_sm:.3f}")

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

    print("== high resolution smoke (2k / 4k) ==")
    t0 = time.time()
    st, _, raw = req("/api/generate", {"config": dict(CONFIG, width=2017, height=2017)}, timeout=600)
    gen = json.loads(raw)
    check("2k generate queued", st == 200 and "id" in gen)
    jid2 = gen["id"]
    status2 = None
    t2 = time.time()
    while True:
        st, _, raw = req(f"/api/status/{jid2}")
        status2 = json.loads(raw)
        if status2["status"] in ("done", "error"):
            break
        time.sleep(0.5)
        if time.time() - t2 > 540:
            break
    print(f"       2k full gen took {time.time() - t2:.1f}s (job ms={status2['ms']})")
    check("2k full done", status2["status"] == "done", str(status2))
    if status2["status"] == "done":
        st, hds, raw2k = req(f"/api/heights/{jid2}")
        w2, h2 = int(hds.get("X-Width")), int(hds.get("X-Height"))
        a2k = np.frombuffer(raw2k, "<f4").reshape(h2, w2)
        check("2k sizes match config", w2 == 2017 and h2 == 2017)
        check("2k borders ocean",
              float(max(a2k[0].max(), a2k[-1].max(), a2k[:, 0].max(), a2k[:, -1].max())) < 1e-6)
        check("2k range sane", float(a2k.min()) >= 0 and float(a2k.max()) <= 1.0001)

    cfg_4k = dict(CONFIG, width=4033, height=4033,
                  erosion={"enabled": False, "droplets": 0, "max_steps": 0})
    t0 = time.time()
    st, _, raw = req("/api/generate", {"config": cfg_4k}, timeout=600)
    gen = json.loads(raw)
    check("4k generate queued (erosion off)", st == 200 and "id" in gen)
    jid4 = gen["id"]
    status4 = None
    t4 = time.time()
    while True:
        st, _, raw = req(f"/api/status/{jid4}")
        status4 = json.loads(raw)
        if status4["status"] in ("done", "error"):
            break
        time.sleep(0.5)
        if time.time() - t4 > 540:
            break
    print(f"       4k full gen took {time.time() - t4:.1f}s (job ms={status4['ms']})")
    check("4k full done (erosion off)", status4["status"] == "done", str(status4))
    if status4["status"] == "done":
        st, hds, raw4k = req(f"/api/heights/{jid4}")
        w4, h4 = int(hds.get("X-Width")), int(hds.get("X-Height"))
        a4k = np.frombuffer(raw4k, "<f4").reshape(h4, w4)
        check("4k sizes match config", w4 == 4033 and h4 == 4033)
        check("4k borders ocean",
              float(max(a4k[0].max(), a4k[-1].max(), a4k[:, 0].max(), a4k[:, -1].max())) < 1e-6)
        check("4k range sane", float(a4k.min()) >= 0 and float(a4k.max()) <= 1.0001)

    print("== exports ==")
    st, hds, raw = req(f"/api/export/{jid}?format=png16&sea_mode=keep")
    from PIL import Image
    # Report a non-PNG body instead of dying inside PIL: a 404/500 body
    # here is a server bug worth seeing, not a test crash.
    is_png = st == 200 and raw[:8] == b"\x89PNG\r\n\x1a\n"
    check("png16 response is a png", is_png,
          f"status {st} body {raw[:160]!r}")
    img = Image.open(io.BytesIO(raw)) if is_png else None
    check("png16 mode/size",
          img is not None and img.mode in ("I;16", "I") and img.size == (w, hh))
    want = np.round(np.clip(arr, 0, 1) * 65535)
    check("png16 values exact",
          img is not None and int(np.abs(np.array(img).astype(np.float64) - want).max()) <= 1)
    check("png16 filename", ".png" in (hds.get("Content-Disposition") or "")
          and "hmg_" in (hds.get("Content-Disposition") or ""))

    st, hds, raw = req(f"/api/export/{jid}?format=raw16&sea_mode=keep")
    check("raw size", st == 200 and len(raw) == w * hh * 2)
    check("raw16 filename", ".raw" in (hds.get("Content-Disposition") or ""))
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

    print("== masks ==")
    st, hds, raw = req(f"/api/masks/{jid}?kind=water")
    check("water mask png", st == 200 and raw[:8] == b"\x89PNG\r\n\x1a\n", f"status {st}")
    wm = Image.open(io.BytesIO(raw))
    check("water mask 8-bit at full size",
          wm.mode == "L" and wm.size == (w, hh), f"{wm.mode} {wm.size}")
    wmask = np.array(wm) > 127
    check("water mask matches sea level",
          bool(np.array_equal(wmask, arr < CONFIG["sea_level"])))
    check("water mask filename", "water" in (hds.get("Content-Disposition") or ""))

    st, hds, raw = req(f"/api/masks/{jid}?kind=slope&steepness=0.5")
    check("slope mask png", st == 200 and raw[:8] == b"\x89PNG\r\n\x1a\n", f"status {st}")
    sm = Image.open(io.BytesIO(raw))
    check("slope mask 8-bit at full size",
          sm.mode == "L" and sm.size == (w, hh), f"{sm.mode} {sm.size}")
    loose = np.array(sm) > 127
    st, _, raw = req(f"/api/masks/{jid}?kind=slope&steepness=1.0")
    tight = np.array(Image.open(io.BytesIO(raw))) > 127
    check("slope mask steepness shrinks rock",
          st == 200 and int(tight.sum()) < int(loose.sum()),
          f"{int(tight.sum())} vs {int(loose.sum())}")
    check("slope mask only on land", not bool(loose[arr < CONFIG["sea_level"]].any()))

    st, _, _ = req(f"/api/masks/{jid}?kind=bogus")
    check("bad mask kind rejected", st == 400)
    st, _, _ = req("/api/masks/deadbeef?kind=water")
    check("missing mask job 404", st == 404)

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
    # sea_level is deliberately non-zero here: landscape has no sea, so the
    # pipeline must ignore it (an inland tile has no water line at all).
    cfg_land = dict(CONFIG, mode="landscape", sea_level=0.15, islands=[])
    st, _, raw = req("/api/preview", {"config": cfg_land}, timeout=240)
    pl = json.loads(raw)
    check("landscape preview ok", st == 200 and pl["status"] == "done", str(pl))
    st, hds, raw = req(f"/api/heights/{pl['id']}")
    w2, h2 = int(hds.get("X-Width")), int(hds.get("X-Height"))
    la = np.frombuffer(raw, "<f4").reshape(h2, w2)
    edges = np.concatenate([la[0], la[-1], la[:, 0], la[:, -1]])
    check("landscape terrain runs off edges",
          float(edges.min()) > 0.02 and float(edges.mean()) > 0.6 * float(la.mean()),
          f"edge min={edges.min():.3f} mean={edges.mean():.3f} map mean={la.mean():.3f}")
    check("landscape range sane", float(la.min()) >= 0 and float(la.max()) <= 1.0001)
    p50, p99 = np.percentile(la, [50, 99])
    check("landscape has lowland plus high ground",
          float(p50) < 0.2 and float(p99) > float(p50) + 0.1,
          f"p50={p50:.3f} p99={p99:.3f}")
    check("landscape ignores sea level",
          abs(float(pl["stats"]["land_frac"]) - 1.0) < 1e-6, str(pl.get("stats")))
    st, _, raw = req(f"/api/masks/{pl['id']}?kind=water")
    check("water mask refused in landscape", st == 400, str(raw[:120]))
    st, _, raw = req(f"/api/masks/{pl['id']}?kind=slope&steepness=0.5")
    check("slope mask works in landscape",
          st == 200 and raw[:8] == b"\x89PNG\r\n\x1a\n", f"status {st}")

    st, _, raw = req("/api/preview", {"config": dict(cfg_land, landscape={
        "land_height": 0.10, "mountain_height": 0.0,
        "mountain_coverage": 0.18, "mountain_size": 1.0})}, timeout=240)
    pf = json.loads(raw)
    check("landscape without mountains stays low",
          pf["status"] == "done" and float(pf["stats"]["max"]) < 0.2, str(pf.get("stats")))

    st, _, raw = req("/api/preview", {"config": dict(cfg_land, landscape={
        "land_height": 0.10, "mountain_height": 0.30,
        "mountain_coverage": 0.60, "mountain_size": 1.0})}, timeout=240)
    pc = json.loads(raw)
    check("landscape coverage raises high ground",
          float(pc["stats"]["mean"]) > float(pl["stats"]["mean"]),
          f"{pc['stats']['mean']:.3f} vs {pl['stats']['mean']:.3f}")

    st, _, raw = req("/api/preview", {"config": cfg_land}, timeout=240)
    pl2 = json.loads(raw)
    st, hds, raw = req(f"/api/heights/{pl2['id']}")
    lb = np.frombuffer(raw, "<f4").reshape(int(hds.get("X-Height")), int(hds.get("X-Width")))
    check("landscape deterministic", bool(np.array_equal(la, lb)))

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
