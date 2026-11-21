"""GridSense Asset Health — enterprise predictive maintenance platform."""

from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.schemas import HealthOut
from app.services.bootstrap import init_database

settings = get_settings()
setup_logging(debug=settings.app_debug)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Enterprise predictive maintenance for DTRs and feeders using SAP PM–shaped data.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(api_router)


@app.middleware("http")
async def security_and_request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = str(duration_ms)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/api/health", response_model=HealthOut, tags=["ops"])
def health():
    db_ok = "ok"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:  # noqa: BLE001
        db_ok = "error"
    status = "ok" if db_ok == "ok" else "degraded"
    return HealthOut(
        status=status,
        version=settings.app_version,
        env=settings.app_env,
        database=db_ok,
    )


@app.get("/api/ready", tags=["ops"])
def ready():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "not_ready", "error": str(exc)}, status_code=503)
    finally:
        db.close()
    return {"status": "ready"}


@app.get("/")
def home():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"error": "UI missing"}, status_code=404)
    return FileResponse(index)


@app.get("/login")
def login_page():
    page = STATIC_DIR / "login.html"
    if not page.exists():
        return FileResponse(STATIC_DIR / "index.html")
    return FileResponse(page)


def run() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    run()
