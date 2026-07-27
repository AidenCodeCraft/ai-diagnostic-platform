import sys
from pathlib import Path

# Ensure project root is on sys.path for plugins package
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging_config import setup_logging, get_logger
from app.api.router import api_router
from app.database.seed import seed_users

# ── Initialize logging first ──────────────────────────────────
setup_logging(level="DEBUG" if settings.DEBUG else "INFO")
logger = get_logger(__name__)

# ── Log Desensitization (Enabled in production) ───────────────
if getattr(settings, 'LOG_DESENSITIZE_ENABLED', False):
    from app.security.log_desensitizer import apply_log_desensitization, DesensitizeLevel
    apply_log_desensitization(level=DesensitizeLevel.MODERATE)


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

# ── CORS (安全配置) ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [
        "https://ai-diagnostic.example.com",
        "https://api.ai-diagnostic.example.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
    max_age=3600,
)

# ── Prometheus Metrics (Enabled in production) ────────────────
if getattr(settings, 'PROMETHEUS_METRICS_ENABLED', True):
    from app.monitoring.metrics import setup_metrics
    setup_metrics(app)
    logger.info("[Main] Prometheus metrics enabled at /metrics")

# ── API Security Middleware (速率限制 + 防重放 + 输入验证) ───
if getattr(settings, 'RATE_LIMIT_ENABLED', True):
    from app.security.api_security import setup_security_middleware
    setup_security_middleware(
        app,
        global_rate_per_min=int(getattr(settings, 'RATE_LIMIT_PER_MINUTE', 600)),
        per_path_rate_per_min=120,
        per_ip_rate_per_min=60,
        enable_replay_protection=not settings.DEBUG,
        enable_input_validation=not settings.DEBUG,
    )
    logger.info("[Main] API security middleware enabled")

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
