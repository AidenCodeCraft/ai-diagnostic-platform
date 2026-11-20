"""章节级混合检索 — BM25 与向量在同一粒度上融合（RRF）。

统一口径的原因：
    BM25 按章节建索引、向量按章节写入，如果融合时一边按文档、一边按章节，
    分数就不可比（同一文档的多个章节会互相掩盖）。这里所有环节都以
    `SectionChunk.key` 为唯一标识：BM25 命中、向量命中、最终排序、引用编号
    全部对齐。

不做的两件事（曾经的弯路）：
    - 不用中文 n-gram 覆盖率给章节「结构提权」：换问法即失效，属于刷测试题；
    - 不比 BM25 与向量的原始分：量纲不同，一律用 RRF 按名次融合。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.services.knowledge.sections import (
    MIN_SECTION_CHARS,
    content_hash,
    section_key,
    split_markdown_sections,
)

DEFAULT_RRF_K = 60
DEFAULT_CANDIDATES = 50
_SEP = chr(10)  # 换行符（避免在源码里写转义）


@dataclass
class SectionChunk:
    doc_id: int
    chunk_no: int
    title: str
    section: str
    content: str
    index_text: str
    key: str
    content_hash: str


def build_section_chunks(docs: Iterable[Any]) -> List[SectionChunk]:
    """把文档切成章节块。

    必须与向量写入使用**同一个**切分实现（`VectorService._build_chunks`）：
    此前这里另写了一套循环，结果 BM25 语料与向量集合的 content_hash 对不上，
    向量命中只能映射回 9/30 条，语义那一路等于废掉。
    """
    from app.services.knowledge.vector_service import VectorService

    chunks: List[SectionChunk] = []
    for doc in docs:
        doc_id = int(getattr(doc, "id", 0) or 0)
        if not doc_id:
            continue
        title = str(getattr(doc, "title", "") or "")
        _title, built = VectorService._build_chunks(
            doc_id, str(getattr(doc, "content", "") or ""), doc_title=title,
        )
        for chunk_no, chunk in enumerate(built):
            body = (chunk.get("content") or "").strip()
            if len(body) < MIN_SECTION_CHARS:
                continue
            heading = (chunk.get("section") or "").strip()
            index_text = chunk.get("index_text") or _SEP.join([title, heading, body])
            chunks.append(SectionChunk(
                doc_id=doc_id,
                chunk_no=chunk_no,
                title=title,
                section=heading,
                content=body,
                index_text=str(index_text).strip(),
                key=section_key(doc_id, heading, chunk_no),
                content_hash=str(chunk.get("content_hash") or ""),
            ))
    return chunks


def corpus_signature(docs: Iterable[Any]) -> str:
    """语料签名：文档集合或其更新时间变化时，BM25 索引必须重建。"""
    parts = []
    for doc in docs:
        updated = getattr(doc, "updated_at", None)
        parts.append(f"{getattr(doc, 'id', 0)}:{updated.isoformat() if updated else ''}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


class SectionBM25Index:
    """进程内 BM25 索引（按语料签名缓存，避免每次请求重建）。"""

    def __init__(self) -> None:
        self._signature: Optional[str] = None
        self._chunks: List[SectionChunk] = []
        self._bm25: Any = None

    def ensure(self, chunks: List[SectionChunk], signature: str) -> None:
        if signature == self._signature and self._bm25 is not None:
            return
        self._chunks = chunks
        self._signature = signature
        self._bm25 = None
        if not chunks:
            return
        try:
            # BM25Plus：IDF = log((N+1)/n) 恒为正。Okapi 在小语料/高频词上
            # IDF 会算成 0，导致整库检索全空（新建库、只有几篇文档时必踩）。
            from rank_bm25 import BM25Plus
        except ImportError:  # pragma: no cover - requirements 已固定依赖
            return
        from app.services.knowledge.retrievers import BM25Retriever

        tokenized = [BM25Retriever._tokenize(chunk.index_text) for chunk in chunks]
        self._bm25 = BM25Plus(tokenized)

    def retrieve(self, query: str, top_k: int = DEFAULT_CANDIDATES) -> List[Tuple[int, float]]:
        if self._bm25 is None or not self._chunks:
            return []
        from app.services.knowledge.retrievers import BM25Retriever

        scores = self._bm25.get_scores(BM25Retriever._tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
        return [(idx, float(score)) for idx, score in ranked[:top_k] if score > 0]


def map_dense_hits(chunks: List[SectionChunk], dense_hits: List[Dict[str, Any]]) -> List[int]:
    """把向量检索结果映射回章节块下标（按 content_hash 对齐）。

    对不上的（旧集合遗留向量、章节已被改写）直接丢弃并计数，不参与融合——
    宁可少一路召回，也不要让错位的向量把无关章节顶上来。
    """
    if not chunks or not dense_hits:
        return []
    by_hash = {chunk.content_hash: idx for idx, chunk in enumerate(chunks)}
    ordered: List[int] = []
    seen = set()
    for hit in dense_hits:
        digest = content_hash(
            str(hit.get("title") or ""),
            str(hit.get("section") or ""),
            str(hit.get("content") or "").strip(),
        )
        idx = by_hash.get(digest)
        if idx is None or idx in seen:
            continue
        seen.add(idx)
        ordered.append(idx)
    return ordered


def fuse_rrf(
    rankings: List[List[int]],
    k: int = DEFAULT_RRF_K,
    weights: Optional[List[float]] = None,
) -> Dict[int, float]:
    """加权 Reciprocal Rank Fusion。

    默认等权；weights 用于表达「更信任哪一路」（BM25 强于专有名词、向量强于同义表达）。
    只依赖名次，避免 BM25 与向量的原始分数量纲不可比。
    """
    fused: Dict[int, float] = {}
    for position, ranking in enumerate(rankings):
        weight = 1.0
        if weights is not None and position < len(weights):
            weight = float(weights[position])
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + weight / (k + rank + 1)
    return fused


def rank_sections(
    chunks: List[SectionChunk],
    *,
    query: str,
    dense_hits: Optional[List[Dict[str, Any]]] = None,
    bm25_index: Optional[SectionBM25Index] = None,
    top_k: int = DEFAULT_CANDIDATES,
    rrf_k: int = DEFAULT_RRF_K,
    weights: Optional[List[float]] = None,
    with_raw: bool = False,
) -> List[Tuple]:
    """章节级 RRF 融合。

    默认返回 [(chunk, 归一化分)]（最高 1.0，便于展示与阈值判断）；
    with_raw=True 时返回 [(chunk, 归一化分, 原始RRF分)] ——
    归一化分在「多层检索再合并」后每层各自变成 1.0，失去可比性，
    原始 RRF 分才是能跨层比较、能用来调排序的那个数。
    """
    if not chunks or not (query or "").strip():
        return []

    sparse: List[Tuple[int, float]] = []
    if bm25_index is None:
        bm25_index = SectionBM25Index()
        bm25_index.ensure(chunks, "adhoc")
    if bm25_index is not None:
        sparse = bm25_index.retrieve(query, top_k)

    dense = map_dense_hits(chunks, list(dense_hits or []))

    rankings = [[idx for idx, _ in sparse]]
    if dense:
        rankings.append(dense)

    fused = fuse_rrf(rankings, k=rrf_k, weights=weights)
    if not fused:
        return []

    top_score = max(fused.values()) or 1.0
    ordered = sorted(fused.items(), key=lambda pair: pair[1], reverse=True)
    if with_raw:
        return [
            (chunks[idx], score / top_score, float(score))
            for idx, score in ordered
            if 0 <= idx < len(chunks)
        ]
    return [(chunks[idx], score / top_score) for idx, score in ordered if 0 <= idx < len(chunks)]
