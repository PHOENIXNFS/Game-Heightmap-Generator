"""Companion mask images derived from a finished heightmap.

Two 8-bit PNGs at the heightmap's own size, so they line up pixel for pixel
in an engine. They are separate downloads, not a bundle: the heightmap is
the product, these are extras for material blending and placement.

* **water** — 255 below the sea line, 0 on land. Islands only: an inland
  landscape tile has no water line at all.
* **slope** — 255 where the ground is steep enough to read as rock/cliff,
  with a soft edge so it antialiases instead of speckling. Steepness is
  relative to the map's own land gradient, so the single slider needs no
  world units and behaves the same at any resolution.
"""

import io

import numpy as np
from PIL import Image

MASK_KINDS = ("water", "slope")

# Absolute floor for the slope mask, in height units per map width. Below
# this the map is simply not steep anywhere (a flat plain), so the mask
# stays empty instead of inventing rock out of numerical noise.
SLOPE_FLOOR = 0.30
# Steepness 0 marks the 55th percentile of the land gradient and 1 the 98th:
# the slider says how steep ground must be to count, so higher = less rock.
# Percentiles keep it honest across modes, whose mountains differ wildly in
# absolute steepness (compact island peaks vs broad landscape ranges).
SLOPE_Q_LO = 0.55
SLOPE_Q_HI = 0.98
# Soft edge around the threshold, as a fraction of it.
SLOPE_FEATHER = 0.18


def _png8(mask):
    buf = io.BytesIO()
    Image.fromarray(mask, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def water_mask(heights, sea_level=0.0):
    """255 wherever the terrain sits below the sea line."""
    h = np.asarray(heights, dtype=np.float32)
    return np.where(h < float(sea_level), 255, 0).astype(np.uint8)


def slope_gradient(heights):
    """Surface steepness in height units per map width (resolution free)."""
    h = np.asarray(heights, dtype=np.float32)
    gy, gx = np.gradient(h)
    return np.hypot(gx, gy) * float(min(h.shape))


def slope_mask(heights, steepness=0.5, sea_level=0.0):
    """255 on ground steeper than the slider's threshold, 0 elsewhere."""
    h = np.asarray(heights, dtype=np.float32)
    g = slope_gradient(h)
    land = h > float(sea_level) if sea_level > 0 else np.ones(h.shape, dtype=bool)
    vals = g[land]
    if vals.size == 0 or float(np.percentile(vals, 99)) < SLOPE_FLOOR:
        return np.zeros(h.shape, dtype=np.uint8)
    s = float(np.clip(steepness, 0.0, 1.0))
    q = SLOPE_Q_LO + (SLOPE_Q_HI - SLOPE_Q_LO) * s
    t = max(float(np.percentile(vals, 100.0 * q)), SLOPE_FLOOR)
    lo = t * (1.0 - SLOPE_FEATHER)
    hi = t * (1.0 + SLOPE_FEATHER)
    x = np.clip((g - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    x = x * x * (3.0 - 2.0 * x)
    x = np.where(land, x, 0.0)
    return np.round(x * 255.0).astype(np.uint8)


def mask_png(kind, heights, sea_level=0.0, steepness=0.5):
    if kind == "water":
        return _png8(water_mask(heights, sea_level))
    if kind == "slope":
        return _png8(slope_mask(heights, steepness, sea_level))
    raise ValueError(f"unknown mask: {kind}")
