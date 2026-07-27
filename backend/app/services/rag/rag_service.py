"""RAG (Retrieval-Augmented Generation) 强制检索服务。

核心流程：
  1. 检索：强制从私域知识库检索相关文档
  2. 过滤：按相关度阈值过滤，只保留高质量匹配
  3. 约束：注入严格系统提示词，限定 LLM 只做语言重组
  4. 回退：无匹配时返回「知识库暂无信息」响应

与现有 DiagnosticChatAgent/DiagnosisPipeline 的差异：
  - 本模块是「严格 RAG」：回答必须 100% 来自知识库
  - 现有模块是「增强对话」：知识库作为上下文参考，LLM 可自行发挥
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.infrastructure.llm_service import LLMService
from app.services.rag.rag_prompt import (
    RAG_STRICT_SYSTEM_PROMPT,
    RAG_NO_MATCH_RESPONSE,
    RAG_PARTIAL_MATCH_HINT,
)

logger = get_logger(__name__)

# 相关度阈值：低于此值的文档将被过滤
RELEVANCE_THRESHOLD = 0.05
# 最少匹配文档数：低于此值视为无匹配
MIN_MATCH_DOCS = 1
# 检索文档数量
SEARCH_PAGE_SIZE = 5


class RAGService:
    """严格 RAG 管道——回答必须来源于检索到的知识库内容。

    Usage:
        rag = RAGService(db, model="deepseek-v4-flash")
        result = rag.answer("设备黑屏怎么办？")
        # result = {
        #     "answer": "...",           # 基于知识库的回答
        #     "sources": [...],          # 参考来源
        #     "from_knowledge_base": True,  # 是否来自知识库
        #     "match_count": 3,          # 匹配文档数
        # }
    """

    def __init__(self, db: Session, model: Optional[str] = None):
        self.db = db
        self.model = model
        self.knowledge = KnowledgeService(db)

    # ==================================================================
    # Public API
    # ==================================================================

    def answer(self, query: str) -> Dict[str, Any]:
        """执行严格 RAG 问答管道。

        Args:
            query: 用户问题

        Returns:
            dict: answer, sources, from_knowledge_base, match_count, ...
        """
        if not query or not query.strip():
            return self._empty_response("输入为空")

        logger.info("[RAG] 管道启动: query=%s", query[:80])

        # ═══════════════════════════════════════════════════════
        # Stage 1: 强制检索知识库
        # ═══════════════════════════════════════════════════════
        docs = self._retrieve(query)
        logger.info("[RAG] Stage 1: 检索到 %d 篇文档", len(docs))

        # ═══════════════════════════════════════════════════════
        # Stage 2: 相关度过滤
        # ═══════════════════════════════════════════════════════
        filtered = self._filter_by_relevance(docs)
        logger.info("[RAG] Stage 2: 过滤后 %d 篇 (阈值=%.2f)", len(filtered), RELEVANCE_THRESHOLD)

        # ═══════════════════════════════════════════════════════
        # Stage 3: 判断是否有匹配
        # ═══════════════════════════════════════════════════════
        if len(filtered) < MIN_MATCH_DOCS:
            logger.info("[RAG] Stage 3: 无匹配 — 返回「知识库暂无」")
            return self._no_match_response(query)

        # ═══════════════════════════════════════════════════════
        # Stage 4: 组装知识上下文
        # ═══════════════════════════════════════════════════════
        context = self._build_context(filtered)
        logger.info("[RAG] Stage 4: 上下文 %d 字符", len(context))

        # ═══════════════════════════════════════════════════════
        # Stage 5: 调用 LLM 做语言重组（仅重组，不生成新知识）
        # ═══════════════════════════════════════════════════════
        answer, from_kb = self._generate_strict_answer(query, context, filtered)
        logger.info("[RAG] Stage 5: LLM 重组完成 from_kb=%s", from_kb)

        sources = self._build_sources(filtered)

        return {
            "answer": answer,
            "sources": sources,
            "from_knowledge_base": from_kb,
            "match_count": len(filtered),
            "total_found": len(docs),
            "query": query,
        }

    def answer_stream(
        self, query: str,
    ):
        """流式 RAG 问答——yield SSE 事件。

        Yields SSE JSON strings: {"sources": [...]}, {"token": "..."}, {"done": true}
        """
        if not query or not query.strip():
            yield json.dumps({"token": "输入为空"}, ensure_ascii=False) + "\n"
            yield json.dumps({"done": True}, ensure_ascii=False) + "\n"
            return

        # 检索 + 过滤
        docs = self._retrieve(query)
        filtered = self._filter_by_relevance(docs)

        # Yield sources first
        sources = self._build_sources(filtered)
        if sources:
            yield "data: " + json.dumps({"sources": sources}, ensure_ascii=False) + "\n\n"

        if len(filtered) < MIN_MATCH_DOCS:
            yield "data: " + json.dumps(
                {"token": RAG_NO_MATCH_RESPONSE}, ensure_ascii=False,
            ) + "\n\n"
            yield "data: " + json.dumps({"done": True, "from_kb": False}, ensure_ascii=False) + "\n\n"
            return

        context = self._build_context(filtered)

        # 流式调用 LLM 重组
        try:
            provider = LLMService(model=self.model)
            # 使用 BaseProvider.chat() 的非流式版本（流式版本路径更长）
            # 但为了体验，尝试用 chat_stream
            from app.services.knowledge.provider_registry import ProviderRegistry
            provider_instance = ProviderRegistry().get_provider(self.model)
            messages = [
                {"role": "system", "content": RAG_STRICT_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_prompt(query, context)},
            ]
            for chunk in provider_instance.chat_stream(messages):
                if isinstance(chunk, dict):
                    reasoning = chunk.get("reasoning", "")
                    if reasoning:
                        yield "data: " + json.dumps({"reasoning": reasoning}, ensure_ascii=False) + "\n\n"
                    continue
                yield "data: " + json.dumps({"token": chunk}, ensure_ascii=False) + "\n\n"
        except Exception as e:
            logger.error("[RAG] LLM 流式调用失败: %s", e)
            yield "data: " + json.dumps({
                "token": f"知识重组服务暂时不可用：{e}",
            }, ensure_ascii=False) + "\n\n"

        yield "data: " + json.dumps({"done": True, "from_kb": True}, ensure_ascii=False) + "\n\n"

    # ==================================================================
    # Stage 1: 检索
    # ==================================================================

    def _retrieve(self, query: str) -> list:
        """强制检索知识库——混合搜索（向量优先 + 关键词回退）。

        策略:
        1. 优先使用 Milvus 向量搜索（语义精确匹配）
        2. 向量搜索无结果时回退到 keywords 搜索（关键字匹配）
        3. 仍无结果则返回空列表
        """
        try:
            # 尝试使用 DocumentIndexer 的混合搜索
            try:
                from app.services.knowledge.document_indexer import DocumentIndexer
                indexer = DocumentIndexer(self.db)
                hybrid_result = indexer.search_with_hybrid(
                    query,
                    vector_top_k=SEARCH_PAGE_SIZE,
                    keyword_top_k=SEARCH_PAGE_SIZE,
                )

                fused = hybrid_result.get("fused", [])
                if fused:
                    logger.info(
                        "[RAG] Hybrid search: %d results (strategy: %s)",
                        len(fused), hybrid_result.get("strategy", "unknown"),
                    )

                    # 转换为 knowledge service 兼容格式
                    items = []
                    for item in fused:
                        doc_id = item.get("id")
                        if doc_id:
                            try:
                                doc = self.knowledge.get(doc_id)
                                items.append({
                                    "id": doc_id,
                                    "title": doc.title,
                                    "category": doc.category,
                                    "doc_type": doc.doc_type,
                                    "source": doc.source,
                                    "relevance_score": round(item.get("score", 0), 2),
                                    "snippet": item.get("snippet", "")[:300],
                                    "content": doc.content,
                                })
                            except Exception:
                                continue
                    return items

            except Exception as exc:
                logger.debug("[RAG] Hybrid search unavailable: %s", exc)

            # 回退：关键词搜索
            result = self.knowledge.search(query, page_size=SEARCH_PAGE_SIZE)
            return result.get("items", [])

        except Exception as e:
            logger.error("[RAG] 检索异常: %s", e)
            return []

    # ==================================================================
    # Stage 2: 过滤
    # ==================================================================

    def _filter_by_relevance(self, docs: list) -> list:
        """按相关度阈值过滤文档。"""
        filtered = []
        for doc in docs:
            score = float(doc.get("relevance_score", 0) or 0)
            if score >= RELEVANCE_THRESHOLD:
                filtered.append(doc)
        # 按相关度降序排列
        filtered.sort(key=lambda d: float(d.get("relevance_score", 0) or 0), reverse=True)
        return filtered

    # ==================================================================
    # Stage 4: 上下文组装
    # ==================================================================

    def _build_context(self, docs: list) -> str:
        """将检索到的文档组装为上下文块。"""
        parts = []
        for i, doc in enumerate(docs):
            title = doc.get("title", "未命名文档")
            content = doc.get("content", "") or doc.get("snippet", "")
            # 截断过长内容
            if len(content) > 1500:
                content = content[:1500] + "…(内容已截断)"
            parts.append(f"### 文档 {i + 1}：{title}\n{content}")
        return "\n\n".join(parts)

    # ==================================================================
    # Stage 5: 严格 LLM 重组
    # ==================================================================

    def _generate_strict_answer(
        self, query: str, context: str, docs: list,
    ) -> tuple[str, bool]:
        """调用 LLM 进行严格的语言重组（禁止生成新知识）。

        Returns:
            (answer_text, from_knowledge_base)
        """
        try:
            provider = LLMService(model=self.model)
            from app.services.knowledge.provider_registry import ProviderRegistry
            provider_instance = ProviderRegistry().get_provider(self.model)

            messages = [
                {"role": "system", "content": RAG_STRICT_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_prompt(query, context)},
            ]

            raw_answer = provider_instance.chat(messages)

            # 验证 LLM 是否遵守了约束（检测「知识库暂无」关键词）
            if "知识库中暂无" in raw_answer or "无与此问题相关的信息" in raw_answer:
                return RAG_NO_MATCH_RESPONSE, False

            return raw_answer, True

        except Exception as e:
            logger.error("[RAG] LLM 调用失败: %s", e)
            # 回退：直接用检索到的内容组装回答
            fallback = self._build_fallback_answer(docs)
            return fallback, True

    def _build_user_prompt(self, query: str, context: str) -> str:
        """构建发送给 LLM 的用户提示。"""
        return (
            f"## 用户问题\n{query}\n\n"
            f"## 知识库检索结果（你的唯一事实来源）\n\n{context}\n\n"
            f"请严格基于以上知识库内容回答用户问题。"
            "只做语言重组和排版优化，不得添加任何知识库未提及的信息。"
        )

    def _build_fallback_answer(self, docs: list) -> str:
        """当 LLM 不可用时，用检索文档直接组装回答。"""
        if not docs:
            return RAG_NO_MATCH_RESPONSE

        parts = ["## 基于知识库的回答 (自动组装)\n"]
        for i, doc in enumerate(docs[:3]):
            title = doc.get("title", "未命名文档")
            snippet = doc.get("snippet", "") or doc.get("content", "")[:500]
            parts.append(f"### 来源 {i + 1}：《{title}》\n{snippet}")

        parts.append(f"\n> ℹ️ 当前 AI 服务不可用，以上为知识库直接检索结果。")
        return "\n\n".join(parts)

    # ==================================================================
    # Helpers
    # ==================================================================

    def _no_match_response(self, query: str) -> Dict[str, Any]:
        """知识库无匹配时的标准响应。"""
        return {
            "answer": RAG_NO_MATCH_RESPONSE,
            "sources": [],
            "from_knowledge_base": False,
            "match_count": 0,
            "total_found": 0,
            "query": query,
        }

    def _empty_response(self, reason: str) -> Dict[str, Any]:
        return {
            "answer": "",
            "sources": [],
            "from_knowledge_base": False,
            "match_count": 0,
            "total_found": 0,
            "query": "",
        }

    def _build_sources(self, docs: list) -> list:
        """从检索文档构建引用来源列表。"""
        return [
            {
                "id": doc.get("id"),
                "title": doc.get("title", "未知"),
                "source": doc.get("source") or "知识库",
                "excerpt": doc.get("snippet", "")[:200],
                "relevance_score": doc.get("relevance_score", 0),
            }
            for doc in docs
        ]
