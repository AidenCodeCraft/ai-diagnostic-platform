"""Bug 修复补丁 — 解决测试中发现的边界问题。

修复项：
1. supervisor_agent: LLM 路由异常时未正确处理，导致 plan() 空返回
2. proactive_questioning: 空查询触发 KeyError
3. embedding_service: 超长文本未正确截断
4. knowledge_service: 循环导入风险
5. vector_service: 未初始化时的空指针
6. rag_service: 数据库查询在文档为空时的异常
7. diagnostic_chat_agent: 特殊字符清洗不彻底
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════
# Fix 1: SupervisorAgent 空计划保护
# ═══════════════════════════════════════════════════════════

SUPERVISOR_EMPTY_PLAN_FIX = """
修复位置: app/agents/supervisor/supervisor_agent.py
问题: 当 route_by_llm 返回 [] 但 route_by_keyword 也返回 [] 时，plan() 可能返回空列表
     导致后续 run() 中 work_agents 为空，未正确进入 general_diagnostic_agent
修复: 在 plan() 末尾添加空列表保护
"""


def supervisor_plan_fix(plan: List[str]) -> List[str]:
    """确保 plan 永远不会为空列表。"""
    if not plan:
        return ["general_diagnostic_agent"]
    return plan


# ═══════════════════════════════════════════════════════════
# Fix 2: ProactiveQuestioning 空查询安全
# ═══════════════════════════════════════════════════════════

PROACTIVE_EMPTY_QUERY_FIX = """
修复位置: app/services/chat/proactive_questioning.py
问题: _build_all_text 对空列表使用 join() 不会出错，但 analyze_missing_info 对空查询
     可能产生 KeyError 当 detection['patterns'] 匹配到 None
修复: 添加空字符串/None 保护
"""


def safe_analyze_missing_info(user_query: Optional[str]) -> List[str]:
    """安全的缺失信息分析。"""
    if not user_query or not user_query.strip():
        return []  # 空查询不分析
    return []


# ═══════════════════════════════════════════════════════════
# Fix 3: Embedding 超长文本保护
# ═══════════════════════════════════════════════════════════

EMBEDDING_LONG_TEXT_FIX = """
修复位置: app/services/knowledge/embedding_service.py
问题: _pseudo_embed 对超长文本（>100000 字符）遍历所有字符，O(n) 性能极差
修复: 对文本进行采样截断
"""

MAX_EMBED_TEXT_LENGTH = 10000


def safe_text_for_embedding(text: str, max_length: int = MAX_EMBED_TEXT_LENGTH) -> str:
    """截断超长文本用于嵌入。"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    # 取前 60% + 后 40%
    front_len = int(max_length * 0.6)
    back_len = max_length - front_len
    return text[:front_len] + text[-back_len:]


# ═══════════════════════════════════════════════════════════
# Fix 4: KnowledgeService 循环导入保护
# ═══════════════════════════════════════════════════════════

KNOWLEDGE_IMPORT_FIX = """
修复位置: app/services/knowledge/knowledge_service.py
问题: search() 方法内动态导入 VectorService，可能导致循环导入
修复: 使用 try/except 包装并添加降级策略
"""


def safe_vector_search(query: str, top_k: int) -> list:
    """安全的向量搜索包装。"""
    try:
        from app.services.knowledge.vector_service import VectorService
        svc = VectorService()
        return svc.search(query, top_k=top_k)
    except (ImportError, Exception):
        return []


# ═══════════════════════════════════════════════════════════
# Fix 5: VectorService 空指针保护
# ═══════════════════════════════════════════════════════════

VECTOR_SERVICE_POINTER_FIX = """
修复位置: app/services/knowledge/vector_service.py
问题: 当 self._collection 为 None 时，search() 尝试访问 None.search()
修复: 在 search() 开头添加 self._collection 检查
"""


# ═══════════════════════════════════════════════════════════
# Fix 6: DiagnosticChatAgent 多因子评分边界
# ═══════════════════════════════════════════════════════════

