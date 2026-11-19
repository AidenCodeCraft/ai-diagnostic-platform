"""检索轨迹 — 每次带问答的检索全过程快照。

用途：
  1. 黄金集标注：事后必须能看到「当时检索到了什么」才能标注期望；
  2. 失败复盘：回答错误时定位是召回漏了、还是重排错了、还是日志没命中；
  3. 回归对比：CI 用同一问题重放时与历史轨迹比对。

没有这张表，黄金集只能靠人工抄写、且历史对话无法复盘。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class RetrievalTrace(Base):
    """一次提问完整的检索轨迹（槽位 → 召回 → 模式 → 日志块 → 耗时）。"""

    __tablename__ = "retrieval_traces"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True, index=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=True)

    question = Column(Text, nullable=False)
    # 五项槽位：{city, device, phenomenon, time_beijing, has_attachment}
    slots = Column(JSON, nullable=True)
    # 知识库召回：{candidates: [{pk, doc_id, section, score}], top_k, fused_k}
    kb_candidates = Column(JSON, nullable=True)
    # 关键字模式：{patterns: [{pattern, type, source_chunk, case_sensitive}], points: [...]}
    log_patterns = Column(JSON, nullable=True)
    # 日志定位：{time_range, hour_buckets, blocks: [{line_start, line_end, hits, module_id}]}
    log_blocks = Column(JSON, nullable=True)
    # 各阶段耗时（毫秒）：{slot_ms, timeline_ms, kb_ms, locate_ms, first_token_ms, total_ms}
    timings = Column(JSON, nullable=True)
    # 结论分支：answered / refused / ask_slot / time_mismatch / no_kb_entry
    conclusion = Column(String(24), nullable=True)

    pipeline_version = Column(String(32), nullable=True)
    kb_version = Column(String(64), nullable=True)
    prompt_version = Column(String(32), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
