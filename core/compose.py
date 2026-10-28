"""Heightmap composition: flat plains with sparse, broad mountains.

Islands are built from three independent layers instead of a radial
dome:

* **plain** — an absolute elevation (island ``land_height``) with a
  gentle fbm rise/fall and a slight tilt toward the coast, scaled by
  ``detail_amp``. At ``detail_amp = 0`` the lowland is exactly flat.
* **mountains** — a warped, elongated mask noise standardized against its
  local spread and thresholded by ``mountain_coverage`` selects *ranges* of
  high ground; ``mountain_height`` scales them and ``mountain_size`` sets
  how broad a single massif is. Ridged noise carves crests on top of a wide
  foothill apron, so peaks grow out of the plain instead of being planted
  on it. Coverage 0 = flat atoll, 1 = mountains everywhere.
* **coast** — the warped radial distance ``d`` (0 at the center,
  1 at the rim) decides only *where* the island is. The rim is not a
  plain circle: a seed-derived Fourier series modulates the radius, so
  every island gets its own lobed footprint (bays, peninsulas, spurs),
  and multi-octave noise adds fine crenulation. The shore band's width
  varies around the island, and each island sets its own band width from
  its ``coast_slope``: 0 keeps the band short, so the land falls to the
  sea over a few pixels (sharp drop), 1 stretches it into a long ramp
  (gentle slope). The band is laid out around a fixed shoreline radius,
  so lengthening it changes the steepness without moving the waterline.
  Land keeps its height across most of the band, drops through sea level,
  then eases into a shelf, so no island ends in a cliff.

Heights are absolute (not sea-relative), so the sea-level slider still
floods land: raising it eats into the shore band and then the plain.
All noise is sampled in the island's rotated local frame, so rotation
is a rigid rotation of the whole island.

Landscape: inland terrain built from the same mask -> crest stack at map
scale, with no coast, running off the map edges.
"""

import numpy as np

from .noise import fbm, fbm01, island_seed, ridged

MAX_ISLANDS = 64
# Seabed depth outside the rim, as a multiple of the island's own plain
# height. Scaling it with the island (instead of using a fixed depth) keeps
# the shore slope proportional: the waterline always falls at the same
# fraction of the shore band, so tall and low islands both get a beach-like
# ramp instead of a tall island getting a cliff and a low one a shelf.
SINK_RATIO = 0.45
# Absolute floor so the seabed always sits below zero (and hence below any
# sea level), even for very low islands.
SINK_MIN = 0.01
# Shore band: width as a fraction of the island radius, varying between
# two values around the island (noise-driven). The per-island
# ``coast_slope`` slider (0 = sharp drop, 1 = gentle slope) interpolates
# between two regimes: SHARP_* keeps the band short, so land falls to the
# sea over a few pixels and the coast reads as a cliff; SHORE_* stretches
# it into a wide ramp, so the same island ends in a long beach. SHORE_*
# is the gentle end (and the fallback default's neighbourhood).
SHORE_MIN = 0.55
SHORE_MAX = 0.75
SHARP_SHORE_MIN = 0.06
SHARP_SHORE_MAX = 0.16
# Fallback shoreline for islands (or direct callers) that carry none.
# 0.5 sits just past the old fixed band: a fresh island keeps most of its
# flat plain while reading a little gentler, and the slider can pull it
# either way — 0 is a cliff at the waterline, 1 a long beach ramp.
DEFAULT_COAST_SLOPE = 0.5
# Nominal radius (in island-normalized distance) where the shore profile
# crosses height 0 — the terrain's own shoreline. The band is laid out
# around that point, so coast_slope trades steepness for length without
# moving the shoreline: dragging the slider to "slope" lengthens the ramp
# instead of shrinking the island.
WATERLINE = 0.85
# How much of each end of the shore band is spent easing in/out, per
# regime. The gentle end eases over a quarter of the band so the middle
# runs at one constant slope; the sharp end is nearly a straight ramp.
SHORE_EASE_MIN = 0.05
SHORE_EASE_MAX = 0.30
SHORE_FREQ = 1.4
# Fine coastline warp: octave bands that make the shore fractal instead of
# a smooth blob (fractions of the island radius). Amplitudes are in the
# same units as the radial distance, so 0.06 moves the shore ~0.06 * r.
COAST_FINE = 0.090
COAST_FINE_FREQ = 3.4
COAST_FINE2 = 0.070
COAST_FINE2_FREQ = 11.0
COAST_FINE3 = 0.070
COAST_FINE3_FREQ = 26.0
COAST_FINE4 = 0.025
COAST_FINE4_FREQ = 48.0
# Island footprint shape: instead of a plain circle/ellipse, the rim radius
# is modulated by a seed-derived Fourier series in the local angle. The
# series has mean radius 1 (so footprint area stays comparable across
# varieties) and is clamped, so lobes bulge a little past the nominal radius
# circle without running away. ``shape_variety`` (0..1) scales the
# harmonics: 0 = perfect circle, 1 = strongly lobed. Each island derives its
# own coefficients from its seed, so rerolling a seed reshapes that island.
SHAPE_HARMONICS = (2, 3, 4, 5, 6, 7)
SHAPE_AMP = 0.30
SHAPE_MIN = 0.32
SHAPE_MAX = 1.45
# Default shape variety when the caller omits it.
DEFAULT_SHAPE_VARIETY = 0.55
# Lowland relief, as a fraction of land_height at detail_amp = 1:
# PLAIN_VAR is the rolling rise/fall, PLAIN_SWELL a broad positive tilt
# across the island, PLAIN_DROP the fall toward the coast.
PLAIN_VAR = 0.62
PLAIN_SWELL = 0.24
PLAIN_SWELL_FREQ = 0.45
PLAIN_DROP = 0.35
PLAIN_FREQ = 1.1
# Hollows are made shallower than hills are high (sediment fills basins),
# which keeps a low plain above the sea without a hard floor that would
# leave a flat shelf with a crease around it.
PLAIN_DIP = 0.55
# Width of the coverage -> mask ramp, as a share of the mask field's own
# distribution around the coverage threshold. ``coverage`` is the share of
# the island where the mask reaches 0.5 (real high ground).
MASK_RAMP = 0.45
# Mask shape: 1 - exp(-MASK_K * u^2), an asymptotic ramp that keeps
# climbing above the threshold instead of clipping to a flat tableland.
MASK_K = 2.0
# Octaves of the mask / crest fields: the mask is deliberately smooth
# (it decides *where* a massif is) and the crest carries the texture.
MASK_OCTAVES = 3
RIDGE_OCTAVES = 4
# Spine field: a broad ridged noise multiplied into the mask so high
# ground gathers into an elongated chain with saddles between the spurs,
# instead of one smooth dome. Frequency relative to the massif scale and
# how far a saddle drops the mask (0 = chain breaks, 1 = no effect).
SPINE_FREQ = 0.55
SPINE_MIN = 0.62
SPINE_OCTAVES = 2
# Mountain feature frequency, in features per island radius at size 1.
# ``mountain_size`` scales the features up or down per island: 0.6 gives
# scattered hills, 2.0 one broad range.
MOUNTAIN_SIZE = 2.4
# Domain warp of the mountain mask (fraction of radius) and its frequency.
MOUNTAIN_WARP = 0.22
MOUNTAIN_WARP_FREQ = 1.0
# Ranges are elongated along the island's local x axis by this factor.
RANGE_STRETCH = 1.45
# Cluster field: multiplies the mask so high ground gathers into 1-3
# nuclei, and doubles as the dominance field (CLUSTER_MIN is how far a
# non-dominant crest sinks below the main one).
CLUSTER_FREQ = 0.50
CLUSTER_MIN = 0.55
# Crest noise frequency relative to the mask, and how deep the saddles
# between crests cut into the massif (fraction of mountain_height). The
# mask carries the massif's mass; the crest only adds spine and spurs.
RIDGE_FREQ = 1.90
RIDGE_MIN = 0.55
# Crest exponent: 1 keeps the ridge line smooth; >1 sharpens it into a
# knife edge and shrinks the high ground to a sliver.
CREST_POWER = 1.00
# Dominance floor: how much of its height a crest outside the dominant
# cluster keeps (0.6 = secondary peaks sit 40% lower than the main one).
DOM_MIN = 0.75
# Crest detail falls off faster than the base noise: a massif should read
# as one spine with a few spurs, not a field of equal boulders.
CREST_FALLOFF = 0.90
# Island footprint sampled on a NxN grid to calibrate the mask.
MASK_SAMPLES = 48
# Per-island elevation defaults/clamps for callers that omit them.
DEFAULT_LAND = 0.085
DEFAULT_PEAKS = 0.10
DEFAULT_COVER = 0.20
DEFAULT_SIZE = 1.0
LAND_RANGE = (0.02, 0.60)
PEAK_RANGE = (0.0, 0.60)
COVER_RANGE = (0.0, 1.0)
SIZE_RANGE = (0.6, 2.0)

