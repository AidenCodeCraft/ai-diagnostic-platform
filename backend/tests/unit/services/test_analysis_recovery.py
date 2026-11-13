"""异步分析任务的中断恢复与重试。"""

from datetime import datetime, timedelta, timezone

from app.models import Analysis, Log
from app.services.diagnostics import analysis_task_service as task_module
from app.services.diagnostics.analysis_task_service import AnalysisTaskService


class _RecorderExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))


def _make_log(db_session, tmp_path) -> Log:
    path = tmp_path / "a.log"
    path.write_text("boot ok\nusb timeout error\n", encoding="utf-8")
    log = Log(filename="a.log", file_path=str(path), size=path.stat().st_size, status="uploaded")
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


def _make_analysis(db_session, log, status: str, age_minutes: int = 0) -> Analysis:
    analysis = Analysis(log_id=log.id, status=status, model="mock")
    db_session.add(analysis)
    db_session.commit()
    db_session.refresh(analysis)
    if age_minutes:
        analysis.updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=age_minutes)
        db_session.commit()
    return analysis


class TestAnalysisRecovery:
    def test_recover_marks_stale_tasks_failed(self, db_session, tmp_path):
        log = _make_log(db_session, tmp_path)
        stale = _make_analysis(db_session, log, "running", age_minutes=60)

        count = AnalysisTaskService.recover_interrupted(db_session)
        db_session.refresh(stale)

        assert count == 1
        assert stale.status == "failed"
        assert "中断" in (stale.error_message or "")

    def test_recover_skips_recent_tasks(self, db_session, tmp_path):
        log = _make_log(db_session, tmp_path)
        recent = _make_analysis(db_session, log, "running")

        count = AnalysisTaskService.recover_interrupted(db_session)
        db_session.refresh(recent)

        assert count == 0
        assert recent.status == "running"


class TestAnalysisRetry:
    def test_retry_submits_failed_task(self, db_session, tmp_path, monkeypatch):
        log = _make_log(db_session, tmp_path)
        analysis = _make_analysis(db_session, log, "failed")
        analysis.error_message = "boom"
        db_session.commit()

        recorder = _RecorderExecutor()
        monkeypatch.setattr(task_module, "_EXECUTOR", recorder)

        result = AnalysisTaskService(db_session).retry_analysis(int(analysis.id))
        db_session.refresh(analysis)

        assert result["status"] == "pending"
        assert analysis.status == "pending"
        assert analysis.error_message is None
        assert recorder.calls

    def test_retry_rejects_running_task(self, db_session, tmp_path):
        log = _make_log(db_session, tmp_path)
        analysis = _make_analysis(db_session, log, "running")
        try:
            AnalysisTaskService(db_session).retry_analysis(int(analysis.id))
        except ValueError as exc:
            assert "重试" in str(exc)
        else:
            raise AssertionError("expected ValueError")
