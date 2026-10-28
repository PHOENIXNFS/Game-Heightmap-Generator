# Terrain Heightmap Generator

Technical documentation for the Terrain Heightmap Generator (HMG).

| | |
| --- | --- |
| **Type** | Local web application (browser UI + HTTP API) |
| **Purpose** | Procedural generation and export of terrain heightmaps |
| **Backend** | Python 3, FastAPI, Uvicorn, NumPy |
| **Frontend** | Vanilla HTML/CSS/JS — 2D canvas + WebGL previews, no build step |
| **Output** | 16-bit PNG, raw 16-bit (`.raw`), OpenEXR (`.exr`), 8-bit mask PNGs |
| **License** | MIT ([LICENSE](LICENSE)) |

---

## 1. What it does

HMG generates a single-channel heightmap — a 2D grid of heights in the
normalized range `[0, 1]` — from a declarative JSON configuration. It is a
*deterministic* generator: the same configuration always produces the same
heightmap, because every random source is derived from explicit seeds.

Generation supports two mutually exclusive terrain models:

- **Islands** — any number of independent islands standing in a sea. Each
  island has its own footprint, coastline profile, elevation model, rotation
  and seed. Changing one island's parameters never affects another.
- **Landscape** — one continuous inland tile with no sea: a near-flat plain
  with mountain ranges rising out of it, running off all four map edges.

The pipeline composes the terrain from noise, then optionally applies
hydraulic erosion, thermal (talus) smoothing and a blur pass. Results are
rendered live in a 2D and a 3D preview, and exported at up to 8192 px in
formats that engines consume directly (Unreal, Unity, Godot, or any tool that
reads height data).

Everything runs on `127.0.0.1` — no accounts, no telemetry, no outbound
network calls.

---

## 2. Requirements and installation

- **Python 3.10+** (uses `X | None` type syntax)
- Dependencies are listed in [`requirements.txt`](requirements.txt):
  `numpy`, `fastapi`, `uvicorn`, `pillow`, `OpenEXR`

```bash
pip install -r requirements.txt
```

Or install the packages directly:

```bash
pip install numpy fastapi uvicorn pillow OpenEXR
```

## 3. Running the application

```bash
python start.py
```

On Windows, `server.bat` runs the same launcher and pauses so the console
stays open.

**start.py** is the environment bootstrap and port chooser:

1. Creates a local virtual environment in `terrain-venv/` on first run and installs
   [`requirements.txt`](requirements.txt) into it (it re-installs only when
   that file changes). The venv uses `--system-site-packages`, so packages
   you already have satisfy the requirements without a download.
2. Starts `server.py` **inside that environment**.
3. Picks the port:
   - `HMG_PORT` if you set it explicitly — that port is used as-is;
   - otherwise **8765 when it is free** (the default);
   - otherwise a **random free port**, so a second launch never disturbs an
     already-running session.
4. Prints the URL once `GET /api/health` answers, e.g.
   `Terrain Heightmap Generator — http://127.0.0.1:8765`

```bash
HMG_PORT=9000 python start.py   # force a specific port
```

`python server.py` still starts the server directly on 8765 (or `HMG_PORT`)
in the current interpreter — that path is what the test suite uses.

Interactive OpenAPI docs are served at the same origin under **/api/docs**
(default `http://127.0.0.1:8765/api/docs`). A health check is available at
`GET /api/health` → `{"ok": true}`.

---

## 4. Using the interface

The UI is one page: a control sidebar on the left, a 2D and a 3D preview pane
on the right, and a toolbar across the top. Previews regenerate automatically
as you change any control.

### 4.1 Toolbar