# ---- landscape (map-scale) ----
# The landscape reuses the island stack (mask -> spine -> crest) but the
# mask lives in map coordinates instead of an island footprint, and there
# is no coast: lowland everywhere, with a few ranges rising out of it.
LANDSCAPE_LAND = 0.10
LANDSCAPE_PEAKS = 0.30
LANDSCAPE_COVER = 0.18
LANDSCAPE_SIZE = 1.0
# Mountain features per map at size 1 (a massif is roughly 1/this wide).
# Low enough that a map holds 1-3 ranges rather than a field of cones.
LAND_MTN_FREQ = 1.3
# Domain warp of the mask: fraction of the map, and cycles per map.
LAND_WARP = 0.06
LAND_WARP_FREQ = 1.2
# Cluster field that gathers high ground into 1-3 nuclei, cycles per map.
LAND_CLUSTER_FREQ = 0.8
# Broad positive swell across the lowland, cycles per map.
LAND_SWELL_FREQ = 1.2
# Coarse grid used to calibrate the mask distribution over the whole map.
LAND_SAMPLES = 64



def _smoothstep(e0, e1, x):
    """Smooth 0->1 ramp from e0 to e1 (works for descending edges too)."""
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _coast_ramp(t, ease):
    """0->1 ramp across the shore band with a constant-slope middle.

    ``ease`` (0..0.45) is how much of each end is spent easing in and out.
    The middle then runs at exactly the average slope, so the waterline —
    which lands near the middle of the band — crosses a steady beach ramp
    instead of smoothstep's steepest point, which sits on the shoreline.
    C2 at both joins, so the flat plain and the flat seabed stay tangent.
    """
    t = np.clip(t, 0.0, 1.0)
    k = float(np.clip(ease, 0.02, 0.45))
    x = t / k
    low = k * (x * x * x - 0.5 * x * x * x * x)
    mid = 0.5 * k + (t - k)
    xr = (1.0 - t) / k
    high = (1.0 - k) - k * (xr * xr * xr - 0.5 * xr * xr * xr * xr)
    s = np.where(t < k, low, np.where(t > 1.0 - k, high, mid))
    return s / (1.0 - k)


