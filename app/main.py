import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.error_handlers import register_exception_handlers
from app.routes import (
    auth_routes,
    authority_routes,
    dashboard_routes,
    report_routes,
    verification_routes,
)
from app.scheduler.escalation_scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# Resolve upload directory relative to this file so it works regardless of
# which directory uvicorn is started from.
# app/main.py  →  parent = app/  →  parent.parent = project root
_BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = _BASE_DIR / "app" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Serve uploaded images at /uploads/reports/<filename>
# e.g. http://<server>:8000/uploads/reports/abc123.jpg
app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploads",
)

app.include_router(auth_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(report_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(verification_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(authority_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard_routes.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME}