| Control | Function |
| --- | --- |
| **Seed** / ↻ | Global seed (0 – 2³¹−1) with a random-roll button. Shown in *Landscape* mode only; in *Islands* mode every island carries its own seed instead. |
| **Preview res** | Preview canvas size: 256 / 512 / 1024 px. |
| **Generate Full Res** | Renders the heightmap at the size set in **Full res**. Required before exporting. |
| **PNG16 / RAW r16 / EXR** | Export buttons; enabled only after a full-res render completes. |
| **Save / Load** | Downloads the configuration as `heightmap-config.json`, or reads one back (it is merged over the defaults, so partial files work). |

### 4.2 MAP panel

| Control | Range / values | Meaning |
| --- | --- | --- |
| **Mode** | `islands` \| `landscape` | Terrain model (see §1). |
| **Full res** | 512, 1024, 2048, 4096; Unreal presets 505, 1009, 1017, 2017, 4033; or **Custom…** with free W/H | Output resolution. Previews are unaffected. |
| **Sea level** | 0.000 – 1.000 (default 0.060) | The waterline. Terrain below it is ocean. Hidden in landscape mode, where the sea is forced to `0`. |

### 4.3 ISLANDS panel

Each island is a card holding its own copy of every per-island control. Click
a card to select it; the selected island is highlighted in the 2D preview.

| Control | Range | Meaning |
| --- | --- | --- |
| **Position / Radius / Aspect / Rotation** | — | Geometry. Also editable by dragging the island in the 2D preview (body = move, handles = resize, orange dot = rotate). |
| **Shape** | 0.00 – 1.00 | Footprint variety: `0` is a perfect circle, `1` a strongly lobed organic outline. |
| **Coast** | 0.00 – 1.00 | Shoreline profile: `0` is a sharp cliff-like drop at the waterline, `1` a long gentle slope into the sea. Does **not** change island size — the band is built around a fixed waterline. |
| **Plain height** | 0.02 – 0.60 | Absolute elevation of the island's flat lowland. |
| **Mountain height** | 0.00 – 0.60 | How far ranges rise above the plain (clamped so `land + peak ≤ 1`). |
| **Mountain coverage** | 0.00 – 1.00 | Share of the island that is high ground: `0` = flat atoll, `1` = mountains everywhere. |
| **Mountain size** | 0.60 – 2.00 | Breadth of a single massif: scattered hills → one large range. |
| **Shape seed** | 0 … 2³²−1 | Drives the outline: footprint harmonics, coast warp, shore band and default rotation. Lock it to keep a coastline you like. |
| **Terrain seed** | 0 … 2³²−1 | Drives the surface: plain relief and mountains (plus the erosion droplets). Reroll it to reshape the land under the same outline. |

Both default to the island's own seed, so a config saved before the split
renders exactly as it did before. A newly added island copies the tool's
default island from `defaults.json` — every slider starts at its default and
only the seeds are drawn at random. **+ add** appends an island; **↻ seeds**
rerolls every island's seed (both of them).

The shape seed also decides each island's *character* — its overall
lobedness and how fast its coastline harmonics decay — so two islands at the
same **Shape** value still read as different kinds of coast (broad bays vs.
a fringed rim).

### 4.4 TERRAIN NOISE panel

| Control | Range | `config.noise.*` |
| --- | --- | --- |
| Feature size | 0.5 – 20.0 | `scale` — base spatial frequency of the hills. |
| Terrain detail | 0.00 – 1.00 | `detail_amp` — amplitude of the fine detail. At `0` the lowland is exactly flat. |
| Coast roughness | 0.00 – 1.00 | `coast_warp` — how far the coastline warps in and out. Islands mode only. |
| Detail falloff | 0.05 – 0.95 | `persistence` — how quickly finer octaves fade. |
| Octaves | 1 – 10 | `octaves` — number of noise layers. |

### 4.5 SMOOTHING panel

| Control | Range | `config.smoothing.*` |
| --- | --- | --- |
| Thermal | 0.00 – 1.00 | `thermal` — talus slump: rounds sharp ridge crests into shoulders without moving the coastline. |
| Blur | 0.00 – 1.00 | `blur` — Gaussian pass that removes residual scratches. |

