"""Celery 应用（P2 步骤 1）。

可靠性相关的四个参数缺一不可，否则长任务会重复执行或丢任务：
  - `task_acks_late=True`：任务执行完才 ack（worker 崩溃不会丢任务）
  - `worker_prefetch_multiplier=1`：一次只预取一个，长任务不堵队列
  - `visibility_timeout` ≥ 单步最长耗时×2：Redis 队列里不设会被重复投递
  - `task_time_limit` / `task_soft_time_limit`：兜底杀超时任务
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import settings

DEFAULT_QUEUE = "ingest"
EMBED_QUEUE = "embed"


def create_celery_app() -> Celery:
    app = Celery("ai_diagnostic")

    time_limit = int(getattr(settings, "CELERY_TASK_TIME_LIMIT", 900) or 900)
    visibility_timeout = int(getattr(settings, "CELERY_VISIBILITY_TIMEOUT", 3600) or 3600)

    app.conf.update(
        broker_url=str(getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/1")),
        result_backend=str(getattr(settings, "CELERY_RESULT_BACKEND", "redis://localhost:6379/2")),
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_time_limit=time_limit,
        task_soft_time_limit=max(30, time_limit - 60),
        broker_transport_options={"visibility_timeout": visibility_timeout},
        task_default_queue=DEFAULT_QUEUE,
        task_queues=(Queue(DEFAULT_QUEUE), Queue(EMBED_QUEUE)),
        task_default_exchange=DEFAULT_QUEUE,
        task_default_routing_key=DEFAULT_QUEUE,
        task_routes={
            "ingest.*": {"queue": DEFAULT_QUEUE},
            "embed.*": {"queue": EMBED_QUEUE},
        },
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Shanghai",
        enable_utc=True,
        worker_max_tasks_per_child=int(getattr(settings, "CELERY_MAX_TASKS_PER_CHILD", 50) or 50),
    )
    return app


celery_app = create_celery_app()
celery_app.autodiscover_tasks(["app.worker"], related_name="tasks", force=True)
