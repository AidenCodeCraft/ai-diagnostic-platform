"""精排服务测试 —— 重排、归一化、失败降级。"""

import pytest

from app.services.knowledge import rerank_service


class FakeReranker:
    def __init__(self, mapping=None, raise_error=False):
        self.mapping = mapping or {}
        self.raise_error = raise_error
        self.calls = []

    def rerank(self, query, documents, top_k=5):
        self.calls.append({"query": query, "documents": documents, "top_k": top_k})
        if self.raise_error:
            raise RuntimeError("model exploded")
        scored = [(idx, self.mapping.get(idx, 0.0)) for idx in range(len(documents))]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


def _items(*texts):
    return [{"id": i + 1, "snippet": text, "relevance_score": 0.5} for i, text in enumerate(texts)]


@pytest.fixture(autouse=True)
def _reset_singleton():
    rerank_service.reset_reranker()
    yield
    rerank_service.reset_reranker()


def test_reorders_by_rerank_score_and_normalizes():
    items = _items("无关内容", "答案就在这一节", "弱相关")
    engine = FakeReranker(mapping={0: 0.1, 1: 0.9, 2: 0.3})

    result = rerank_service.rerank_items("问题", items, keep=3, reranker=engine)

    assert [item["id"] for item in result] == [2, 3, 1]
    assert result[0]["relevance_score"] == 1.0
    assert result[1]["relevance_score"] == pytest.approx(0.3333, abs=1e-3)
    assert result[0]["_rerank_score"] == pytest.approx(0.9)
    # 原始融合分保留下来，便于排查「精排把谁顶上来了」
    assert result[0]["_retrieval_score"] == 0.5


def test_inference_failure_falls_back_to_original_order():
    items = _items("a", "b", "c")
    engine = FakeReranker(raise_error=True)

    result = rerank_service.rerank_items("问题", items, keep=3, reranker=engine)

    assert [item["id"] for item in result] == [1, 2, 3]
    assert all("_rerank_score" not in item for item in result)


def test_missing_engine_is_passthrough(monkeypatch):
    monkeypatch.setattr(rerank_service, "get_reranker", lambda: None)
    items = _items("a", "b")

    result = rerank_service.rerank_items("问题", items, keep=2)

    assert [item["id"] for item in result] == [1, 2]


def test_only_top_n_candidates_are_reranked():
    items = _items(*[f"doc {i}" for i in range(10)])
    engine = FakeReranker(mapping={9: 1.0})

    result = rerank_service.rerank_items("问题", items, top_n=5, keep=2, reranker=engine)

    assert engine.calls[0]["top_k"] == 2
    assert len(engine.calls[0]["documents"]) == 5
    # 第 10 条不在精排范围内，因此不会出现
    assert all(item["id"] <= 5 for item in result)


def test_keep_limits_result_size():
    items = _items(*[f"doc {i}" for i in range(8)])
    engine = FakeReranker(mapping={i: 1.0 - i * 0.1 for i in range(8)})

    result = rerank_service.rerank_items("问题", items, top_n=8, keep=3, reranker=engine)

    assert len(result) == 3


def test_empty_inputs_are_safe():
    assert rerank_service.rerank_items("", _items("a")) == _items("a")
    assert rerank_service.rerank_items("问题", []) == []


def test_items_without_text_are_handled(monkeypatch):
    monkeypatch.setattr(rerank_service, "get_reranker", lambda: None)
    items = [{"id": 1}, {"id": 2}]
    assert rerank_service.rerank_items("问题", items, keep=2) == items


def test_score_threshold_filters_low_candidates(monkeypatch):
    items = _items("好", "差")
    engine = FakeReranker(mapping={0: 1.0, 1: 0.04})
    monkeypatch.setattr(rerank_service.settings, "RERANKER_SCORE_THRESHOLD", 0.2)

    result = rerank_service.rerank_items("问题", items, keep=2, reranker=engine)

    assert [item["id"] for item in result] == [1]
