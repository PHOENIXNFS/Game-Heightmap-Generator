"""Local web server for the terrain heightmap generator.

Run with:  python server.py   (then open http://127.0.0.1:8765)
"""

from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from core.export import FORMATS, SEA_MODES, export_heights
from core.generate import (
    DEFAULT_CONFIG,
    JobStore,
    normalize_config,
    run_job_blocking,
    start_job,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Terrain Heightmap Generator", docs_url="/api/docs")
store = JobStore()


@app.middleware("http")
async def no_store_static(request, call_next):
    """Never cache assets: the UI was rewritten in place and stale JS
    from an old open tab breaks it."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/defaults")
def defaults():
    return {"config": normalize_config(DEFAULT_CONFIG)}


@app.post("/api/preview")
async def preview(request: Request, size: int = Query(512, ge=64, le=1024)):
    """Interactive preview; capped at 1024 so a stray client cannot ask the
    server for a 2k preview. Full-resolution renders go through /api/generate."""
    body = await request.json()
    cfg = body.get("config") if isinstance(body, dict) else None
    cfg = cfg if isinstance(cfg, dict) else {}
    cfg["width"] = size
    cfg["height"] = size
    # run off the event loop: generation takes seconds and must not
    # freeze status polls / static files / other requests
    job = await run_in_threadpool(run_job_blocking, store, cfg, "preview")
    return _job_response(job)


@app.get("/api/heights/{job_id}")
def heights(job_id: str):
    job = store.get(job_id)
    if job is None or job.heights is None:
        return JSONResponse({"error": "job not found"}, status_code=404)
    data = job.heights.astype("<f4").tobytes()
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "X-Width": str(job.heights.shape[1]),
            "X-Height": str(job.heights.shape[0]),
        },
    )


@app.post("/api/generate")
async def generate(request: Request):
    body = await request.json()
    cfg = body.get("config") if isinstance(body, dict) else None
    job = start_job(store, cfg, kind="full")
    return {"id": job.id, "status": job.status}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    job = store.get(job_id)
    if job is None:
        return JSONResponse({"error": "job not found"}, status_code=404)
    return _job_response(job, include_heights_meta=False)


@app.get("/api/export/{job_id}")
def export(
    job_id: str,
    format: str = Query("png16"),
    sea_mode: str = Query("keep"),
    sea: float | None = Query(None),
    scale: float = Query(1.0),
):
    job = store.get(job_id)
    if job is None or job.heights is None:
        return JSONResponse({"error": "job not found"}, status_code=404)
    if format not in FORMATS:
        return JSONResponse({"error": f"unknown format: {format}"}, status_code=400)
    if sea_mode not in SEA_MODES:
        return JSONResponse({"error": f"unknown sea_mode: {sea_mode}"}, status_code=400)
    sea_level = job.cfg["sea_level"] if sea is None else min(max(sea, 0.0), 1.0)
    try:
        data = export_heights(format, job.heights, sea_level, sea_mode, scale)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    media = {
        "png16": "image/png",
        "raw16": "application/octet-stream",
        "exr": "image/x-exr",
    }[format]
    name = f"hmg_{job.heights.shape[1]}x{job.heights.shape[0]}.{format}"
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _job_response(job, include_heights_meta=True):
    payload = {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "ms": job.ms,
        "error": job.error,
        "stats": job.stats,
    }
    if include_heights_meta:
        payload["width"] = job.heights.shape[1] if job.heights is not None else 0
        payload["height"] = job.heights.shape[0] if job.heights is not None else 0
    return payload


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"error": "not found"}, status_code=404)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
