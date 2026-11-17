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
    _tune_threadpool()

    # 恢复中断的异步分析任务（进程内线程池无法跨重启持久化）
    try:
        from app.database import session as session_module
        from app.services.diagnostics.analysis_task_service import AnalysisTaskService

        db = session_module.create_session()
        try:
            recovered = AnalysisTaskService.recover_interrupted(db)
            if recovered:
                logger.warning("Recovered %d interrupted analysis task(s)", recovered)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - 启动恢复失败不应阻断服务
        logger.exception("Failed to recover interrupted analysis tasks")

    yield
    logger.info("Application shutting down")


def _tune_threadpool() -> None:
    """按系统参数（最大同时在线人数）扩容 anyio 默认线程池。

    同步流式接口在等待 LLM 返回 token 期间会占用线程池线程，
    anyio 默认仅 40 条，必须与允许的并发提问数匹配，否则并发提问会被排队卡死。
    """
    try:
        import anyio.to_thread

        from app.services.system.system_config import get_system_config

        max_online = int(get_system_config().get("max_online_users", 200) or 200)
        desired = max(64, max_online + 20)
        limiter = anyio.to_thread.current_default_thread_limiter()
        if desired > limiter.total_tokens:
            logger.info("[Main] Thread pool size: %d -> %d", limiter.total_tokens, desired)
            limiter.total_tokens = desired
    except Exception:  # noqa: BLE001 - 调整失败不阻断启动
        logger.exception("Failed to tune thread pool size")


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