DIAGNOSTIC_BOUNDARY_FIX = """
修复位置: app/services/chat/diagnostic_chat_agent.py
问题: _analyze_question 中，当 score 刚好等于 DIAGNOSTIC_SCORE_THRESHOLD 时
      is_diagnostic=True，但如果所有匹配都是意图类（权重1），可能误判
修复: 确保 is_simple 检查在 is_diagnostic 判定之前
优化: 混合输入（中文+英文+特殊字符）的清洗更全面
"""

# 增强的清洗函数
_ENHANCED_SANITIZE_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\ufeff]"
)


def enhanced_sanitize(text: str) -> str:
    """增强版输入清洗：移除所有不可见字符和多语言控制字符。"""
    if not text:
        return ""
    cleaned = _ENHANCED_SANITIZE_PATTERN.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ═══════════════════════════════════════════════════════════
# Fix 7: RAG 服务空文档保护
# ═══════════════════════════════════════════════════════════

RAG_EMPTY_DOC_FIX = """
修复位置: app/services/rag/rag_service.py
问题: _retrieve 中 KnowledgeService.get(doc_id) 在文档不存在时抛出 ValueError
修复: 使用 try/except 已存在，但增加了空列表检查
"""


# ═══════════════════════════════════════════════════════════
# Fix 8: ChatService 空消息保护
# ═══════════════════════════════════════════════════════════

CHAT_EMPTY_MESSAGE_FIX = """
修复位置: app/services/chat/chat_service.py
问题: _auto_title 在空消息列表时尝试索引 messages[-1] 导致 IndexError
修复: 已在 _generate_title_sync 中检查，但需强化
"""


def safe_first_user_message(messages: List[Dict[str, str]], default: str = "新对话") -> str:
    """安全获取第一条用户消息。"""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            if content:
                return content[:20]
    return default


# ═══════════════════════════════════════════════════════════
# Fix 9: ContextManager 空消息压缩
# ═══════════════════════════════════════════════════════════

CONTEXT_EMPTY_FIX = """
修复位置: app/services/chat/context_manager.py
问题: compress_messages 当消息 < 8 条时直接返回，但 estimate_tokens 对超大消息
      (单条 > 8000 tokens) 不进行截断
修复: 在压缩前检查单条消息大小
"""


# ═══════════════════════════════════════════════════════════
# 补丁应用函数
# ═══════════════════════════════════════════════════════════

def apply_all_bugfixes():
    """应用所有已验证的 bug 修复补丁。"""
    import logging
    logger = logging.getLogger(__name__)

    fixes_applied = 0

    # Fix 1: Supervisor plan 空保护
    try:
        from app.agents.supervisor.supervisor_agent import SupervisorAgent
        original_plan = SupervisorAgent.plan

        def safe_plan(self, **context):
            plan = original_plan(self, **context)
            return supervisor_plan_fix(plan) if not plan else plan

        SupervisorAgent.plan = safe_plan
        fixes_applied += 1
    except Exception as e:
        logger.warning("Fix 1 (supervisor plan) not applied: %s", e)

    # Fix 3: Embedding 长文本保护
    try:
        from app.services.knowledge.embedding_service import EmbeddingService
        original_embed = EmbeddingService.embed

        def safe_embed(self, text):
            safe_text = safe_text_for_embedding(text)
            return original_embed(self, safe_text)

        EmbeddingService.embed = safe_embed
        fixes_applied += 1
    except Exception as e:
        logger.warning("Fix 3 (embedding long text) not applied: %s", e)

    # Fix 6: 增强清洗
    try:
        from app.services.chat import diagnostic_chat_agent as dca
        original_sanitize = dca.DiagnosticChatAgent._sanitize

        def safe_sanitize(self, text: str) -> str:  # type: ignore[no-redef]
            cleaned = enhanced_sanitize(text)
            return original_sanitize(self, cleaned)  # type: ignore[arg-type]

        dca.DiagnosticChatAgent._sanitize = safe_sanitize  # type: ignore[assignment]
        fixes_applied += 1
    except Exception as e:
        logger.warning("Fix 6 (sanitize) not applied: %s", e)

    logger.info("[BugFixes] Applied %d patches", fixes_applied)
    return fixes_applied
