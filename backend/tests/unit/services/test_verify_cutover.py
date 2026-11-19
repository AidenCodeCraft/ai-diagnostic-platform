"""v3 切流脚本的纯函数测试（不连 Milvus）。"""

from scripts.verify_v3_cutover import _acceptance_hit, _check_hits


def hit(title="FAQ", section="第 5 节 日志检索", chunk_type="section", source="knowledge"):
    return {"title": title, "section": section, "chunk_type": chunk_type, "source": source}


def test_check_hits_accepts_pure_section_results():
    result = _check_hits([hit(), hit(section="第 6 节")])
    assert result["ok"] is True
    assert result["chunk_types"] == ["section"]


def test_check_hits_rejects_log_chunks():
    result = _check_hits([hit(chunk_type="error", source="log:7")])
    assert result["ok"] is False
    assert result["chunk_types"] == ["error"]


def test_check_hits_fails_on_empty_recall():
    assert _check_hits([])["ok"] is False


def test_acceptance_matches_expected_doc_and_section():
    result = _acceptance_hit([hit()], "FAQ", "第 5 节")
    assert result["ok"] is True
    assert result["rank"] == 1


def test_acceptance_reports_old_failure_shape():
    """旧实现只召回《线路》第 1 节——必须判失败并回传 top5 便于定位。"""
    hits = [hit(title="线路", section="第 1 节 线路命名"), hit(title="FAQ", section="第 2 节")]
    result = _acceptance_hit(hits, "FAQ", "第 5 节")

    assert result["ok"] is False
    assert result["top5"][0]["title"] == "线路"


def test_acceptance_skipped_without_expectations():
    assert _acceptance_hit([hit()], None, None)["ok"] is None