def _coast_t_at(level, ease):
    """Fraction along the shore band where the profile reaches ``level``.

    Used to pin the band around the island's shoreline (see WATERLINE):
    the band can then be lengthened or shortened without moving where the
    land meets the water.
    """
    lo, hi = 0.0, 1.0
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        if float(_coast_ramp(mid, ease)) < level:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _norm_ppf(p):
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    p = float(np.clip(p, 1e-9, 1.0 - 1e-9))
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)
    lo, hi = 0.02425, 1.0 - 0.02425
    if p < lo:
        q = np.sqrt(-2.0 * np.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > hi:
        q = np.sqrt(-2.0 * np.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
    )


def _mountain_warp(x, y, freq, amp, seed, persistence, lacunarity):
    """Two decorrelated low-frequency offsets for domain-warping a mask."""
    wx = fbm(x * freq, y * freq, seed, 2, persistence, lacunarity)
    wy = fbm(
        x * freq + 31.7, y * freq + 11.3, seed + 7717, 2, persistence, lacunarity
    )
    return wx * amp, wy * amp


def _float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def island_elevation(isl):
    """Clamped (land_height, mountain_height, coverage, size) tuple."""
    lo, hi = LAND_RANGE
    land = float(np.clip(_float(isl.get("land_height"), DEFAULT_LAND), lo, hi))
    lo, hi = PEAK_RANGE
    peak = float(np.clip(_float(isl.get("mountain_height"), DEFAULT_PEAKS), lo, hi))
    peak = min(peak, max(0.0, 1.0 - land))  # land + peaks never exceeds 1
    lo, hi = COVER_RANGE
    cover = float(np.clip(_float(isl.get("mountain_coverage"), DEFAULT_COVER), lo, hi))
    lo, hi = SIZE_RANGE
    size = float(np.clip(_float(isl.get("mountain_size"), DEFAULT_SIZE), lo, hi))
    return land, peak, cover, size


def landscape_elevation(lcfg):
    """Clamped (land_height, mountain_height, coverage, size) for landscape."""
    lcfg = lcfg if isinstance(lcfg, dict) else {}
    lo, hi = LAND_RANGE
    land = float(np.clip(_float(lcfg.get("land_height"), LANDSCAPE_LAND), lo, hi))
    lo, hi = PEAK_RANGE
    peak = float(np.clip(_float(lcfg.get("mountain_height"), LANDSCAPE_PEAKS), lo, hi))
    peak = min(peak, max(0.0, 1.0 - land))  # land + peaks never exceeds 1
    lo, hi = COVER_RANGE
    cover = float(np.clip(_float(lcfg.get("mountain_coverage"), LANDSCAPE_COVER), lo, hi))
    lo, hi = SIZE_RANGE
    size = float(np.clip(_float(lcfg.get("mountain_size"), LANDSCAPE_SIZE), lo, hi))
    return land, peak, cover, size


def default_island_angle(base_seed, index):
    """Deterministic seed-derived angle used when an island has none."""
    rng = np.random.default_rng(island_seed(base_seed, 0x5A17 + index))
    return float(rng.random()) * 2.0 * np.pi


def island_shape_coeffs(isl_seed, variety):
    """Seed-derived Fourier coefficients for an island's footprint radius.

    Returns a tuple of ``(harmonic, amplitude, phase)`` terms. ``variety``
    in [0, 1] scales every amplitude, so 0 gives an exact circle and 1
    gives strongly lobed, organic coastlines. Higher harmonics add crenels
    to the outline; lower ones make bays and peninsulas.

    The island's own seed also picks its *character*: how lobed the outline
    is overall, and how fast the harmonics fall off with frequency. A high
    decay leaves broad bays and peninsulas (low harmonics dominate); a low
    decay keeps a fringed, crinkled rim. Two islands sitting on the same
    slider value therefore read as different kinds of coast.
    """
    variety = float(np.clip(variety, 0.0, 1.0))
    if variety <= 1e-6:
        return ()
    rng = np.random.default_rng(island_seed(isl_seed, 0x5348))
    scale = 0.70 + 0.50 * rng.random()   # per-island lobedness
    decay = 0.15 + 0.95 * rng.random()   # per-island spectral balance
    coeffs = []
    for n in SHAPE_HARMONICS:
        # Higher harmonics get a little less amplitude so the outline stays
        # readable instead of turning into a starburst.
        amp = SHAPE_AMP * variety * scale * (0.45 + 0.55 * rng.random()) / (n ** decay)
        phase = rng.random() * 2.0 * np.pi
        coeffs.append((n, float(amp), float(phase)))
    return tuple(coeffs)


def compose_islands(
    width,
    height,
    islands,
    seed=0,
    noise_scale=2.5,
    octaves=6,
    persistence=0.5,
    lacunarity=2.0,
    detail_amp=0.4,
    coast_warp=0.35,
    sea_level=0.06,
    edge_margin=0.04,
    shape_variety=DEFAULT_SHAPE_VARIETY,
    coast_slope=DEFAULT_COAST_SLOPE,
    chunk_rows=512,
):
    """Compose islands into a float32 heightmap in [0, 1].

    Heights are absolute: ``land_height`` and ``mountain_height`` are
    elevations in the 0..1 range, not offsets from sea level, so
    raising ``sea_level`` floods land. ``sea_level`` itself no longer
    shapes the terrain and is kept only for API compatibility.
    """
    out = np.zeros((height, width), dtype=np.float32)
    min_dim = min(width, height)
    a = float(np.clip(detail_amp, 0.0, 1.0))
    warp_amp = float(np.clip(coast_warp, 0.0, 1.0))
    terr_freq = noise_scale / min_dim

    active = [
        (i, isl)
        for i, isl in enumerate(islands[:MAX_ISLANDS])
        if isl.get("enabled", True)
    ]

    for i, isl in active:
        radius = max(float(isl.get("radius", 0.25)), 1e-4)
        r_px = radius * min_dim
        asp = float(np.clip(isl.get("aspect", 1.0), 0.3, 3.0))
        # Each island owns a seed; only legacy callers that omit it fall
        # back to a seed derived from the global one.
        isl_seed = isl.get("seed")
        isl_seed = (
            int(isl_seed) & 0xFFFFFFFF
            if isl_seed is not None
            else island_seed(seed, i)
        )
        # Outline vs surface sub-seeds (see normalize_config): shape_seed
        # draws the footprint and rotation, terrain_seed draws the plain,
        # mountains and shore band. A missing key falls back to the island
        # seed, which keeps configs that predate the split byte-identical.
        shape_seed = isl.get("shape_seed")
        shape_seed = (
            int(shape_seed) & 0xFFFFFFFF
            if shape_seed is not None
            else isl_seed
        )
        terrain_seed = isl.get("terrain_seed")
        terrain_seed = (
            int(terrain_seed) & 0xFFFFFFFF
            if terrain_seed is not None
            else isl_seed
        )
        angle = isl.get("angle")
        if angle is None:
            angle = default_island_angle(shape_seed, i)
        angle = float(angle)
        ca = np.float32(np.cos(angle))
        sa = np.float32(np.sin(angle))
        fcx = np.float32(float(isl.get("cx", 0.5)) * width)
        fcy = np.float32(float(isl.get("cy", 0.5)) * height)

        # Coast warp: low-frequency noise (~1 feature per radius) pushing
        # the radial distance in and out, sampled in the local frame, plus
        # four fine bands so the shoreline carries detail at every scale.
        warp_freq = 1.2 / r_px
        fine_freq = COAST_FINE_FREQ / r_px
        fine2_freq = COAST_FINE2_FREQ / r_px
        fine3_freq = COAST_FINE3_FREQ / r_px
        fine4_freq = COAST_FINE4_FREQ / r_px
        # Coast warp, fine crenulation and the shore band's width noise all
        # decide where the waterline falls, so they belong to the outline:
        # shape_seed keeps the coast locked while terrain is rerolled.
        warp_seed = island_seed(shape_seed, 0x51EA + i)
        fine_seed = island_seed(shape_seed, 0x434F + i)
        shore_seed = island_seed(shape_seed, 0x5348 + i)
        # Plain relief and mountains belong to the surface: rerolling
        # terrain_seed reshapes them and leaves the outline where it was.
        terr_seed = island_seed(terrain_seed, 0x7E42 + i)
        plain_seed = island_seed(terrain_seed, 0x504C + i)
        swell_seed = island_seed(terrain_seed, 0x5357 + i)
        mtn_seed = island_seed(terrain_seed, 0x4D4F + i)
        mwarp_seed = island_seed(terrain_seed, 0x4D57 + i)
        ridge_seed = island_seed(terrain_seed, 0x5247 + i)
        spine_seed = island_seed(terrain_seed, 0x5350 + i)
        clu_seed = island_seed(terrain_seed, 0x434C + i)
        # Seed-derived footprint: the radius is modulated by a Fourier
        # series so every island has its own lobed, non-circular outline.
        # Each island may carry its own shape_variety; the function-level
        # value is only the fallback for islands that omit it.
        isl_variety = isl.get("shape_variety")
        if isl_variety is None:
            isl_variety = shape_variety
        shape_coeffs = island_shape_coeffs(shape_seed, isl_variety)
        # Per-island shoreline: 0 keeps the band short (sharp drop at the
        # waterline), 1 stretches it wide (long gentle slope into the sea).
        isl_coast = float(np.clip(_float(isl.get("coast_slope"), coast_slope), 0.0, 1.0))
        band_lo = SHARP_SHORE_MIN + (SHORE_MIN - SHARP_SHORE_MIN) * isl_coast
        band_hi = SHARP_SHORE_MAX + (SHORE_MAX - SHARP_SHORE_MAX) * isl_coast
        coast_ease = SHORE_EASE_MIN + (SHORE_EASE_MAX - SHORE_EASE_MIN) * isl_coast
        # Fine coast detail: mostly independent of the coarse slider, but
        # still fades to nearly nothing at "Coast roughness 0".
        fine_w = 0.25 + 0.75 * warp_amp
        fine_amp = COAST_FINE * fine_w
        fine2_amp = COAST_FINE2 * fine_w
        fine3_amp = COAST_FINE3 * fine_w
        fine4_amp = COAST_FINE4 * fine_w


        # Plain + mountain parameters for this island (clamped).
        land_h, peak_h, cover, msize = island_elevation(isl)
        # Where the nominal shore profile (plain falling to the sunk
        # seabed) crosses height 0, as a fraction of the band. The band is
        # laid out around that point, so a longer band lengthens the ramp
        # in both directions while the shoreline stays at WATERLINE.
        sink_i = max(SINK_MIN, SINK_RATIO * land_h)
        coast_t0 = _coast_t_at(land_h / (land_h + sink_i), coast_ease)
        rough = a  # detail_amp: how much the lowland rolls
        # The mountain mask is thresholded at this island's own distribution:
        # a sample of the warped noise over the footprint fixes the value
        # where mask 0.5 sits (coverage share above it) and how wide the
        # flank ramp is.
        mtn_freq = MOUNTAIN_SIZE / (r_px * msize)
        mwarp_freq = MOUNTAIN_WARP_FREQ / r_px
        mwarp_amp = MOUNTAIN_WARP * r_px
        # Crests follow the massif scale: a broad range has broad crests.
        ridge_freq = mtn_freq * RIDGE_FREQ
        spine_freq = mtn_freq * SPINE_FREQ
        clu_freq = mtn_freq * CLUSTER_FREQ
        plain_freq = PLAIN_FREQ / r_px
        swell_freq = PLAIN_SWELL_FREQ / r_px
        shore_freq = SHORE_FREQ / r_px
        want_mtn = peak_h > 1e-6 and cover > 1e-6
        want_ripple = rough > 1e-6
        if want_mtn:
            # Sample the warped mountain noise over the island's footprint to
            # learn the local mean and spread. The mask is then standardized
            # against them and thresholded in units of that spread, which
            # keeps ``coverage`` (the share of the island above mask 0.5)
            # stable whether a massif spans the island or the island sits on
            # one flank of a much larger range.
            span = r_px * (1.0 + warp_amp) * 1.15
            sxv = np.linspace(-span * asp, span * asp, MASK_SAMPLES, dtype=np.float32)
            syv = np.linspace(-span / asp, span / asp, MASK_SAMPLES, dtype=np.float32)
            gsx, gsy = np.meshgrid(sxv, syv, indexing="xy")
            swx, swy = _mountain_warp(
                gsx, gsy, mwarp_freq, mwarp_amp, mwarp_seed,
                persistence, lacunarity,
            )
            m_sample = fbm01(
                (gsx + swx) * mtn_freq,
                (gsy + swy) * mtn_freq * RANGE_STRETCH,
                mtn_seed, MASK_OCTAVES, persistence, lacunarity,
            )
            # Cluster envelope: gathers high ground into a few nuclei and
            # later decides which crest dominates.
            c_sample = fbm01(
                gsx * clu_freq,
                gsy * clu_freq * RANGE_STRETCH,
                clu_seed, 2, persistence, lacunarity,
            )
            m_sample = m_sample * (CLUSTER_MIN + (1.0 - CLUSTER_MIN) * c_sample)
            s_sample = ridged(
                gsx * spine_freq,
                gsy * spine_freq * RANGE_STRETCH,
                spine_seed, SPINE_OCTAVES, persistence, lacunarity,
            )
            s_vals = s_sample[(gsx / (r_px * asp)) ** 2 + (gsy / r_px) ** 2
                              <= 0.85 ** 2]
            if s_vals.size == 0:
                s_vals = s_sample.ravel()
            s_lo = float(np.quantile(s_vals, 0.05))
            s_hi = float(np.quantile(s_vals, 0.95))
            if s_hi - s_lo < 1e-6:
                s_hi = s_lo + 1e-6
            sp_sample = np.clip((s_sample - s_lo) / (s_hi - s_lo), 0.0, 1.0)
            m_sample = m_sample * (SPINE_MIN + (1.0 - SPINE_MIN) * sp_sample)
            r_sample = ridged(
                gsx * ridge_freq,
                gsy * ridge_freq * RANGE_STRETCH,
                ridge_seed, RIDGE_OCTAVES, persistence * CREST_FALLOFF, lacunarity,
            )
            keep = (gsx / (r_px * asp)) ** 2 + (gsy / r_px) ** 2 <= 0.85**2
            if not keep.any():
                keep = np.ones_like(gsx, dtype=bool)
            m_vals = m_sample[keep]
            r_vals = r_sample[keep]
            c_vals = c_sample[keep]
            m_mu = float(m_vals.mean())
            m_sd = max(float(m_vals.std()), 1e-6)
            # Ramp geometry in standardized units: the mask reaches 0.5 at
            # the (1 - coverage) quantile and grows like a Gaussian from a
            # foot MASK_RAMP wide. It is deliberately asymptotic, so the
            # summit keeps rising instead of clipping to a mesa.
            z_mid = _norm_ppf(np.clip(1.0 - cover, 0.005, 0.995))
            z_lo_raw = _norm_ppf(np.clip(1.0 - cover - 0.5 * MASK_RAMP, 0.005, 0.995))
            z_hi_raw = _norm_ppf(np.clip(1.0 - cover + 0.5 * MASK_RAMP, 0.005, 0.995))
            m_width = max(z_hi_raw - z_lo_raw, 0.35)
            m_foot = z_mid - 0.59 * m_width
            # Crest field stretched to full range, so saddles reach ~0 and
            # spines ~1 instead of the narrow band raw noise produces.
            r_lo = float(np.quantile(r_vals, 0.01))
            r_hi = float(np.quantile(r_vals, 0.99))
            if r_hi - r_lo < 1e-6:
                r_hi = r_lo + 1e-6
            # Dominance: the cluster field, restretched, tells which part of
            # the massif keeps a full-height crest and which sinks to a spur.
            c_lo = float(np.quantile(c_vals, 0.02))
            c_hi = float(np.quantile(c_vals, 0.98))
            if c_hi - c_lo < 1e-6:
                c_hi = c_lo + 1e-6

        reach = r_px * ((WATERLINE + (1.0 - coast_t0) * band_hi + warp_amp
                         + fine_amp + fine2_amp + fine3_amp + fine4_amp)
                        * SHAPE_MAX) + 4.0
        bx0 = max(0, int(fcx) - int(np.ceil(reach)))
        bx1 = min(width, int(fcx) + int(np.ceil(reach)) + 1)
        by0 = max(0, int(fcy) - int(np.ceil(reach)))
        by1 = min(height, int(fcy) + int(np.ceil(reach)) + 1)
        if bx1 <= bx0 or by1 <= by0:
            continue

        xs = np.arange(bx0, bx1, dtype=np.float32)
        for y0 in range(by0, by1, chunk_rows):
            y1 = min(y0 + chunk_rows, by1)
            gy, gx = np.meshgrid(
                np.arange(y0, y1, dtype=np.float32), xs, indexing="ij"
            )
            # World -> island-local frame (rigid rotation by -angle).
            dx = gx - fcx
            dy = gy - fcy
            lx = dx * ca + dy * sa
            ly = -dx * sa + dy * ca

            warp = fbm(lx * warp_freq, ly * warp_freq, warp_seed, 3,
                       persistence, lacunarity) * warp_amp
            # Fine bands: the shore keeps crenulation at 10-60 px instead of
            # being a smooth curve (a smooth boundary has fractal dimension
            # 1.0 exactly, which is the giveaway of a procedural coastline).
            warp += fbm(lx * fine_freq, ly * fine_freq, fine_seed, 3,
                        persistence, lacunarity) * fine_amp
            warp += fbm(lx * fine2_freq, ly * fine2_freq, fine_seed + 31, 2,
                        persistence, lacunarity) * fine2_amp
            warp += fbm(lx * fine3_freq, ly * fine3_freq, fine_seed + 67, 2,
                        persistence, lacunarity) * fine3_amp
            warp += fbm(lx * fine4_freq, ly * fine4_freq, fine_seed + 101, 2,
                        persistence, lacunarity) * fine4_amp
            # Seed-derived footprint: evaluate the Fourier radius at this
            # pixel's local angle. The series has mean 1, so the island's
            # overall size stays put; dividing the radial distance by it
            # carves bays where the profile is small and pushes peninsulas
            # out where it is large.
            if shape_coeffs:
                local_angle = np.arctan2(ly, lx)
                shape_factor = np.ones_like(local_angle)
                for n, amp, phase in shape_coeffs:
                    shape_factor = shape_factor + amp * np.cos(n * local_angle + phase)
                # The series has mean 1, so footprint area stays comparable
                # across varieties; clamp the lobes so a high variety can
                # bulge a little past the radius but never run away.
                shape_factor = np.clip(shape_factor, SHAPE_MIN, SHAPE_MAX)
            else:
                shape_factor = 1.0
            # Elliptical base: aspect > 1 widens along local x, narrows
            # along local y. The shape factor then bends the rim.
            ex = lx / (r_px * asp)
            ey = (ly * asp) / r_px
            d = np.sqrt(ex * ex + ey * ey) / shape_factor + warp
            # ---- plain: near-flat lowland with gentle rolling relief and
            # a slight fall toward the coast (detail_amp scales both, so
            # detail 0 gives an exactly flat plain)
            if want_ripple:
                t = fbm01(lx * terr_freq, ly * terr_freq, terr_seed, octaves, persistence, lacunarity)
                p = fbm01(lx * plain_freq, ly * plain_freq, plain_seed, 4, persistence, lacunarity)
                s = fbm01(lx * swell_freq, ly * swell_freq, swell_seed, 2, persistence, lacunarity)
                roll = PLAIN_VAR * (2.0 * p - 1.0) + PLAIN_SWELL * (2.0 * s - 1.0)
                roll = np.where(roll < 0.0, roll * PLAIN_DIP, roll)
                fall = PLAIN_DROP * _smoothstep(0.15, 1.0, d)
                plain = land_h * (1.0 + rough * (roll - fall))
            else:
                plain = land_h
            # ---- mountains: a warped, elongated mask picks out ranges;
            # ridged noise builds crests over a wide foothill apron
            if want_mtn:
                wvx, wvy = _mountain_warp(
                    lx, ly, mwarp_freq, mwarp_amp, mwarp_seed,
                    persistence, lacunarity,
                )
                m = fbm01(
                    (lx + wvx) * mtn_freq,
                    (ly + wvy) * mtn_freq * RANGE_STRETCH,
                    mtn_seed, MASK_OCTAVES, persistence, lacunarity,
                )
                clu = fbm01(
                    lx * clu_freq,
                    ly * clu_freq * RANGE_STRETCH,
                    clu_seed, 2, persistence, lacunarity,
                )
                m = m * (CLUSTER_MIN + (1.0 - CLUSTER_MIN) * clu)
                sp = ridged(
                    lx * spine_freq, ly * spine_freq * RANGE_STRETCH,
                    spine_seed, SPINE_OCTAVES, persistence, lacunarity,
                )
                sp = np.clip((sp - s_lo) / (s_hi - s_lo), 0.0, 1.0)
                m = m * (SPINE_MIN + (1.0 - SPINE_MIN) * sp)
                u = np.maximum(((m - m_mu) / m_sd - m_foot) / m_width, 0.0)
                mask = 1.0 - np.exp(-MASK_K * u * u)
                r = ridged(
                    lx * ridge_freq, ly * ridge_freq * RANGE_STRETCH,
                    ridge_seed, RIDGE_OCTAVES, persistence * CREST_FALLOFF, lacunarity,
                )
                # Crest field: deliberately not clipped at the top, so each
                # massif has one summit and the ground falls away from it
                # instead of forming a flat tableland.
                rn = (r - r_lo) / (r_hi - r_lo)
                crest = RIDGE_MIN + (1.0 - RIDGE_MIN) * rn
                if CREST_POWER != 1.0:
                    crest = np.maximum(crest, 0.0) ** CREST_POWER
                # Dominance: the cluster field decides which part of the
                # massif carries the highest crest, so the silhouette has
                # one main spine instead of equal bumps.
                dom = DOM_MIN + (1.0 - DOM_MIN) * np.clip(
                    (clu - c_lo) / (c_hi - c_lo), 0.0, 1.0)
                peak = peak_h * mask * crest * dom
            else:
                peak = 0.0

            # keep plain + peaks inside 0..1 even at extreme settings
            if want_mtn:
                plain = np.minimum(plain, 1.0 - peak_h)

            # ---- coast: a continuous slope from the full-height interior
            # down through sea level to the seabed. One eased ramp blends
            # land height into the sunk sea floor, so the profile is
            # monotonic, runs at a constant slope past the waterline, and
            # has no cliff. This island's coast_slope sets how long that
            # ramp is: a short band = sharp drop, a wide band = gentle
            # slope, laid out around a fixed shoreline so the island keeps
            # its size. The sink depth is proportional to this island's
            # plain, which puts the waterline at a fixed fraction of the
            # band for every island.
            sn = fbm01(lx * shore_freq, ly * shore_freq, shore_seed, 3, persistence, lacunarity)
            shore_w = band_lo + (band_hi - band_lo) * sn
            # Lay the band out around the pinned shoreline: widening it
            # lengthens the ramp inland and out to sea without moving the
            # point where the land meets the water.
            band_in = WATERLINE - coast_t0 * shore_w
            coast_t = np.clip((d - band_in) / shore_w, 0.0, 1.0)
            s = _coast_ramp(coast_t, coast_ease)
            sink = max(SINK_MIN, SINK_RATIO * land_h)
            h = (plain + peak) * (1.0 - s) - sink * s

            region = out[y0:y1, bx0:bx1]
            np.maximum(region, h.astype(np.float32), out=region)

    # Guarantee open ocean at the map borders.
    apply_edge_margin(out, width, height, edge_margin)

    np.clip(out, 0.0, 1.0, out=out)
    return out


def apply_edge_margin(out, width, height, edge_margin, chunk_rows=512):
    """Multiply the border ramps down to zero so islands never touch the map edge."""
    if edge_margin <= 1e-6:
        return out
    min_dim = min(width, height)
    margin = edge_margin * min_dim
    xs_all = np.arange(width, dtype=np.float32)
    dx = np.minimum(xs_all, (width - 1) - xs_all)
    for y0 in range(0, height, chunk_rows):
        y1 = min(y0 + chunk_rows, height)
        gy = np.arange(y0, y1, dtype=np.float32)
        dy = np.minimum(gy, (height - 1) - gy)
        edge = np.minimum(dx[None, :], dy[:, None])
        t = np.clip(edge / margin, 0.0, 1.0)
        out[y0:y1] *= (t * t * (3.0 - 2.0 * t)).astype(np.float32)
    return out


def compose_landscape(
    width,
    height,
    seed=0,
    noise_scale=2.5,
    octaves=6,
    persistence=0.5,
    lacunarity=2.0,
    detail_amp=0.4,
    landscape=None,
    chunk_rows=512,
):
    """Continuous inland terrain: near-flat lowland with sparse ranges.

    No sea and no coast: the map is a tile of a larger landmass, so terrain
    runs off every edge. ``land_height`` is the plain, ``mountain_height``
    the rise above it, ``mountain_coverage`` the share of the map that is
    real high ground and ``mountain_size`` how broad one massif is. The
    mountain stack (mask -> spine -> crest -> dominance) is the island one
    with the mask living in map coordinates.
    """
    min_dim = float(min(width, height))
    land_h, peak_h, cover, msize = landscape_elevation(landscape)
    a = float(np.clip(detail_amp, 0.0, 1.0))
    seed = int(seed) & 0xFFFFFFFF

    mtn_freq = LAND_MTN_FREQ / (min_dim * msize)
    mwarp_freq = LAND_WARP_FREQ / min_dim
    mwarp_amp = LAND_WARP * min_dim
    clu_freq = LAND_CLUSTER_FREQ / min_dim
    ridge_freq = mtn_freq * RIDGE_FREQ
    spine_freq = mtn_freq * SPINE_FREQ
    plain_freq = float(noise_scale) / min_dim
    swell_freq = LAND_SWELL_FREQ / min_dim

    mtn_seed = island_seed(seed, 0x4D4F)
    mwarp_seed = island_seed(seed, 0x4D57)
    ridge_seed = island_seed(seed, 0x5247)
    spine_seed = island_seed(seed, 0x5350)
    clu_seed = island_seed(seed, 0x434C)
    plain_seed = island_seed(seed, 0x504C)
    swell_seed = island_seed(seed, 0x5357)

    want_mtn = peak_h > 1e-6 and cover > 1e-6
    want_ripple = a > 1e-6

    if want_mtn:
        # Calibrate the mask on a coarse grid over the whole map: coverage
        # is the share of the map above mask 0.5, and the flank width comes
        # from the field's own spread, so it holds at any resolution.
        sx = np.linspace(0.0, width, LAND_SAMPLES, dtype=np.float32)
        sy = np.linspace(0.0, height, LAND_SAMPLES, dtype=np.float32)
        gsx, gsy = np.meshgrid(sx, sy, indexing="xy")

        sp_sample = ridged(
            gsx * spine_freq, gsy * spine_freq * RANGE_STRETCH,
            spine_seed, SPINE_OCTAVES, persistence, lacunarity,
        )
        s_lo = float(np.quantile(sp_sample, 0.05))
        s_hi = float(np.quantile(sp_sample, 0.95))
        if s_hi - s_lo < 1e-6:
            s_hi = s_lo + 1e-6

        wvx, wvy = _mountain_warp(
            gsx, gsy, mwarp_freq, mwarp_amp, mwarp_seed, persistence, lacunarity,
        )
        m_sample = fbm01(
            (gsx + wvx) * mtn_freq,
            (gsy + wvy) * mtn_freq * RANGE_STRETCH,
            mtn_seed, MASK_OCTAVES, persistence, lacunarity,
        )
        c_sample = fbm01(
            gsx * clu_freq, gsy * clu_freq * RANGE_STRETCH,
            clu_seed, 2, persistence, lacunarity,
        )
        m_sample = m_sample * (CLUSTER_MIN + (1.0 - CLUSTER_MIN) * c_sample)
        sp_norm = np.clip((sp_sample - s_lo) / (s_hi - s_lo), 0.0, 1.0)
        m_sample = m_sample * (SPINE_MIN + (1.0 - SPINE_MIN) * sp_norm)
        r_sample = ridged(
            gsx * ridge_freq, gsy * ridge_freq * RANGE_STRETCH,
            ridge_seed, RIDGE_OCTAVES, persistence * CREST_FALLOFF, lacunarity,
        )

        m_mu = float(m_sample.mean())
        m_sd = max(float(m_sample.std()), 1e-6)
        z_mid = _norm_ppf(np.clip(1.0 - cover, 0.005, 0.995))
        z_lo_raw = _norm_ppf(np.clip(1.0 - cover - 0.5 * MASK_RAMP, 0.005, 0.995))
        z_hi_raw = _norm_ppf(np.clip(1.0 - cover + 0.5 * MASK_RAMP, 0.005, 0.995))
        m_width = max(z_hi_raw - z_lo_raw, 0.35)
        m_foot = z_mid - 0.59 * m_width

        r_lo = float(np.quantile(r_sample, 0.01))
        r_hi = float(np.quantile(r_sample, 0.99))
        if r_hi - r_lo < 1e-6:
            r_hi = r_lo + 1e-6
        c_lo = float(np.quantile(c_sample, 0.02))
        c_hi = float(np.quantile(c_sample, 0.98))
        if c_hi - c_lo < 1e-6:
            c_hi = c_lo + 1e-6

    out = np.empty((height, width), dtype=np.float32)
    xs = np.arange(width, dtype=np.float32)
    for y0 in range(0, height, chunk_rows):
        y1 = min(y0 + chunk_rows, height)
        gy, gx = np.meshgrid(
            np.arange(y0, y1, dtype=np.float32), xs, indexing="ij",
        )

        # ---- plain: near-flat lowland with gentle rolling relief
        if want_ripple:
            p = fbm01(gx * plain_freq, gy * plain_freq, plain_seed, octaves,
                      persistence, lacunarity)
            s = fbm01(gx * swell_freq, gy * swell_freq, swell_seed, 2,
                      persistence, lacunarity)
            roll = PLAIN_VAR * (2.0 * p - 1.0) + PLAIN_SWELL * (2.0 * s - 1.0)
            roll = np.where(roll < 0.0, roll * PLAIN_DIP, roll)
            plain = land_h * (1.0 + a * roll)
        else:
            plain = land_h

        # ---- mountains: same mask -> spine -> crest -> dominance stack
        if want_mtn:
            wvx, wvy = _mountain_warp(
                gx, gy, mwarp_freq, mwarp_amp, mwarp_seed, persistence, lacunarity,
            )
            m = fbm01(
                (gx + wvx) * mtn_freq,
                (gy + wvy) * mtn_freq * RANGE_STRETCH,
                mtn_seed, MASK_OCTAVES, persistence, lacunarity,
            )
            clu = fbm01(
                gx * clu_freq, gy * clu_freq * RANGE_STRETCH,
                clu_seed, 2, persistence, lacunarity,
            )
            m = m * (CLUSTER_MIN + (1.0 - CLUSTER_MIN) * clu)
            sp = ridged(
                gx * spine_freq, gy * spine_freq * RANGE_STRETCH,
                spine_seed, SPINE_OCTAVES, persistence, lacunarity,
            )
            sp = np.clip((sp - s_lo) / (s_hi - s_lo), 0.0, 1.0)
            m = m * (SPINE_MIN + (1.0 - SPINE_MIN) * sp)
            u = np.maximum(((m - m_mu) / m_sd - m_foot) / m_width, 0.0)
            mask = 1.0 - np.exp(-MASK_K * u * u)
            r = ridged(
                gx * ridge_freq, gy * ridge_freq * RANGE_STRETCH,
                ridge_seed, RIDGE_OCTAVES, persistence * CREST_FALLOFF, lacunarity,
            )
            rn = (r - r_lo) / (r_hi - r_lo)
            crest = RIDGE_MIN + (1.0 - RIDGE_MIN) * rn
            if CREST_POWER != 1.0:
                crest = np.maximum(crest, 0.0) ** CREST_POWER
            dom = DOM_MIN + (1.0 - DOM_MIN) * np.clip(
                (clu - c_lo) / (c_hi - c_lo), 0.0, 1.0)
            peak = peak_h * mask * crest * dom
            plain = np.minimum(plain, 1.0 - peak_h)
        else:
            peak = 0.0

        out[y0:y1] = (plain + peak).astype(np.float32)

    np.clip(out, 0.0, 1.0, out=out)
    return out
