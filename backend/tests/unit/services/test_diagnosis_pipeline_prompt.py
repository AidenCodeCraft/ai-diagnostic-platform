"""诊断流水线：Prompt 构建、无支撑结论、阶段进度回调。"""

from app.services.diagnostics.diagnosis_pipeline import DiagnosisPipeline


def _make_pipeline(db_session):
    return DiagnosisPipeline(db_session, model="mock")


class TestDiagnosisPrompt:
    def test_build_prompt_contains_user_question_and_output_schema(self, db_session):
        """Prompt 必须自带用户问题与输出 schema（Provider 层不再二次包装/截断）。"""
        pipeline = _make_pipeline(db_session)
        prompt = pipeline._build_prompt(
            events=[{"module": "usb", "message": "timeout"}],
            error_events=[{"module": "usb", "message": "timeout"}],
            rule_summary="未匹配到已知规则。",
            knowledge_summary="未找到相关知识库案例。",
            trimmed_log="usb timeout",
            user_query="USB 超时怎么处理",
        )
        assert "## 用户问题" in prompt
        assert "USB 超时怎么处理" in prompt
        # 输出字段 schema 必须随 Prompt 下发，LLM 才能产出可解析 JSON
        for field in ("summary", "root_cause", "confidence", "next_steps", "evidence"):
            assert field in prompt

    def test_no_support_result_references_user_query(self, db_session):
        """无知识库支撑时的结论必须引用用户的问题，而非只给通用话术。"""
        pipeline = _make_pipeline(db_session)
        result = pipeline._no_support_result(
            events=[], error_events=[], detections=[],
            knowledge_results=[], rule_suggestions=[],
            user_query="设备黑屏怎么办",
        )
        assert result["support_missing"] is True
        assert "设备黑屏怎么办" in result["summary"]

    def test_run_reports_stage_progress(self, db_session, tmp_path):
        """run(on_stage=...) 逐阶段上报进度，且无证据时走无结论路径。"""
        log_path = tmp_path / "a.log"
        log_path.write_text("boot ok\nusb timeout error\n", encoding="utf-8")

        stages: list = []
        result = _make_pipeline(db_session).run(
            str(log_path), user_query="USB 超时", on_stage=stages.append,
        )

        assert result["support_missing"] is True
        assert any("解析日志" in s for s in stages)
        assert any("知识库" in s for s in stages)
