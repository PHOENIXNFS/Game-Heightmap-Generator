"""Generation pipeline orchestration and the in-memory job registry."""

import copy
import threading
import time
import traceback
import uuid

import numpy as np

from .compose import (
    COVER_RANGE,
    LAND_RANGE,
    PEAK_RANGE,
    SIZE_RANGE,
    apply_edge_margin,
    compose_islands,
    compose_landscape,
    default_island_angle,
)
from .erosion import hydraulic_erosion
from .noise import island_seed
from .smoothing import thermal_erosion, smooth_blur

MIN_DIM = 64
MAX_DIM = 8192

DEFAULT_CONFIG = {
    "width": 1024,
    "height": 1024,
    "seed": 1337,
    "sea_level": 0.06,
    "mode": "islands",
    "noise": {
        "scale": 2.5,
        "octaves": 6,
        "persistence": 0.5,
        "lacunarity": 2.0,
        "detail_amp": 0.4,
        "coast_warp": 0.35,
        "edge_margin": 0.04,
    },
    "islands": [
        {
            "cx": 0.5,
            "cy": 0.5,
            "radius": 0.3,
            "aspect": 1.0,
            "angle": None,
            "seed": None,  # None = derive a distinct seed from the global seed
            # Elevation model: a flat plain at land_height with ranges of
            # mountains above it; coverage 0 = flat atoll, 1 = all mountains,
            # mountain_size scales how broad a single massif is.
            "land_height": 0.12,
            "mountain_height": 0.30,
            "mountain_coverage": 0.20,
            "mountain_size": 1.0,
            "enabled": True,
        }
    ],
    # Landscape-mode elevation model (no sea, no coast): a near-flat plain
    # with ranges of mountains rising out of it. Same four knobs as an
    # island, but they apply to the whole map.
    "landscape": {
        "land_height": 0.10,
        "mountain_height": 0.30,
        "mountain_coverage": 0.18,
        "mountain_size": 1.0,
    },
    "erosion": {
        "enabled": True,
        "droplets": 60000,
        "max_steps": 30,
        "inertia": 0.05,
        "capacity_factor": 4.0,
        "min_capacity": 0.01,
        "max_capacity": 0.10,
        "max_sediment": 0.10,
        "erode_speed": 0.3,
        "deposit_speed": 0.3,
        "evaporate": 0.02,
        "gravity": 4.0,
        "brush_radius": 2,
    },
    "smoothing": {
        "thermal": 0.5,
        "blur": 0.5,
    },
}

# Per-island elevation defaults (kept in sync with core.compose).
LAND_DEFAULT = DEFAULT_CONFIG["islands"][0]["land_height"]
PEAK_DEFAULT = DEFAULT_CONFIG["islands"][0]["mountain_height"]
COVER_DEFAULT = DEFAULT_CONFIG["islands"][0]["mountain_coverage"]
SIZE_DEFAULT = DEFAULT_CONFIG["islands"][0]["mountain_size"]

EROSION_KEYS = (
    "inertia",
    "capacity_factor",
    "min_capacity",
    "max_capacity",
    "max_sediment",
    "erode_speed",
    "deposit_speed",
    "evaporate",
    "gravity",
    "brush_radius",
)


