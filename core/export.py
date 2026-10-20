"""Heightmap export: PNG16, RAW r16 (little-endian), float EXR."""

import io

import numpy as np
import OpenEXR
from PIL import Image

FORMATS = ("png16", "raw16", "exr")
SEA_MODES = ("keep", "flatten", "remap")


def apply_sea(heights, sea_level, sea_mode):
    """Apply the sea cut for export. Returns float32 in [0, 1]."""
    x = heights.astype(np.float32)
    sea = float(np.clip(sea_level, 0.0, 1.0))
    if sea_mode == "flatten":
        x = np.where(x < sea, 0.0, x).astype(np.float32)
    elif sea_mode == "remap":
        land = x >= sea
        land_max = float(x[land].max()) if land.any() else 0.0
        out = np.zeros_like(x)
        if land_max > sea + 1e-6:
            out[land] = (x[land] - sea) / (land_max - sea)
        x = np.clip(out, 0.0, 1.0)
    return np.clip(x, 0.0, 1.0)


def _to_u16(x):
    return np.round(x * 65535.0).astype(np.uint16)


def to_png16(heights, sea_level=0.0, sea_mode="keep"):
    x = apply_sea(heights, sea_level, sea_mode)
    img = Image.fromarray(_to_u16(x), mode="I;16")
    buf = io.BytesIO()
    img.save(buf, format="PNG", bitdepth=16)
    return buf.getvalue()


def to_raw16(heights, sea_level=0.0, sea_mode="keep"):
    x = apply_sea(heights, sea_level, sea_mode)
    return _to_u16(x).astype("<u2").tobytes()


def to_exr(heights, sea_level=0.0, sea_mode="keep", scale=1.0):
    x = apply_sea(heights, sea_level, sea_mode).astype(np.float32)
    if scale != 1.0:
        x = x * float(scale)
    f = OpenEXR.File([OpenEXR.Part({}, {"Y": x})])
    buf = io.BytesIO()
    f.write(buf)
    return buf.getvalue()


def export_heights(fmt, heights, sea_level=0.0, sea_mode="keep", scale=1.0):
    if fmt not in FORMATS:
        raise ValueError(f"unknown format: {fmt}")
    if sea_mode not in SEA_MODES:
        raise ValueError(f"unknown sea_mode: {sea_mode}")
    if fmt == "png16":
        return to_png16(heights, sea_level, sea_mode)
    if fmt == "raw16":
        return to_raw16(heights, sea_level, sea_mode)
    return to_exr(heights, sea_level, sea_mode, scale)
