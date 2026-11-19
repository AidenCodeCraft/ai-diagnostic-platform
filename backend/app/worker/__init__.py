"""异步任务（P2）：Celery 应用、任务状态、日志处理链路。"""

from app.worker.celery_app import celery_app

__all__ = ["celery_app"]
