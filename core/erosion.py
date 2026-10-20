"""Droplet-based hydraulic erosion.

Droplet count is scaled by resolution (the slider is calibrated for
1024x1024) so small previews don't get pathological over-erosion. The
hot loop runs on nested Python lists — numpy scalar indexing costs
~10x more per access, which dominates this access pattern.
"""

import math

import numpy as np


def _brush_offsets(radius):
    r = int(radius)
    offs = []
    weights = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= r:
                offs.append((dx, dy))
                weights.append(1.0 - dist / (r + 1e-6))
    total = sum(weights)
    weights = [w / total for w in weights]
    return offs, weights


def hydraulic_erosion(
    heights,
    seed=0,
    droplets=60000,
    max_steps=30,
    start_min_height=0.0,
    inertia=0.05,
    capacity_factor=4.0,
    min_capacity=0.01,
    max_capacity=0.10,
    max_sediment=0.10,
    erode_speed=0.3,
    deposit_speed=0.3,
    evaporate=0.02,
    gravity=4.0,
    brush_radius=2,
    progress=None,
):
    """Erode a heightmap (droplet simulation); returns a new float32 array."""
    height, width = heights.shape
    min_dim = min(width, height)
    # Slider is calibrated for 1024; scale droplet density by area.
    n = int(max(1, round(droplets * (min_dim / 1024.0) ** 2)))

    grid = heights.astype(np.float64).tolist()
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    rand = rng.random
    spawn_min = float(start_min_height)
    inv_w = width - 3.0
    inv_h = height - 3.0

    offs, bweights = _brush_offsets(brush_radius)
    off_x = [o[0] for o in offs]
    off_y = [o[1] for o in offs]
    n_offs = len(offs)

    for di in range(n):
        # Spawn on land only.
        x = 1.0 + rand() * inv_w
        y = 1.0 + rand() * inv_h
        if spawn_min > 0.0:
            tries = 0
            while grid[int(y)][int(x)] <= spawn_min and tries < 16:
                x = 1.0 + rand() * inv_w
                y = 1.0 + rand() * inv_h
                tries += 1
            if grid[int(y)][int(x)] <= spawn_min:
                continue

        dx = 0.0
        dy = 0.0
        speed = 1.0
        sediment = 0.0
        row = grid[int(y)]
        for _step in range(int(max_steps)):
            ix = int(x)
            iy = int(y)
            if ix < 1 or iy < 1 or ix >= width - 2 or iy >= height - 2:
                break
            fx = x - ix
            fy = y - iy
            row = grid[iy]
            row2 = grid[iy + 1]

            h00 = row[ix]
            h10 = row[ix + 1]
            h01 = row2[ix]
            h11 = row2[ix + 1]
            gx = (h10 - h00) * (1.0 - fy) + (h11 - h01) * fy
            gy = (h01 - h00) * (1.0 - fx) + (h11 - h10) * fx
            height_here = (
                h00 * (1.0 - fx) * (1.0 - fy)
                + h10 * fx * (1.0 - fy)
                + h01 * (1.0 - fx) * fy
                + h11 * fx * fy
            )

            dx = dx * inertia - gx * (1.0 - inertia)
            dy = dy * inertia - gy * (1.0 - inertia)
            norm = math.sqrt(dx * dx + dy * dy)
            if norm < 1e-8:
                ang = rand() * 2.0 * math.pi
                dx = math.cos(ang)
                dy = math.sin(ang)
            else:
                dx /= norm
                dy /= norm

            x += dx
            y += dy
            nix = int(x)
            niy = int(y)
            if nix < 1 or niy < 1 or nix >= width - 2 or niy >= height - 2:
                break
            nfx = x - nix
            nfy = y - niy
            nrow = grid[niy]
            nrow2 = grid[niy + 1]
            new_height = (
                nrow[nix] * (1.0 - nfx) * (1.0 - nfy)
                + nrow[nix + 1] * nfx * (1.0 - nfy)
                + nrow2[nix] * (1.0 - nfx) * nfy
                + nrow2[nix + 1] * nfx * nfy
            )
            delta = new_height - height_here

            capacity = -delta * speed * gravity * capacity_factor
            if capacity < min_capacity:
                capacity = min_capacity
            elif capacity > max_capacity:
                capacity = max_capacity

            if sediment > capacity or delta > 0.0:
                amount = (sediment - capacity) * deposit_speed
                if amount <= 0.0:
                    amount = 0.0
                elif delta > 0.0 and amount > delta:
                    amount = delta
                if amount > sediment:
                    amount = sediment
                sediment -= amount
                if amount > 0.0:
                    w00 = (1.0 - fx) * (1.0 - fy)
                    w10 = fx * (1.0 - fy)
                    w01 = (1.0 - fx) * fy
                    w11 = fx * fy
                    row[ix] += amount * w00
                    row[ix + 1] += amount * w10
                    row2[ix] += amount * w01
                    row2[ix + 1] += amount * w11
            else:
                amount = (capacity - sediment) * erode_speed
                if amount > -delta:
                    amount = -delta
                if amount > max_sediment:
                    amount = max_sediment
                if amount <= 0.0:
                    break
                taken = 0.0
                for k in range(n_offs):
                    px = ix + off_x[k]
                    py = iy + off_y[k]
                    if 0 <= px < width and 0 <= py < height:
                        d = amount * bweights[k]
                        grid[py][px] -= d
                        taken += d
                sediment += taken

            speed *= 1.0 - evaporate
            if speed < 0.01:
                break

        if progress is not None and di % 8192 == 0:
            progress(di / max(n, 1), "erosion")

    out = np.clip(np.asarray(grid, dtype=np.float64), 0.0, 1.0).astype(np.float32)
    if progress is not None:
        progress(1.0, "erosion")
    return out
