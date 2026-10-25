"""Deterministic vectorized value-noise FBM on numpy coordinate grids."""

import numpy as np

_U64 = np.uint64


def _hash01(ix, iy, seed):
    """Per-lattice-point hash mapped to [-1, 1]. Deterministic in uint64."""
    h = (
        ix.astype(_U64) * _U64(374761393)
        + iy.astype(_U64) * _U64(668265263)
        + _U64(int(seed) & 0xFFFFFFFF) * _U64(1442695041)
    )
    h ^= h >> _U64(13)
    h *= _U64(1274126177)
    h ^= h >> _U64(16)
    return (h & _U64(0xFFFF)).astype(np.float64) / 32767.5 - 1.0


def value_noise(x, y, seed):
    """Smooth value noise in [-1, 1] over float coordinate arrays."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    xi = np.floor(x)
    yi = np.floor(y)
    xf = x - xi
    yf = y - yi
    u = xf * xf * (3.0 - 2.0 * xf)
    v = yf * yf * (3.0 - 2.0 * yf)
    xi = xi.astype(np.int64)
    yi = yi.astype(np.int64)
    n00 = _hash01(xi, yi, seed)
    n10 = _hash01(xi + 1, yi, seed)
    n01 = _hash01(xi, yi + 1, seed)
    n11 = _hash01(xi + 1, yi + 1, seed)
    nx0 = n00 + u * (n10 - n00)
    nx1 = n01 + u * (n11 - n01)
    return nx0 + v * (nx1 - nx0)


def fbm(x, y, seed, octaves=6, persistence=0.5, lacunarity=2.0):
    """Fractional Brownian motion in roughly [-1, 1].

    ``x``/``y`` are in noise units (frequency = 1 unit per lattice cell);
    callers scale pixel coordinates by the desired cycles-per-pixel.
    """
    total = np.zeros(np.broadcast(np.asarray(x), np.asarray(y)).shape, dtype=np.float64)
    amp = 1.0
    norm = 0.0
    freq = 1.0
    for i in range(int(octaves)):
        total += amp * value_noise(
            np.asarray(x, dtype=np.float64) * freq,
            np.asarray(y, dtype=np.float64) * freq,
            int(seed) + i * 1013,
        )
        norm += amp
        amp *= persistence
        freq *= lacunarity
    return total / norm


def fbm01(x, y, seed, octaves=6, persistence=0.5, lacunarity=2.0):
    """FBM remapped to [0, 1]."""
    return np.clip(fbm(x, y, seed, octaves, persistence, lacunarity) * 0.5 + 0.5, 0.0, 1.0)


def ridged(x, y, seed, octaves=4, persistence=0.5, lacunarity=2.0):
    """Ridged multifractal in [0, 1]: sharp crest lines, broad valleys.

    Each octave contributes ``(1 - |noise|)**2`` weighted by the previous
    octave, so fine detail appears on the crests instead of spraying over
    the whole surface. That hierarchy (dominant spine, spurs, then
    gullies) is what makes a massif read as a mountain rather than a pile
    of equal bumps.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    total = np.zeros(np.broadcast(x, y).shape, dtype=np.float64)
    amp = 1.0
    freq = 1.0
    prev = 1.0
    norm = 0.0
    for i in range(int(octaves)):
        # Rotate each octave: |noise| creases otherwise follow the value
        # noise lattice, which shows up as straight-edged steps on a flank.
        ang = 0.37 + i * 0.7231
        ca, sa = np.cos(ang), np.sin(ang)
        xo = x * freq
        yo = y * freq
        n = 1.0 - np.abs(value_noise(
            xo * ca - yo * sa, xo * sa + yo * ca, int(seed) + i * 1013))
        n *= n
        total += amp * n * prev
        norm += amp
        # Keep part of every octave alive: a pure multifractal suppresses
        # fine detail to the knife-edge crest and leaves the flanks glassy.
        prev = 0.55 + 0.45 * n
        amp *= persistence
        freq *= lacunarity
    return total / norm if norm > 0.0 else total


def island_seed(base_seed, index):
    """Stable per-island seed so editing one island doesn't perturb others."""
    return (int(base_seed) * 73856093 ^ int(index) * 19349663) & 0xFFFFFFFF
