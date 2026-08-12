"""FastAPI app entrypoint.

On startup: create the schema, seed once, and start the background publish
engine. Also serves the built frontend from ../../frontend/dist if present, so a
production build can run from a single process.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

from . import config  # noqa: F401 — loads backend/.env into the environment on import

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import scheduler, seed
from .api import router


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    seed.seed_if_empty()
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(title="Wolfie API", version="0.1.0", lifespan=lifespan)

# Vite dev server proxies /api, but allow direct browser access too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve the production build if it exists (frontend/dist).
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    def _index():
        return FileResponse(_DIST / "index.html")
