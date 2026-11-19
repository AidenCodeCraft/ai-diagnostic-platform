"""任务状态与幂等测试（P2 步骤 1）。"""

from app.models import Log
from app.worker.task_state import (
    MAX_ATTEMPTS,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    TaskStateStore,
    task_key,
)


def _log(db_session):
    log = Log(filename="a.log", file_path="/tmp/a.log", status="parsed")
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


def test_task_key_is_deterministic():
    assert task_key(7, "parse", 2) == "7:parse:2"


def test_claim_creates_running_task(db_session):
    log = _log(db_session)
    store = TaskStateStore(db_session)

    claim = store.claim(log_id=log.id, stage="prepare")

    assert claim["claimed"] is True
    assert claim["task"].status == "running"
    assert claim["task"].state == "prepare"
    assert '"attempts": 1' in claim["task"].steps


def test_claim_twice_increments_attempts(db_session):
    log = _log(db_session)
    store = TaskStateStore(db_session)

    store.claim(log_id=log.id, stage="parse", chunk_no=1)
    second = store.claim(log_id=log.id, stage="parse", chunk_no=1)

    assert second["claimed"] is True
    assert '"attempts": 2' in second["task"].steps


def test_succeeded_task_is_not_reclaimed(db_session):
    log = _log(db_session)
    store = TaskStateStore(db_session)

    claim = store.claim(log_id=log.id, stage="compress")
    store.finish(claim["task"], status=STATUS_SUCCEEDED, summary="ok")

    again = store.claim(log_id=log.id, stage="compress")
    assert again["claimed"] is False
    assert again["reason"] == "already-succeeded"


def test_attempts_exhausted_requires_manual(db_session):
    log = _log(db_session)
    store = TaskStateStore(db_session)

    for _ in range(MAX_ATTEMPTS):
        store.claim(log_id=log.id, stage="template")
    blocked = store.claim(log_id=log.id, stage="template")

    assert blocked["claimed"] is False
    assert blocked["reason"] == "attempts-exhausted"


def test_finish_failure_records_error(db_session):
    log = _log(db_session)
    store = TaskStateStore(db_session)

    claim = store.claim(log_id=log.id, stage="parse", chunk_no=0)
    task = store.finish(claim["task"], status=STATUS_FAILED, error="boom")

    assert task.status == "failed"
    assert task.error_message == "boom"


def test_summary_aggregates_stages(db_session):
    log = _log(db_session)
    store = TaskStateStore(db_session)

    ok = store.claim(log_id=log.id, stage="parse", chunk_no=0)
    store.finish(ok["task"], status=STATUS_SUCCEEDED)
    bad = store.claim(log_id=log.id, stage="parse", chunk_no=1)
    store.finish(bad["task"], status=STATUS_FAILED, error="x")

    summary = store.summary(log.id)

    assert summary["tasks"] == 2
    assert summary["stages"]["parse"]["succeeded"] == 1
    assert summary["stages"]["parse"]["failed"] == 1
    assert summary["all_succeeded"] is False
    assert summary["failed_tasks"]
