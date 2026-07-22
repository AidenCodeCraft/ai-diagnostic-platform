import sys
from pathlib import Path

# Ensure project root is on sys.path for plugins package
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging_config import setup_logging, get_logger
from app.api.router import api_router
from app.database.seed import seed_users

# ── Initialize logging first ──────────────────────────────────
setup_logging(level="DEBUG" if settings.DEBUG else "INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting — seeding users...")
    seed_users()
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# ── Global exception handler ──────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception: {exc}",
        extra={"path": str(request.url), "method": request.method},
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Middleware: request logging ───────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url.path}", extra={"method": request.method, "path": request.url.path})
    response = await call_next(request)
    if response.status_code >= 400:
        logger.warning(
            f"{request.method} {request.url.path} → {response.status_code}",
            extra={"status": response.status_code},
        )
    return response


app.include_router(
    api_router,
    prefix="/api/v1",
)


@app.get("/")
def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
