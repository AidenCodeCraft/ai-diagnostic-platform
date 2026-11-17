"""分析任务异步化：任务创建、后台状态流转。"""

from app.models import Analysis, Log
from app.services.diagnostics import analysis_task_service as task_module
from app.services.diagnostics.analysis_task_service import AnalysisTaskService


def _make_log(db_session, tmp_path) -> Log:
    path = tmp_path / "a.log"
    path.write_text("boot ok\nusb timeout error\n", encoding="utf-8")
    log = Log(filename="a.log", file_path=str(path), size=path.stat().st_size, status="uploaded")
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


class _RecorderExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))


class TestAnalysisAsync:
    def test_run_analysis_async_returns_pending(self, db_session, tmp_path, monkeypatch):
        log = _make_log(db_session, tmp_path)
        recorder = _RecorderExecutor()
        monkeypatch.setattr(task_module, "_EXECUTOR", recorder)

        result = AnalysisTaskService(db_session).run_analysis_async(
            log.id, model="mock", user_query="USB 超时",
        )

        assert result["status"] == "pending"
        assert result["id"] > 0
        assert recorder.calls
        _, args = recorder.calls[0]
        assert args == (result["id"], "USB 超时")

        analysis = db_session.query(Analysis).filter(Analysis.id == result["id"]).first()
        assert analysis is not None
        assert analysis.status == "pending"

    def test_execute_async_marks_completed(self, db_session, tmp_path, monkeypatch):
        log = _make_log(db_session, tmp_path)
        analysis = AnalysisTaskService(db_session).create_analysis(log.id, model="mock")

        monkeypatch.setattr(
            AnalysisTaskService, "_execute_analysis",
            lambda self, analysis, user_query="", on_progress=None: {"summary": "ok"},
        )
        AnalysisTaskService._execute_async(int(analysis.id), "")

        db_session.expire_all()
        refreshed = db_session.query(Analysis).filter(Analysis.id == analysis.id).first()
        assert refreshed.status == "completed"

    def test_execute_async_marks_failed(self, db_session, tmp_path, monkeypatch):
        log = _make_log(db_session, tmp_path)
        analysis = AnalysisTaskService(db_session).create_analysis(log.id, model="mock")

        def _boom(self, analysis, user_query="", on_progress=None):
            raise RuntimeError("pipeline exploded")

        monkeypatch.setattr(AnalysisTaskService, "_execute_analysis", _boom)
        AnalysisTaskService._execute_async(int(analysis.id), "")

        db_session.expire_all()
        refreshed = db_session.query(Analysis).filter(Analysis.id == analysis.id).first()
        assert refreshed.status == "failed"
        assert "pipeline exploded" in (refreshed.error_message or "")

    def test_execute_async_watchdog_times_out_stuck_tasks(self, db_session, tmp_path, monkeypatch):
        """看门狗：卡死的分析任务必须落到 failed，不能永远停留在 running。"""
        log = _make_log(db_session, tmp_path)
        analysis = AnalysisTaskService(db_session).create_analysis(log.id, model="mock")

        import time

        def _hang(self, analysis, user_query="", on_progress=None):
            time.sleep(1.5)
            return {"summary": "late"}

        monkeypatch.setattr(AnalysisTaskService, "_execute_analysis", _hang)
        monkeypatch.setattr(task_module, "ANALYSIS_TIMEOUT_SECONDS", 0)
        AnalysisTaskService._execute_async(int(analysis.id), "")

        db_session.expire_all()
        refreshed = db_session.query(Analysis).filter(Analysis.id == analysis.id).first()
        assert refreshed.status == "failed"
        assert "超时" in (refreshed.error_message or "")

    def test_execute_async_reports_stage_progress(self, db_session, tmp_path, monkeypatch):
        """阶段进度写入 summary（"[进度] …"），供前端思维链呈现 Agent 进度。"""
        log = _make_log(db_session, tmp_path)
        analysis = AnalysisTaskService(db_session).create_analysis(log.id, model="mock")

        monkeypatch.setattr(
            AnalysisTaskService, "_execute_analysis",
            lambda self, analysis, user_query="", on_progress=None: (
                on_progress("④ 知识库检索相关案例…") if on_progress else None
            ) or {"summary": "done"},
        )
        AnalysisTaskService._execute_async(int(analysis.id), "")

        db_session.expire_all()
        refreshed = db_session.query(Analysis).filter(Analysis.id == analysis.id).first()
        assert refreshed.status == "completed"
        # 进度回调写入了 [进度] 标记（真实流水线会在结束时用结果覆盖 summary）
        assert refreshed.summary == "[进度] ④ 知识库检索相关案例…"