def _num(value, default, lo, hi, cast=float):
    try:
        v = cast(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return cast(min(max(v, lo), hi))


def normalize_config(cfg):
    """Merge a user config over defaults and clamp everything to sane ranges."""
    cfg = cfg if isinstance(cfg, dict) else {}
    base = copy.deepcopy(DEFAULT_CONFIG)
    width = _num(cfg.get("width"), base["width"], MIN_DIM, MAX_DIM, int)
    height = _num(cfg.get("height"), base["height"], MIN_DIM, MAX_DIM, int)
    seed = _num(cfg.get("seed"), base["seed"], 0, 2**31 - 1, int)
    sea = _num(cfg.get("sea_level"), base["sea_level"], 0.0, 1.0)
    mode = "landscape" if str(cfg.get("mode", "")).lower() == "landscape" else "islands"
    if mode == "landscape":
        # An inland tile has no sea: zero the water line so nothing downstream
        # (export flattening, stats, previews) can treat low ground as ocean.
        sea = 0.0

    n_in = cfg.get("noise")
    if not isinstance(n_in, dict):
        n_in = {}
    noise = base["noise"]
    noise["scale"] = _num(n_in.get("scale"), noise["scale"], 0.1, 64.0)
    noise["octaves"] = _num(n_in.get("octaves"), noise["octaves"], 1, 10, int)
    noise["persistence"] = _num(n_in.get("persistence"), noise["persistence"], 0.05, 0.95)
    noise["lacunarity"] = _num(n_in.get("lacunarity"), noise["lacunarity"], 1.2, 4.0)
    noise["detail_amp"] = _num(n_in.get("detail_amp"), noise["detail_amp"], 0.0, 1.0)
    noise["coast_warp"] = _num(n_in.get("coast_warp"), noise["coast_warp"], 0.0, 1.0)
    noise["edge_margin"] = _num(n_in.get("edge_margin"), noise["edge_margin"], 0.0, 0.3)

    islands = []
    raw_islands = cfg.get("islands")
    if not isinstance(raw_islands, list):
        raw_islands = base["islands"]
    for i, item in enumerate(raw_islands[:64]):
        if not isinstance(item, dict):
            continue
        # Every island carries its own seed; the global seed only fills in
        # the gap for configs saved before per-island seeds existed.
        isl_seed = item.get("seed")
        if isl_seed is None:
            isl_seed = island_seed(seed, i)
        else:
            isl_seed = _num(isl_seed, island_seed(seed, i), 0, 2**32 - 1, int) & 0xFFFFFFFF
        angle = item.get("angle")
        base_angle = default_island_angle(isl_seed, i)
        if angle is None:
            angle = base_angle
        else:
            angle = _num(angle, base_angle, -np.pi * 4, np.pi * 4)
        land_h = _num(item.get("land_height"), LAND_DEFAULT, *LAND_RANGE)
        peak_h = _num(item.get("mountain_height"), PEAK_DEFAULT, *PEAK_RANGE)
        peak_h = min(peak_h, max(0.0, 1.0 - land_h))  # land + peaks <= 1
        cover = _num(item.get("mountain_coverage"), COVER_DEFAULT, *COVER_RANGE)
        msize = _num(item.get("mountain_size"), SIZE_DEFAULT, *SIZE_RANGE)
        islands.append(
            {
                "cx": _num(item.get("cx"), 0.5, -0.5, 1.5),
                "cy": _num(item.get("cy"), 0.5, -0.5, 1.5),
                "radius": _num(item.get("radius"), 0.25, 0.01, 1.5),
                "aspect": _num(item.get("aspect"), 1.0, 0.3, 3.0),
                "angle": angle,
                "seed": int(isl_seed),
                "land_height": land_h,
                "mountain_height": peak_h,
                "mountain_coverage": cover,
                "mountain_size": msize,
                "enabled": bool(item.get("enabled", True)),
            }
        )
    if not islands:
        islands = copy.deepcopy(base["islands"])
        islands[0]["seed"] = island_seed(seed, 0)
        islands[0]["angle"] = default_island_angle(islands[0]["seed"], 0)

    e_in = cfg.get("erosion")
    if not isinstance(e_in, dict):
        e_in = {}
    erosion = base["erosion"]
    erosion["enabled"] = bool(e_in.get("enabled", True))
    erosion["droplets"] = _num(e_in.get("droplets"), erosion["droplets"], 0, 400_000, int)
    erosion["max_steps"] = _num(e_in.get("max_steps"), erosion["max_steps"], 0, 200, int)
    for key in EROSION_KEYS:
        if key == "brush_radius":
            erosion[key] = _num(e_in.get(key), erosion[key], 1, 8, int)
        else:
            erosion[key] = _num(e_in.get(key), erosion[key], 0.0, 100.0)

    s_in = cfg.get("smoothing")
    if not isinstance(s_in, dict):
        s_in = {}
    smoothing = base["smoothing"]
    smoothing["thermal"] = _num(s_in.get("thermal"), smoothing["thermal"], 0.0, 1.0)
    smoothing["blur"] = _num(s_in.get("blur"), smoothing["blur"], 0.0, 1.0)

    l_in = cfg.get("landscape")
    if not isinstance(l_in, dict):
        l_in = {}
    landscape = base["landscape"]
    landscape["land_height"] = _num(
        l_in.get("land_height"), landscape["land_height"], *LAND_RANGE)
    landscape["mountain_height"] = _num(
        l_in.get("mountain_height"), landscape["mountain_height"], *PEAK_RANGE)
    landscape["mountain_height"] = min(
        landscape["mountain_height"],
        max(0.0, 1.0 - landscape["land_height"]))  # plain + peaks <= 1
    landscape["mountain_coverage"] = _num(
        l_in.get("mountain_coverage"), landscape["mountain_coverage"], *COVER_RANGE)
    landscape["mountain_size"] = _num(
        l_in.get("mountain_size"), landscape["mountain_size"], *SIZE_RANGE)

    return {
        "width": width,
        "height": height,
        "seed": seed,
        "sea_level": sea,
        "mode": mode,
        "noise": noise,
        "islands": islands,
        "landscape": landscape,
        "erosion": erosion,
        "smoothing": smoothing,
    }


def islands_seed(islands):
    """Fold every island seed into one seed for whole-map passes (erosion).

    Keeps maps reproducible without a global knob: rerolling an island
    re-rolls that island's terrain *and* the droplets that fall on it.
    """
    acc = 0x811C9DC5
    for i, isl in enumerate(islands):
        acc = island_seed(acc ^ int(isl.get("seed", 0)), i + 1)
    return int(acc) & 0xFFFFFFFF


def post_seed(cfg):
    """Seed for the erosion pass: islands fold their own seeds together,
    landscape has no islands so the global seed is the only one there is."""
    if cfg["mode"] != "islands":
        return int(cfg["seed"]) & 0xFFFFFFFF
    return islands_seed(cfg["islands"])


def run_pipeline(cfg, progress=None):
    """Run compose (+ optional erosion) and return a float32 heightmap."""
    cfg = normalize_config(cfg)

    def report(frac, msg):
        if progress is not None:
            progress(max(0.0, min(frac, 1.0)), msg)

    report(0.0, "starting")

    if cfg["mode"] == "landscape":
        heights = compose_landscape(
            cfg["width"],
            cfg["height"],
            seed=cfg["seed"],
            noise_scale=cfg["noise"]["scale"],
            octaves=cfg["noise"]["octaves"],
            persistence=cfg["noise"]["persistence"],
            lacunarity=cfg["noise"]["lacunarity"],
            detail_amp=cfg["noise"]["detail_amp"],
            landscape=cfg["landscape"],
        )
    else:
        heights = compose_islands(
            cfg["width"],
            cfg["height"],
            cfg["islands"],
            seed=cfg["seed"],
            noise_scale=cfg["noise"]["scale"],
            octaves=cfg["noise"]["octaves"],
            persistence=cfg["noise"]["persistence"],
            lacunarity=cfg["noise"]["lacunarity"],
            detail_amp=cfg["noise"]["detail_amp"],
            coast_warp=cfg["noise"]["coast_warp"],
            sea_level=cfg["sea_level"],
            edge_margin=cfg["noise"]["edge_margin"],
        )
    report(0.55, "composing done")

    min_dim = min(cfg["width"], cfg["height"])
    sea = cfg["sea_level"]
    land = heights > sea
    relief = float(heights[land].max() - sea) if land.any() else 0.1

    er = cfg["erosion"]
    if er["enabled"] and er["droplets"] > 0 and er["max_steps"] > 0:

        def erosion_progress(f, msg):
            report(0.55 + 0.28 * f, msg)

        heights = hydraulic_erosion(
            heights,
            seed=post_seed(cfg) ^ 0xE40510,
            droplets=er["droplets"],
            max_steps=er["max_steps"],
            start_min_height=cfg["sea_level"] * 0.98,
            relief=relief,
            progress=erosion_progress,
            **{k: er[k] for k in EROSION_KEYS},
        )

    sm = cfg["smoothing"]
    if sm["thermal"] > 0:
        report(0.83, "thermal")
        heights = thermal_erosion(heights, strength=sm["thermal"], relief=relief, min_dim=min_dim)
    if sm["blur"] > 0:
        report(0.89, "blur")
        heights = smooth_blur(heights, strength=sm["blur"], min_dim=min_dim)
    if cfg["mode"] == "islands" and cfg["noise"]["edge_margin"] > 1e-6:
        report(0.94, "edge")
        heights = apply_edge_margin(heights, cfg["width"], cfg["height"], cfg["noise"]["edge_margin"])

    np.clip(heights, 0.0, 1.0, out=heights)
    report(1.0, "done")
    return heights


def compute_stats(heights, sea_level):
    land = heights > sea_level
    return {
        "min": float(heights.min()),
        "max": float(heights.max()),
        "mean": float(heights.mean()),
        "land_frac": float(land.mean()),
    }


class Job:
    def __init__(self, kind, cfg):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind  # "preview" | "full"
        self.cfg = cfg
        self.status = "running"
        self.progress = 0.0
        self.stage = "queued"
        self.error = None
        self.heights = None
        self.stats = None
        self.created = time.time()
        self.finished = time.time()
        self.ms = 0

    @property
    def nbytes(self):
        if self.heights is None:
            return 0
        return int(self.heights.nbytes)


class JobStore:
    """Thread-safe registry with simple LRU eviction of finished jobs."""

    def __init__(self, max_jobs=8, max_bytes=1_500_000_000):
        self._jobs = {}
        self._order = []
        self._lock = threading.Lock()
        self.max_jobs = max_jobs
        self.max_bytes = max_bytes

    def create(self, kind, cfg):
        job = Job(kind, cfg)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._evict_locked()
        return job

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def remove(self, job_id):
        with self._lock:
            if job_id in self._jobs:
                self._jobs.pop(job_id, None)
                if job_id in self._order:
                    self._order.remove(job_id)

    def _evict_locked(self):
        while len(self._order) > self.max_jobs or sum(
            self._jobs[j].nbytes for j in self._order if j in self._jobs
        ) > self.max_bytes:
            victim = None
            for jid in self._order:
                job = self._jobs.get(jid)
                if job is not None and job.status != "running":
                    victim = jid
                    break
            if victim is None:
                break
            self._order.remove(victim)
            self._jobs.pop(victim, None)


def start_job(store, cfg, kind="full"):
    cfg = normalize_config(cfg)
    job = store.create(kind, cfg)
    t0 = time.time()

    def _progress(f, msg):
        job.progress = float(f)
        job.stage = msg

    def _run():
        try:
            heights = run_pipeline(cfg, progress=_progress)
            job.heights = heights
            job.stats = compute_stats(heights, cfg["sea_level"])
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - report any failure to UI
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            job.ms = int((time.time() - t0) * 1000)
            job.finished = time.time()

    threading.Thread(target=_run, daemon=True).start()
    return job


def run_job_blocking(store, cfg, kind="preview"):
    """Run synchronously (used for previews so the response carries the id)."""
    cfg = normalize_config(cfg)
    job = store.create(kind, cfg)
    t0 = time.time()
    try:
        job.heights = run_pipeline(
            cfg,
            progress=lambda f, m: (
                setattr(job, "progress", float(f)),
                setattr(job, "stage", m),
            ),
        )
        job.stats = compute_stats(job.heights, cfg["sea_level"])
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        job.ms = int((time.time() - t0) * 1000)
        job.finished = time.time()
    return job
