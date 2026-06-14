"""ExamShield FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from backend.config import ALLOWED_ORIGINS, APP_TITLE, APP_VERSION
from backend.database import init_db
from backend.ratelimit import limiter
from backend.routes import audit_routes, dashboard_routes, exam_routes, forensics_routes, vault_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    await init_db()
    logger.info("ExamShield started — database initialized")
    yield
    logger.info("ExamShield shutting down")


app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "Too many requests", "code": "RATE_LIMITED"},
    )


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception on %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )


app.include_router(vault_routes.router)
app.include_router(forensics_routes.router)
app.include_router(audit_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(exam_routes.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}
