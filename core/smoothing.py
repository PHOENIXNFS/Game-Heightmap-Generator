"""Post-erosion passes: thermal (talus/slump) smoothing and blur.

Both are resolution-scaled so a 512 preview and a 4k export look alike:
every pixel-unit quantity is scaled by min_dim / 1024.
"""

import numpy as np


def thermal_erosion(heights, strength=0.5, relief=1.0, min_dim=1024,
                    iterations=10, talus_frac=0.012, rate=0.5):
    """Mass-conserving talus slump.

    Where the local slope exceeds ``talus`` (height per pixel step), a
    fraction of the excess material slides downhill to lower neighbors.
    Rounds sharp ridge crests into smooth shoulders without changing the
    coastline or the overall relief much.

    ``relief`` is the land height range above sea level; talus scales with
    it so the same ``strength`` behaves identically at any map size.
    """
    h = np.asarray(heights, dtype=np.float64)
    if strength <= 0 or iterations <= 0:
        return h
    talus = talus_frac * float(relief) * (float(min_dim) / 1024.0)
    move = float(strength) * float(rate) / 4.0
    for _ in range(int(iterations)):
        padded = np.pad(h, 1, mode="edge")
        north = padded[:-2, 1:-1]
        south = padded[2:, 1:-1]
        west = padded[1:-1, :-2]
        east = padded[1:-1, 2:]
        # material leaving hcur toward each lower neighbor
        out_n = np.clip(h - north - talus, 0.0, None) * move
        out_s = np.clip(h - south - talus, 0.0, None) * move
        out_w = np.clip(h - west - talus, 0.0, None) * move
        out_e = np.clip(h - east - talus, 0.0, None) * move
        # material received from each higher neighbor flowing toward hcur
        in_n = np.clip(south - h - talus, 0.0, None) * move
        in_s = np.clip(north - h - talus, 0.0, None) * move
        in_w = np.clip(east - h - talus, 0.0, None) * move
        in_e = np.clip(west - h - talus, 0.0, None) * move
        h = h - (out_n + out_s + out_w + out_e) + (in_n + in_s + in_w + in_e)
        h = np.clip(h, 0.0, 1.0)
    return h


def _box_blur_1d(a, radius, axis):
    """Fractional-radius box blur along an axis, edge-replicate padding."""
    if radius <= 0:
        return a
    ir = int(np.floor(radius))
    frac = radius - ir
    pad = ir + 2
    pads = [(pad, pad) if axis == 0 else (0, 0),
            (pad, pad) if axis == 1 else (0, 0)]
    ap = np.pad(a, pads, mode="edge")
    c = np.concatenate(
        [np.zeros_like(ap.take([0], axis=axis)), np.cumsum(ap, axis=axis)],
        axis=axis)
    n = a.shape[axis]
    idx = np.arange(n, dtype=np.int64)
    base = idx + pad

    def window(r):
        c0 = np.take(c, np.clip(base - r, 0, c.shape[axis] - 1), axis=axis)
        c1 = np.take(c, np.clip(base + r + 1, 0, c.shape[axis] - 1), axis=axis)
        return (c1 - c0) / float(2 * r + 1)

    out = window(ir)
    if frac > 0:
        out = (1.0 - frac) * out + frac * window(ir + 1)
    return out


def smooth_blur(heights, strength=0.5, min_dim=1024, passes=3, radius_const=3.0):
    """Separable box blur (3 passes ~ gaussian).

    Fractional radius ``strength * radius_const * min_dim / 1024`` keeps
    relative smoothing identical from 512 preview to 4k export.
    """
    h = np.asarray(heights, dtype=np.float64)
    if strength <= 0 or passes <= 0:
        return h
    radius = float(strength) * float(radius_const) * (float(min_dim) / 1024.0)
    for _ in range(int(passes)):
        h = _box_blur_1d(h, radius, 1)
        h = _box_blur_1d(h, radius, 0)
    return np.clip(h, 0.0, 1.0)