### 4.6 HYDRAULIC EROSION panel

| Control | Range | `config.erosion.*` |
| --- | --- | --- |
| enabled | checkbox | Toggles the droplet simulation. |
| Droplets | 0 – 400 000 (default 60 000) | Number of simulated raindrops. Calibrated for 1024×1024 and scaled internally by resolution. |
| Steps | 0 – 120 (default 30) | Path length of each droplet. |

The remaining erosion parameters (inertia, capacity, evaporation, gravity,
brush radius, …) are part of the configuration but not exposed in the UI —
set them via Save/Load JSON or the API. See §5.

### 4.7 MASKS panel

Companion 8-bit PNG masks at the full-resolution size, downloadable after
**Generate Full Res**:

| Mask | Content |
| --- | --- |
| **Water mask** | `255` below sea level, `0` on land. Islands mode only — landscape mode has no water line and the API returns `400`. |
| **Slope mask** | `255` where the ground is steep enough to read as rock, with a feathered edge so it antialiases instead of speckling. |

**Steepness** (0.00 – 1.00) sets the threshold. It is expressed in percentiles
of the map's own land gradient — `0` marks the 55th percentile, `1` the 98th —
so higher means *less* rock, and the same slider behaves consistently at any
resolution without needing world units.

### 4.8 STATS panel

Live statistics for the current preview: `min`, `max`, `mean` height and
`land %` (fraction of pixels above sea level), plus the render time in ms.

### 4.9 Previews

- **2D pane** — top-down render with island overlays: drag the body to move,
  a handle to resize, the orange dot to rotate, double-click anywhere on the
  map to add an island (islands mode).
- **3D pane** — WebGL heightmap mesh. Left-drag orbits, wheel zooms,
  right-drag pans, double-click resets the view.

