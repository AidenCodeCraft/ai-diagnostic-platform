"""RAG 引擎 — 统一的检索增强生成管道。

基于 DeepSeek RAG 架构重构，实现完整的检索漏斗：
  1. Query Understanding → 查询预处理
  2. Hybrid Retrieval → Dense + Sparse 混合检索
  3. Reranking → Cross-Encoder 精排 + MMR 去重
  4. Context Assembly → 上下文组装
  5. LLM Generation → 生成 + 引用校验

完全替换旧的 rag_service.py，保持相同的公开 API 签名以兼容现有调用方。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.services.core.interfaces import (
    IEmbedder, IRetriever, IReranker,
    SearchResult, RetrievalOutput, Chunk,
)
from app.services.core.config import RAGConfig, DEFAULT_CONFIG
from app.services.rag.rag_prompt import (
    RAG_STRICT_SYSTEM_PROMPT,
    RAG_NO_MATCH_RESPONSE,
)

logger = get_logger(__name__)

# 相关度阈值
RELEVANCE_THRESHOLD = 0.05
MIN_MATCH_DOCS = 1
SEARCH_PAGE_SIZE = 5


class RAGService:
    """RAG 引擎 — 统一入口，替换旧实现。

    保持与旧 RAGService 完全相同的 API 签名：
      rag = RAGService(db, model="deepseek-v4-flash")
      result = rag.answer("设备黑屏怎么办？")
      for chunk in rag.answer_stream("设备黑屏怎么办？"):
          ...

    Usage:
        rag = RAGService(db)
        result = rag.answer("启迪云控平台车辆上线问题")
    """

    def __init__(self, db: Session, model: Optional[str] = None):
        self.db = db
        self.model = model
        self.config = DEFAULT_CONFIG

        # 延迟初始化重型组件
        self._embedder: Optional[IEmbedder] = None
        self._retriever: Optional[IRetriever] = None
        self._reranker: Optional[IReranker] = None

    # ==================================================================
    # 公开 API — 与旧版完全兼容
    # ==================================================================

    def answer(self, query: str) -> Dict[str, Any]:
        """执行 RAG 问答管道。

        Returns:
            {"answer": str, "sources": list, "from_knowledge_base": bool,
             "match_count": int, "pipeline_stages": dict}
        """
        if not query or not query.strip():
            return self._empty_response("输入为空")

        logger.info("[RAG] Pipeline start: query=%.80s", query)

        # Stage 1+2+3: 检索 → 融合 → 精排
        output = self.retrieve(query)

        if not output.results:
            logger.info("[RAG] No results found")
            return {
                "answer": RAG_NO_MATCH_RESPONSE,
                "sources": [],
                "from_knowledge_base": False,
                "match_count": 0,
                "pipeline_stages": output.pipeline_stages,
            }

        # Stage 4: 上下文组装
        context = self._build_context(query, output.results)

        # Stage 5: LLM 生成
        answer = self._generate(context)

        # 检查 LLM 是否遵守约束
        from_kb = RAG_NO_MATCH_RESPONSE not in answer

        sources = [
            {
                "id": r.chunk.doc_id,
                "title": r.chunk.doc_title or "Untitled",
                "excerpt": r.chunk.text[:300],
                "score": round(r.score, 4),
            }
            for r in output.results
        ]

        return {
            "answer": answer,
            "sources": sources,
            "from_knowledge_base": from_kb,
            "match_count": len(output.results),
            "pipeline_stages": output.pipeline_stages,
        }

    def answer_stream(self, query: str) -> Generator[Dict[str, Any], None, None]:
        """流式 RAG 回答（SSE 事件）。

        Yields:
            {"type": "sources", "data": [...]}
            {"type": "content", "data": "文本片段"}
            {"type": "done", "data": None}
        """
        if not query or not query.strip():
            yield {"type": "content", "data": RAG_NO_MATCH_RESPONSE}
            yield {"type": "done", "data": None}
            return

        output = self.retrieve(query)

        # 发送 sources
        sources_data = [
            {
                "id": r.chunk.doc_id,
                "title": r.chunk.doc_title or "Untitled",
                "excerpt": r.chunk.text[:300],
                "score": round(r.score, 4),
            }
            for r in output.results
        ]
        yield {"type": "sources", "data": sources_data}

        if not output.results:
            yield {"type": "content", "data": RAG_NO_MATCH_RESPONSE}
            yield {"type": "done", "data": None}
            return

        context = self._build_context(query, output.results)

        for chunk in self._generate_stream(context):
            yield chunk

        yield {"type": "done", "data": None}

    # ==================================================================
    # 检索管道
    # ==================================================================

    def retrieve(self, query: str) -> RetrievalOutput:
        """完整检索管道: Embed → Retrieve → Rerank → Diversify"""
        t0 = time.time()
        stages: Dict[str, float] = {}

        if not query.strip():
            return RetrievalOutput(query=query, pipeline_stages=stages)

        retriever = self._get_retriever()
        reranker = self._get_reranker()

        # Stage 1+2: 混合检索（粗排）
        t1 = time.time()
        candidates = retriever.retrieve(query, top_k=self.config.retrieval.hybrid_top_k)
        stages["retrieval_ms"] = round((time.time() - t1) * 1000, 1)

        if not candidates:
            return RetrievalOutput(
                query=query, total_candidates=0, total_retrieved=0,
                latency_ms=(time.time()-t0)*1000, pipeline_stages=stages,
            )

        # Stage 3: Reranker 精排
        t2 = time.time()
        if reranker.health_check() and self.config.reranker.enabled:
            doc_texts = [r.chunk.text for r in candidates]
            reranked = reranker.rerank(query, doc_texts, top_k=min(
                self.config.reranker.top_k * 2, len(doc_texts),
            ))
            for idx, rerank_score in reranked:
                candidates[idx].rerank_score = rerank_score
                candidates[idx].score = rerank_score
            candidates.sort(key=lambda x: x.score, reverse=True)
        stages["rerank_ms"] = round((time.time() - t2) * 1000, 1)

        # Stage 3.5: LLM 辅助重排序（Cross-Encoder 置信度不足时触发）
        if self.config.reranker.llm_fallback_enabled:
            t2_5 = time.time()
            ce_scores = [r.rerank_score for r in candidates if r.rerank_score > 0]
            try:
                from app.services.knowledge.llm_reranker import LLMReranker
                llm_reranker = LLMReranker(
                    model=self.model or "deepseek-chat",
                    confidence_threshold=self.config.reranker.llm_fallback_threshold,
                    timeout=self.config.reranker.llm_fallback_timeout,
                )
                llm_ranked = llm_reranker.rerank(
                    query=query,
                    documents=[(i, r.chunk.text) for i, r in enumerate(candidates)],
                    cross_encoder_scores=ce_scores,
                    top_k=self.config.reranker.top_k,
                )
                if llm_ranked:
                    # LLM 重排序结果替换 Cross-Encoder 排序
                    for idx, llm_score in llm_ranked:
                        if 0 <= idx < len(candidates):
                            candidates[idx].score = llm_score
                    candidates.sort(key=lambda x: x.score, reverse=True)
                    stages["llm_rerank_ms"] = round((time.time() - t2_5) * 1000, 1)
            except Exception as e:
                logger.debug("[RAG] LLM reranker skipped: %s", e)

        # Stage 4: 截断
        final = candidates[:self.config.reranker.top_k]

        total_ms = (time.time() - t0) * 1000
        logger.info(
            "[RAG] Pipeline done: query=%.50s candidates=%d final=%d %.0fms",
            query, len(candidates), len(final), total_ms,
        )

        return RetrievalOutput(
            query=query, results=final,
            total_candidates=len(candidates), total_retrieved=len(final),
            latency_ms=round(total_ms, 1), pipeline_stages=stages,
        )

    # ==================================================================
    # 上下文组装
    # ==================================================================

    def _build_context(self, query: str, results: List[SearchResult]) -> str:
        """组装 RAG 上下文，按模型感知的 token 预算填充。

        不限制文档数量，不限制单篇文档大小。
        按相关度从高到低填充，超出预算则停止。
        """
        # 模型感知的动态预算
        model = self.model or "deepseek-chat"
        try:
            from app.services.core.token_counter import get_token_counter
            max_tokens = self.config.context.get_rag_budget(model)
        except Exception:
            max_tokens = self.config.context.max_tokens

        parts = []
        total_tokens = 0

        for i, r in enumerate(results):
            title = r.chunk.doc_title or "Untitled"
            header = f"{i + 1}. **{title}** (相关度: {r.score:.0%})\n   "

            # 估算 header + text 的 token 数
            header_tokens = self._estimate_single_text_tokens(header)
            text_tokens = self._estimate_single_text_tokens(r.chunk.text)

            if total_tokens + header_tokens + text_tokens > max_tokens:
                # 尝试截断文本以适配剩余预算
                remaining = max_tokens - total_tokens - header_tokens
                if remaining > 50:  # 至少保留 50 tokens 才有意义
                    truncated = self._truncate_text_to_tokens(r.chunk.text, remaining)
                    total_tokens += header_tokens + self._estimate_single_text_tokens(truncated)
                    parts.append(header + truncated)
                else:
                    logger.info(
                        "[RAG] Token budget exhausted at doc %d/%d (%d/%d tokens)",
                        i, len(results), total_tokens, max_tokens,
                    )
                break

            total_tokens += header_tokens + text_tokens
            parts.append(header + r.chunk.text)

        context = "\n\n".join(parts)
        logger.info(
            "[RAG] Context: %d/%d docs, ~%d tokens (budget: %d tokens, model: %s)",
            len(parts), len(results), total_tokens, max_tokens, model,
        )
        return context

    def _estimate_single_text_tokens(self, text: str) -> int:
        """估算单段文本的 token 数。"""
        try:
            from app.services.core.token_counter import get_token_counter
            return get_token_counter().count(text, model=self.model or "default")
        except Exception:
            return int(len(text) * 0.6)

    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        """将文本截断到指定 token 数以内。"""
        if max_tokens <= 0:
            return ""
        # 保守策略：按 1 token ≈ 0.6 中文字符 截断
        max_chars = int(max_tokens / 0.6)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "…"

    # ==================================================================
    # LLM 生成
    # ==================================================================

    def _generate(self, context: str) -> str:
        try:
            from app.services.knowledge.provider_registry import ProviderRegistry
            from app.core.config import settings
            provider = ProviderRegistry().get_provider(self.model or settings.LLM_PROVIDER)
            return provider.chat([
                {"role": "system", "content": RAG_STRICT_SYSTEM_PROMPT},
                {"role": "user", "content": f"## 知识库检索结果\n\n{context}"},
            ])
        except Exception as e:
            logger.error("[RAG] Generation failed: %s", e)
            return f"生成回答时发生错误: {e}"

    def _generate_stream(self, context: str) -> Generator[Dict[str, Any], None, None]:
        try:
            from app.services.knowledge.provider_registry import ProviderRegistry
            from app.core.config import settings
            provider = ProviderRegistry().get_provider(self.model or settings.LLM_PROVIDER)
            for chunk in provider.chat_stream([
                {"role": "system", "content": RAG_STRICT_SYSTEM_PROMPT},
                {"role": "user", "content": f"## 知识库检索结果\n\n{context}"},
            ]):
                if isinstance(chunk, str):
                    yield {"type": "content", "data": chunk}
                elif isinstance(chunk, dict):
                    yield chunk
        except Exception as e:
            logger.error("[RAG] Stream generation failed: %s", e)
            yield {"type": "error", "data": str(e)}

    # ==================================================================
    # 组件懒加载（避免启动时加载重型模型）
    # ==================================================================

    def _get_embedder(self) -> IEmbedder:
        if self._embedder is None:
            from app.services.knowledge.embedding import EmbeddingService
            self._embedder = EmbeddingService(self.config.embedding)
        return self._embedder

    def _get_retriever(self) -> IRetriever:
        if self._retriever is None:
            from app.services.knowledge.retrievers import (
                MilvusRetriever, BM25Retriever, HybridRetriever,
            )
            dense = MilvusRetriever()
            sparse = BM25Retriever()
            self._build_bm25_index(sparse)
            self._retriever = HybridRetriever(dense, sparse, self.config.retrieval)
        return self._retriever

    def _get_reranker(self) -> IReranker:
        if self._reranker is None:
            from app.services.knowledge.rerankers import CrossEncoderReranker
            self._reranker = CrossEncoderReranker(self.config.reranker)
        return self._reranker

    def _build_bm25_index(self, bm25) -> None:
        """从知识库构建 BM25 索引"""
        try:
            from app.services.knowledge.knowledge_service import KnowledgeService
            ks = KnowledgeService(self.db)
            docs = ks.list(page=1, page_size=1000)
            items = docs.get("items", [])
            if items:
                bm25.index([
                    (int(doc.id), f"{doc.title or ''}\n{doc.content or ''}")
                    for doc in items
                ])
        except Exception as e:
            logger.warning("[RAG] BM25 index build failed: %s", e)

    # ==================================================================
    # 辅助
    # ==================================================================

    def _empty_response(self, reason: str = "") -> Dict[str, Any]:
        return {
            "answer": RAG_NO_MATCH_RESPONSE,
            "sources": [],
            "from_knowledge_base": False,
            "match_count": 0,
            "detail": reason,
        }

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "embedder": self._get_embedder().health_check(),
            "retriever": self._get_retriever().health_check(),
            "reranker": self._get_reranker().health_check(),
        }
