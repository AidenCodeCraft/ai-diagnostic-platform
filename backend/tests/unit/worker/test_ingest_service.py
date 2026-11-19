"""日志处理纯逻辑测试（P2 步骤 1）。"""

from app.worker.ingest_service import (
    MAX_CHUNKS,
    ChunkPlan,
    mask_variables,
    normalize_line,
    plan_chunks,
    stage_progress,
    template_id,
    template_source,
)


def test_plan_chunks_covers_whole_file():
    plans = plan_chunks(120, chunk_bytes=50)
    assert [plan.index for plan in plans] == [0, 1, 2]
    assert [plan.length for plan in plans] == [50, 50, 20]
    assert plans[-1].end == 120


def test_plan_chunks_single_small_file():
    plans = plan_chunks(10, chunk_bytes=1024)
    assert plans == [ChunkPlan(index=0, start=0, length=10)]


def test_plan_chunks_empty_file():
    assert plan_chunks(0) == [ChunkPlan(index=0, start=0, length=0)]


def test_plan_chunks_caps_chunk_count():
    plans = plan_chunks(10 * 1024 * 1024, chunk_bytes=1)
    assert len(plans) == MAX_CHUNKS


def test_mask_variables_replaces_unstable_tokens():
    line = "2026-08-02 14:20:00 client 192.168.1.7 hex 0x9f3a guid 123e4567-e89b-12d3-a456-426614174000 seq 123456"
    masked = mask_variables(line)

    assert "<TS>" in masked
    assert "<IP>" in masked
    assert "<HEX>" in masked
    assert "<GUID>" in masked
    assert "<NUM>" in masked
    assert "192.168.1.7" not in masked


def test_mask_keeps_enums_and_commands():
    line = "[NL668_4G] pri:  AT+CGDCONT? CHINA MOBILE"
    masked = mask_variables(line)
    assert "AT+CGDCONT" in masked
    assert "CHINA MOBILE" in masked


def test_normalize_line_parses_timestamp_and_module():
    record = normalize_line("[2026-08-02 14:20:00]  [NL668_4G_GetRegSta.. 0719] pri:  AT+CGDCONT? empty")

    assert record is not None
    assert record["ts"] == "2026-08-02 14:20:00"
    assert record["module"].startswith("NL668_4G_GetRegSta..")
    assert "AT+CGDCONT" in record["text"]


def test_normalize_line_skips_stack_traces():
    assert normalize_line("    at com.example.Task.run(Task.java:42)") is None


def test_template_id_is_stable_for_same_shape():
    first = template_id("[APP] Volume:27, 20, 20")
    second = template_id("[APP] Volume:11, 5, 5")

    assert first == second, "数值不同但结构相同的行应归为同一模板"


def test_template_id_differs_for_different_shape():
    assert template_id("[APP] Volume:27") != template_id("[APP] Network registered")


def test_template_source_is_reported():
    source = template_source()
    assert source in ("drain3", "fallback-hash")
    if source == "fallback-hash":
        assert template_id("[APP] x").startswith("h:")


def test_stage_progress_percentages():
    assert stage_progress("parse", 3, 4)["percent"] == 75
    assert stage_progress("parse", 0, 0)["percent"] == 0
    assert stage_progress("parse", 10, 4)["percent"] == 100
