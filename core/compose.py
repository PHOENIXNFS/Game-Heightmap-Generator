"""Classic heightmap composition: FBM noise minus a radial deficit.

Islands: h = terrain - k * d_local^2, then heights above sea level are
compressed by RELIEF so land stays low and gentle over the water
(sea + RELIEF * (h - sea)); everything below sea level is untouched,
so the coastline, water shading and ocean floor are exactly the same
as without compression. The terrain term is full-range noise (same
expression as landscape mode), the deficit grows from 0 at the island
center to k at its rim, so the *noise* decides where the coastline
sits instead of a radial dome envelope. All noise (coast warp +
terrain) is sampled in the island's rotated local frame, so rotation
is a rigid rotation of the whole island.

Landscape: full-map FBM terrain that runs off the map edges.
"""

import numpy as np

from .noise import fbm, fbm01, island_seed

MAX_ISLANDS = 64
# Radial deficit strength: at the rim (d=1) every island sinks to
# terrain - 1.05 < sea level for any detail_amp, guaranteeing ocean.
DEFICIT = 1.05
# Compression of land heights above sea level: land tops out at
# sea + RELIEF * (terrain - sea), keeping islands low over the water.
RELIEF = 0.28


def default_island_angle(base_seed, index):
    """Deterministic seed-derived angle used when an island has none."""
    rng = np.random.default_rng(island_seed(base_seed, 0x5A17 + index))
    return float(rng.random()) * 2.0 * np.pi


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
    chunk_rows=512,
):
    """Compose islands into a float32 heightmap in [0, 1]."""
    out = np.zeros((height, width), dtype=np.float32)
    min_dim = min(width, height)
    a = float(np.clip(detail_amp, 0.0, 1.0))
    warp_amp = float(np.clip(coast_warp, 0.0, 1.0))
    sea_c = np.float32(np.clip(sea_level, 0.0, 1.0))
    relief_c = np.float32(RELIEF)
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
        angle = isl.get("angle")
        if angle is None:
            angle = default_island_angle(isl_seed, i)
        angle = float(angle)
        ca = np.float32(np.cos(angle))
        sa = np.float32(np.sin(angle))
        fcx = np.float32(float(isl.get("cx", 0.5)) * width)
        fcy = np.float32(float(isl.get("cy", 0.5)) * height)

        # Coast warp: low-frequency noise (~1 feature per radius) pushing
        # the radial distance in and out, sampled in the local frame.
        warp_freq = 1.2 / r_px
        warp_seed = island_seed(isl_seed, 0x51EA + i)
        terr_seed = island_seed(isl_seed, 0x7E42 + i)

        reach = r_px * (1.0 + warp_amp) + 4.0
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

            warp = fbm(lx * warp_freq, ly * warp_freq, warp_seed, 3, persistence, lacunarity)
            # elliptical island: rim at local (+-r*aspect, 0) / (0, +-r/aspect)
            ex = lx / (r_px * asp)
            ey = (ly * asp) / r_px
            d = np.sqrt(ex * ex + ey * ey) + warp * warp_amp

            t = fbm01(lx * terr_freq, ly * terr_freq, terr_seed, octaves, persistence, lacunarity)
            # terrain around 0.5 (same expression as compose_landscape)
            terrain = 0.5 + a * (t - 0.5)
            # subtract the radial deficit: 0 at center, 1 at rim -> ocean
            h = terrain - DEFICIT * d * d
            # compress land so islands sit low above the water; the map
            # is fixed at h == sea_level, so the coastline is unchanged
            h = np.where(h >= sea_c, sea_c + relief_c * (h - sea_c), h)

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
    chunk_rows=512,
):
    """Continuous full-map FBM terrain (hills to mountains), no islands.

    ``detail_amp`` 0 = flat plain at 0.5, 1 = full-range mountains.
    Terrain runs off the map edges by default.
    """
    freq = noise_scale / min(width, height)
    a = float(np.clip(detail_amp, 0.0, 1.0))
    out = np.empty((height, width), dtype=np.float32)
    seed = int(seed)

    for y0 in range(0, height, chunk_rows):
        y1 = min(y0 + chunk_rows, height)
        gy, gx = np.meshgrid(
            np.arange(y0, y1, dtype=np.float64),
            np.arange(width, dtype=np.float64),
            indexing="ij",
        )
        t = fbm01(gx * freq, gy * freq, seed, octaves, persistence, lacunarity)
        out[y0:y1] = (0.5 + 0.5 * a * (2.0 * t - 1.0)).astype(np.float32)

    np.clip(out, 0.0, 1.0, out=out)
    return out