Both views use the same shading and the same rock threshold (derived from the
map's own 99th-percentile slope), so they always agree.

### 4.10 Typical workflow

1. Choose **Mode** and, in Islands mode, place and shape your islands.
2. Tune the elevation, noise, smoothing and erosion controls while watching
   the previews.
3. Set **Full res** to the target resolution (Unreal 2ⁿ+1 presets included).
4. Press **Generate Full Res**.
5. Export **PNG16**, **RAW r16** or **EXR**, and optionally the water/slope
   masks.
6. **Save** the configuration if you want to reproduce or tweak it later.

---

## 5. Configuration reference

Every default value for the tool lives in one file:
[`defaults.json`](defaults.json) at the project root. `core/generate.py`
loads it into `DEFAULT_CONFIG`, `GET /api/defaults` serves it, and the web UI
caches that response — so the backend, the API and the interface can never
drift apart. Edit `defaults.json` to change a default; nothing else holds a
copy of it.

The configuration is a single JSON object. `POST /api/preview` and
`POST /api/generate` accept it as `{"config": {...}}`. Every key is optional:
missing, malformed or out-of-range values are replaced or clamped by
`normalize_config()` in [core/generate.py](core/generate.py).

### 5.1 Top level

| Key | Type | Range | Default | Notes |
| --- | --- | --- | --- | --- |
| `width`, `height` | int | 64 – 8192 | 1024 | Output size. Previews are overridden to their own size (≤ 1024). |
| `seed` | int | 0 – 2³¹−1 | 1337 | Global seed (landscape mode + erosion). |
| `mode` | string | `islands` \| `landscape` | `islands` | Anything unrecognized falls back to `islands`. |
| `sea_level` | float | 0 – 1 | 0.06 | Forced to `0` in landscape mode. |
| `shape_variety` | float | 0 – 1 | 0.55 | Fallback only; each island carries its own `shape_variety`. |

### 5.2 `noise`

| Key | Range | Default | Notes |
| --- | --- | --- | --- |
| `scale` | 0.1 – 64.0 | 2.5 | Base noise frequency. |
| `octaves` | 1 – 10 (int) | 6 | Number of fractal layers. |
| `persistence` | 0.05 – 0.95 | 0.5 | Per-octave amplitude falloff. |
| `lacunarity` | 1.2 – 4.0 | 2.0 | Per-octave frequency multiplier. |
| `detail_amp` | 0 – 1 | 0.4 | Lowland relief amplitude. |
| `coast_warp` | 0 – 1 | 0.15 | Coastline warping. |
| `edge_margin` | 0 – 0.3 | 0.04 | Fraction of the map pulled down at the border (islands mode). |

### 5.3 `islands` (array, max 64 entries)

| Key | Type | Range | Default | Notes |
| --- | --- | --- | --- | --- |
| `cx`, `cy` | float | −0.5 – 1.5 | 0.5 | Center in normalized map coordinates; values outside `[0,1]` allow partly off-map islands. |
| `radius` | float | 0.01 – 1.5 | 0.3 | Nominal radius as a fraction of the map's smaller dimension. |
| `aspect` | float | 0.3 – 3.0 | 1.0 | Ellipse aspect ratio. |
| `angle` | float | ±4π | seed-derived | Rotation in radians. `null` = derived from the island seed. |
| `seed` | int | 0 – 2³²−1 | derived | `null` = derived from the global seed via `island_seed(seed, index)`. Legacy single seed; both sub-seeds fall back to it. |
| `shape_seed` | int | 0 – 2³²−1 | `seed` | Outline seed: footprint harmonics, coast warp, shore-band width, default rotation. `null` = follow `seed`. |
| `terrain_seed` | int | 0 – 2³²−1 | `seed` | Surface seed: plain relief, mountains, and the erosion droplet pattern. `null` = follow `seed`. |
| `land_height` | float | 0.02 – 0.60 | 0.085 | Absolute plain elevation. |
| `mountain_height` | float | 0 – 0.60 | 0.15 | Clamped to `1 − land_height`. |
| `mountain_coverage` | float | 0 – 1 | 0.20 | Share of the island that is high ground. |
| `mountain_size` | float | 0.6 – 2.0 | 1.0 | Massif breadth. |
| `shape_variety` | float | 0 – 1 | 0.55 | Footprint variety (see §4.3). |
| `coast_slope` | float | 0 – 1 | 0.5 | Shore profile: sharp → gentle (see §4.3). |
| `enabled` | bool | — | `true` | Disabled islands are skipped. |

### 5.4 `landscape`

Same four elevation knobs as an island, applied map-wide. In landscape mode
there is no coast, so `coast_slope` and `noise.coast_warp` have no effect.

| Key | Range | Default |
| --- | --- | --- |
| `land_height` | 0.02 – 0.60 | 0.10 |
| `mountain_height` | 0 – 0.60 (clamped to `1 − land_height`) | 0.30 |
| `mountain_coverage` | 0 – 1 | 0.18 |
| `mountain_size` | 0.6 – 2.0 | 1.0 |

### 5.5 `erosion`

| Key | Range | Default | Notes |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | |
| `droplets` | 0 – 400 000 (int) | 60 000 | Scaled internally by resolution. |
| `max_steps` | 0 – 200 (int) | 30 | |
| `inertia` | 0 – 100 | 0.05 | Direction smoothing per step. |
| `capacity_factor` | 0 – 100 | 4.0 | Sediment the flow can carry. |
| `min_capacity`, `max_capacity` | 0 – 100 | 0.01 / 0.10 | Capacity clamps. |
| `max_sediment` | 0 – 100 | 0.10 | Per-cell deposition cap. |
| `erode_speed`, `deposit_speed` | 0 – 100 | 0.3 / 0.3 | Fraction of excess removed / deposited. |
| `evaporate` | 0 – 100 | 0.02 | Capacity decay per step. |
| `gravity` | 0 – 100 | 4.0 | Downward acceleration. |
| `brush_radius` | 1 – 8 (int) | 2 | Radius of the erosion brush in pixels. |

### 5.6 `smoothing`

| Key | Range | Default |
| --- | --- | --- |
| `thermal` | 0 – 1 | 0.5 |
| `blur` | 0 – 1 | 0.5 |

### 5.7 Minimal example

```json
{
  "width": 2048,
  "height": 2048,
  "seed": 42,
  "mode": "islands",
  "sea_level": 0.06,
  "islands": [
    { "cx": 0.35, "cy": 0.40, "radius": 0.28, "coast_slope": 1.0, "shape_variety": 0.8 },
    { "cx": 0.70, "cy": 0.62, "radius": 0.20, "coast_slope": 0.0,
      "seed": 777, "shape_seed": 777, "terrain_seed": 4211 }
  ],
  "erosion": { "enabled": true, "droplets": 120000, "max_steps": 40 }
}
```

---

## 6. HTTP API

Base URL `http://127.0.0.1:8765`. All endpoints are listed with live docs at
`/api/docs`. Error responses are JSON of the form `{"error": "..."}`.

### 6.1 Endpoints

| Method & path | Body / query | Response |
| --- | --- | --- |
| `GET /api/health` | — | `{"ok": true}` |
| `GET /api/defaults` | — | `{"config": <normalized default config>}` |
| `POST /api/preview` | body `{"config":{...}}`, query `size` (64–1024, default 512) | Job object — runs synchronously and returns when the render is finished. |
| `POST /api/generate` | body `{"config":{...}}` | `{"id","status"}` — starts a background full-res render. |
| `GET /api/status/{id}` | — | Job object without `width`/`height`. |
| `GET /api/heights/{id}` | — | Raw `float32` little-endian pixels (`height × width`), headers `X-Width`, `X-Height`, `Content-Type: application/octet-stream`. |
| `GET /api/export/{id}` | `format`, `sea_mode`, `sea`, `scale` | The encoded heightmap as a download (see §6.3). |
| `GET /api/masks/{id}` | `kind`, `steepness` | 8-bit mask PNG as a download (see §6.4). |

Unknown `/api/*` paths return `404 {"error":"not found"}`.

### 6.2 Job object

```json
{
  "id": "3f9c1a2b7e40",
  "status": "done",
  "progress": 1.0,
  "stage": "done",
  "ms": 1840,
  "error": null,
  "stats": { "min": 0.0, "max": 0.482, "mean": 0.071, "land_frac": 0.412 },
  "width": 1024,
  "height": 1024
}
```

- `status` — `running` | `done` | `error`; on error, `error` carries
  `ExceptionType: message`.
- `stage` — current pipeline step: `starting`, `composing done`, `erosion`,
  `thermal`, `blur`, `edge`, `done`.
- `progress` — `0.0` … `1.0`.
- `stats` — `min` / `max` / `mean` heights and `land_frac`, the fraction of
  pixels above sea level.

Jobs are held in an in-memory LRU store (`JobStore`): at most **8 jobs** and
**1.5 GB** of height data; running jobs are never evicted. A `404` from any
job endpoint means the id was never created or has been evicted.

### 6.3 `GET /api/export/{id}`

| Query | Values | Default | Meaning |
| --- | --- | --- | --- |
| `format` | `png16` \| `raw16` \| `exr` | `png16` | Output encoding. Unknown values → `400`. |
| `sea_mode` | `keep` \| `flatten` \| `remap` | `keep` | Treatment of pixels below sea level: keep them, zero them, or rescale land to the full `0..1` range. |
| `sea` | 0 – 1 | job's `sea_level` | Overrides the sea level used for the cut. |
| `scale` | float | `1.0` | Multiplier applied to heights (EXR only, where it is applied before encoding). |

Encodings:

| `format` | Content-Type | File | Layout |
| --- | --- | --- | --- |
| `png16` | `image/png` | `hmg_{W}x{H}.png` | 16-bit grayscale PNG. |
| `raw16` | `application/octet-stream` | `hmg_{W}x{H}.raw` | Little-endian `uint16`, row-major, `W × H` pixels. |
| `exr` | `image/x-exr` | `hmg_{W}x{H}.exr` | OpenEXR, single channel, half float. |

### 6.4 `GET /api/masks/{id}`

| Query | Values | Default |
| --- | --- | --- |
| `kind` | `water` \| `slope` | `slope` |
| `steepness` | 0 – 1 | `0.5` |

Returns `image/png`, 8-bit, at the heightmap's own size, named
`hmg_{W}x{H}_{kind}.png`. `kind=water` in landscape mode →
`400 {"error":"water mask needs sea: landscape mode has none"}`.

### 6.5 Example session

```bash
# 1. Fetch the default configuration
curl -s http://127.0.0.1:8765/api/defaults > config.json

# 2. Render a preview at 512 px
curl -s -X POST http://127.0.0.1:8765/api/preview?size=512 \
  -H 'content-type: application/json' \
  -d '{"config":{"seed":42}}'

# 3. Start a full-resolution render
curl -s -X POST http://127.0.0.1:8765/api/generate \
  -H 'content-type: application/json' \
  -d '{"config":{"width":2048,"height":2048,"seed":42}}'
# -> {"id":"<ID>","status":"running"}

# 4. Poll until status is "done"
curl -s http://127.0.0.1:8765/api/status/<ID>

# 5. Download the results
curl -OJ "http://127.0.0.1:8765/api/export/<ID>?format=png16&sea_mode=remap"
curl -OJ "http://127.0.0.1:8765/api/masks/<ID>?kind=slope&steepness=0.4"
```

---

## 7. How generation works

Pipeline (`run_pipeline` in [core/generate.py](core/generate.py)):

```
normalize_config → compose → [hydraulic erosion] → [thermal] → [blur]
                  → [edge margin] → clip to [0,1] → stats
```

Progress stages map onto those steps: `starting` (0.00) → `composing done`
(0.55) → `erosion` (0.55–0.83) → `thermal` (0.83) → `blur` (0.89) → `edge`
(0.94) → `done` (1.00).

### 7.1 Composition (islands mode)

`compose_islands()` builds each island from three independent layers instead
of a radial dome (see the module docstring in
[core/compose.py](core/compose.py)):

1. **Plain** — an absolute elevation (`land_height`) with a gentle fractal
   rise/fall and a slight tilt toward the coast, scaled by `detail_amp`. At
   `detail_amp = 0` the lowland is exactly flat.
2. **Mountains** — a warped, elongated mask noise standardized against its
   local spread and thresholded by `mountain_coverage` selects *ranges* of
   high ground; `mountain_height` scales them and `mountain_size` sets
   massif breadth. Ridged noise carves crests on top of a wide foothill
   apron, so peaks grow out of the plain rather than being planted on it.
3. **Coast** — the warped radial distance decides *where* the island is. The
   rim is a seed-derived Fourier series (`SHAPE_HARMONICS = 2…7`) modulating
   the radius, scaled by `shape_variety`, plus four octaves of fine
   crenulation. The shore band width varies around the island and is set per
   island by `coast_slope`: it interpolates between a short band
   (`0.06–0.16 × radius`, a cliff) and a wide ramp (`0.55–0.75 × radius`, a
   beach). The band is laid out around `WATERLINE = 0.85`, so the slider
   changes steepness without moving the shoreline.

Heights are **absolute**, not sea-relative: raising sea level genuinely floods
land. All noise is sampled in the island's own rotated local frame, so
rotation is a rigid rotation of the whole island.

### 7.2 Composition (landscape mode)

`compose_landscape()` reuses the same mask → crest stack at map scale, with
no coast and no sea, so the terrain runs off the map edges.

### 7.3 Post-processing

- **Hydraulic erosion** ([core/erosion.py](core/erosion.py)) — droplet
  simulation: each droplet walks downhill, picks up sediment according to its
  carrying capacity and deposits it where the slope flattens. Droplet count
  and step length scale with resolution so a 512 preview and a 4k export look
  alike.
- **Thermal smoothing** ([core/smoothing.py](core/smoothing.py)) —
  mass-conserving talus slump: where the local slope exceeds the talus angle,
  a fraction of the excess slides to lower neighbours. Rounds ridge crests
  without changing the coastline.
- **Blur** — a fractional-radius box blur (three passes, approximating a
  Gaussian) that removes residual scratches.
- **Edge margin** — pulls the border of the map down (islands mode) so no
  island is cut off by the frame.

### 7.4 Determinism and seeding

All pseudo-randomness derives from `island_seed(base_seed, index)`, a 32-bit
integer hash used as a NumPy `Generator` seed. Each island carries two
sub-seeds on top of its own:

- **`shape_seed`** — footprint harmonics, coast warp, fine crenulation, the
  shore band and the default rotation, i.e. everything that fixes the
  coastline.
- **`terrain_seed`** — plain relief, the mountain mask/crest stack and the
  erosion pass, i.e. everything that fills the island in.

Both fall back to the island's `seed` when unset, so:

- rerolling one island changes only that island;
- rerolling **Terrain seed** reshapes the land while the outline stays put
  (on an island with no relief and no mountains, the output is
  bit-identical);
- rerolling **Shape seed** redraws the coast while the terrain underneath
  keeps its character;
- the same configuration at the same size always produces a byte-identical
  heightmap.

The post passes (droplet count, talus, blur radius) scale with the map's
smaller dimension, so a 512 preview and a 4096 export of the same config are
designed to *look* alike, not to be pixel-identical.

---

## 8. Export formats in practice

| Format | Typical use |
| --- | --- |
| **PNG16** | Importing into tools that read 16-bit grayscale images (Unreal landscape import, Unity, image-based pipelines). |
| **RAW r16** | Direct file import where the engine expects a bare `uint16` array; pair with the declared W×H. |
| **EXR** | Float pipelines — Houdini, Blender, compositing — where relative precision across the whole range matters. |
| **Masks** | Material blending (water vs. land, rock vs. grass) and procedural placement. |

Choose `sea_mode` to match the consuming tool: `keep` preserves the seabed,
`flatten` zeroes everything underwater, and `remap` stretches land to the
full `0..1` range (this is what the UI uses, so previews and exports agree).

---

## 9. Project structure

```
defaults.json      central default values for the whole tool (single source of truth)
start.py           environment bootstrap + port selection launcher
server.py          FastAPI app: JSON API + static file serving
server.bat         Windows launcher (runs start.py)
requirements.txt   runtime dependencies (pip install -r requirements.txt)
terrain-venv/      virtual environment created by start.py (not in git)
core/generate.py   config normalization, job registry, pipeline orchestration
core/compose.py    island and landscape heightmap composition
core/noise.py      value noise, fbm, ridged noise, island seed hashing
core/erosion.py    droplet-based hydraulic erosion
core/smoothing.py  thermal (talus) smoothing and Gaussian blur
core/export.py     PNG16 / RAW r16 / EXR encoding and sea modes
core/masks.py      water and slope mask PNGs
static/index.html  application markup
static/app.js      UI state, API client, job polling, config save/load
static/preview2d.js  2D canvas preview with island manipulation handles
static/preview3d.js  WebGL 3D preview
static/style.css   styling
tests/e2e.py       end-to-end checks against a running server
```

---

## 10. Testing

The end-to-end suite exercises the running server over HTTP — start it first,
then:

```bash
python tests/e2e.py
```

It prints one `ok` / `FAIL` line per check and covers the static assets,
preview rendering, per-island control isolation, coastline behaviour, flat
lowland and mountain distribution, and the three export formats.

---

## 11. License

MIT — see [LICENSE](LICENSE).
