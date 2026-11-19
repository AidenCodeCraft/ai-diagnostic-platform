"""Celery 可靠性配置与任务注册测试（不连接 broker）。"""

from app.worker.celery_app import EMBED_QUEUE, celery_app
from app.worker import tasks as ingest_tasks


def test_reliability_settings():
    conf = celery_app.conf

    assert conf.task_acks_late is True
    assert conf.worker_prefetch_multiplier == 1
    assert int(conf.broker_transport_options["visibility_timeout"]) >= 600
    assert conf.task_time_limit and conf.task_soft_time_limit
    assert conf.task_soft_time_limit < conf.task_time_limit


def test_queues_are_declared():
    names = {queue.name for queue in celery_app.conf.task_queues}
    assert {"ingest", EMBED_QUEUE} <= names
    assert celery_app.conf.task_default_queue == "ingest"


def test_serialization_is_json_only():
    conf = celery_app.conf
    assert conf.task_serializer == "json"
    assert conf.result_serializer == "json"
    assert list(conf.accept_content) == ["json"]


def test_pipeline_tasks_are_registered():
    for name in (
        "ingest.prepare", "ingest.parse", "ingest.template",
        "ingest.compress", "embed.log_index", "ingest.finalize",
    ):
        assert name in celery_app.tasks, f"{name} 未注册"


def _flatten_tasks(signature):
    names = []
    children = getattr(signature, "tasks", None)
    if children is not None:
        for child in children:
            names.extend(_flatten_tasks(child))
    else:
        task = getattr(signature, "task", None)
        if task:
            names.append(task)
    body = getattr(signature, "body", None)
    if body is not None:
        names.extend(_flatten_tasks(body))
    return names


def test_pipeline_chain_order_and_immutability():
    from app.worker.ingest_service import ChunkPlan
    from app.worker.tasks import build_pipeline_chain

    signature = build_pipeline_chain(9, [ChunkPlan(0, 0, 10), ChunkPlan(1, 10, 10)])

    assert _flatten_tasks(signature) == [
        "ingest.parse", "ingest.parse",
        "ingest.template", "ingest.compress", "embed.log_index", "ingest.finalize",
    ]


def test_log_index_task_routes_to_embed_queue():
    routed = celery_app.amqp.router.route({}, "embed.log_index")
    assert routed["queue"].name == EMBED_QUEUE


def test_tasks_have_retry_policy():
    for name in ("ingest.prepare", "ingest.parse", "ingest.template", "ingest.compress"):
        task = celery_app.tasks[name]
        assert task.max_retries and task.max_retries > 0


def test_parse_task_routes_to_ingest_queue():
    routed = celery_app.amqp.router.route({}, "ingest.parse")
    assert routed["queue"].name == "ingest"
    embed_routed = celery_app.amqp.router.route({}, "embed.chunk")
    assert embed_routed["queue"].name == EMBED_QUEUE
    assert ingest_tasks.EMBED_QUEUE == "embed"
