"""批量分析任务。"""

from app.models import Log
from app.services.diagnostics import analysis_task_service as task_module
from app.services.diagnostics.analysis_task_service import AnalysisTaskService


class _RecorderExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))


def _make_log(db_session, tmp_path, name: str) -> Log:
    path = tmp_path / name
    path.write_text("boot ok\nusb timeout error\n", encoding="utf-8")
    log = Log(filename=name, file_path=str(path), size=path.stat().st_size, status="uploaded")
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


class TestBatchAnalysis:
    def test_batch_creates_pending_tasks(self, db_session, tmp_path, monkeypatch):
        log1 = _make_log(db_session, tmp_path, "a.log")
        log2 = _make_log(db_session, tmp_path, "b.log")
        recorder = _RecorderExecutor()
        monkeypatch.setattr(task_module, "_EXECUTOR", recorder)

        result = AnalysisTaskService(db_session).run_batch_async(
            [int(log1.id), int(log2.id)], model="mock", user_query="usb",
        )

        assert result["total"] == 2
        assert [item["status"] for item in result["items"]] == ["pending", "pending"]
        assert len(recorder.calls) == 2

    def test_batch_keeps_going_after_invalid_log(self, db_session, tmp_path, monkeypatch):
        log1 = _make_log(db_session, tmp_path, "a.log")
        recorder = _RecorderExecutor()
        monkeypatch.setattr(task_module, "_EXECUTOR", recorder)

        result = AnalysisTaskService(db_session).run_batch_async(
            [int(log1.id), 999999], model="mock",
        )

        assert result["items"][0]["status"] == "pending"
        assert result["items"][1]["status"] == "failed"
        assert "log not found" in result["items"][1]["error"]
