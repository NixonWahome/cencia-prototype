"""FastAPI entry point: `uvicorn app.main:app --reload` from backend/."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api import alerts, demo, integrity, reports, scans, sites, telemetry, ws
from .config import Settings
from .runtime import build_runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cencia")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_db(settings.db_path, reset=settings.reset_on_start)
        log.info("seeding sites and %d days of signed history...", settings.history_days)
        rt = await asyncio.to_thread(build_runtime, settings)
        app.state.rt = rt
        log.info("ready: sim time %s at %sx", rt.clock.now().isoformat(timespec="minutes"), rt.clock.speed)
        await rt.start()
        try:
            yield
        finally:
            await rt.stop()
            db.dispose()

    app = FastAPI(title="Cencia AI prototype (simulated demo data)", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (sites, telemetry, alerts, scans, integrity, reports, demo, ws):
        app.include_router(module.router)

    @app.get("/api/health")
    def health():
        return {"ok": True, "simulated": True}

    _serve_frontend(app)
    return app


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _serve_frontend(app: FastAPI) -> None:
    """Serve the built React app (npm run build) so one process runs the whole demo."""
    if not (FRONTEND_DIST / "index.html").exists():
        return
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = FRONTEND_DIST / path
        if path and candidate.is_file() and FRONTEND_DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


app = create_app()
