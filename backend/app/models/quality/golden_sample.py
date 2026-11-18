"""回归黄金集 — 检索与问答质量的唯一标尺。

流程（三级审核，防污染）：
    提交(draft) → 测试初审(pending_test) → 开发复审(pending_dev)
    → 管理员终审(pending_admin) → approved（进入 CI）→ superseded（文档/日志失效）

硬规则：
  - 提交人不得担任该样本的任一审核人；
  - approved 样本不可原地修改，只能打回重审或标记 superseded；
  - 每次内容变更 sample_version +1，旧版本经 SampleReview 留痕。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base

# 审核状态（顺序即流转顺序，不允许跳级）
GOLDEN_SAMPLE_STATUSES = (
    "draft",           # 提交人填写中
    "pending_test",    # 待测试初审
    "pending_dev",     # 待开发复审
    "pending_admin",   # 待管理员终审
    "approved",        # 进入 CI 回归
    "rejected",        # 任一环节驳回，退回提交人
    "superseded",      # 文档改版 / 日志失效，保留但跳过
)

STATUS_TRANSITIONS = {
    "draft": ("pending_test",),
    "pending_test": ("pending_dev", "rejected"),
    "pending_dev": ("pending_admin", "rejected"),
    "pending_admin": ("approved", "rejected"),
    "approved": ("pending_test", "superseded"),   # 打回重审 / 标记失效
    "rejected": ("pending_test",),
    "superseded": ("pending_test",),
}

# 期望结论四类 —— 负样本必须覆盖，否则只测正样本会严重偏乐观
EXPECTED_CONCLUSIONS = ("answered", "refused", "ask_slot", "time_mismatch")


class GoldenSample(Base):
    """一条可重放的回归样本（问题 + 槽位 + 期望章节 + 期望日志时段 + 期望结论）。"""

    __tablename__ = "golden_samples"

    id = Column(Integer, primary_key=True)
    question = Column(Text, nullable=False)
    # 五项槽位：{city, device, phenomenon, time_beijing, has_attachment, log_id}
    slots = Column(JSON, nullable=True)
    # 应命中的章节：[{doc_id, section, pk}]
    kb_expected = Column(JSON, nullable=True)
    # 应命中的日志：{time_range, line_ranges, must_hit_patterns}
    log_expected = Column(JSON, nullable=True)
    # answered / refused / ask_slot / time_mismatch
    expected_conclusion = Column(String(24), nullable=False, default="answered")

    category = Column(String(64), nullable=True, index=True)        # 现象类别（覆盖矩阵用）
    device_model = Column(String(64), nullable=True, index=True)    # 设备型号

    status = Column(String(24), nullable=False, default="draft", index=True)
    sample_version = Column(Integer, nullable=False, default=1)

    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # 固化证据（命中块 + 上下文 + 原日志切片），独立桶，不随 ILM 清理
    replay_snapshot_ref = Column(String(512), nullable=True)
    # 溯源到当时的检索轨迹（复盘用；CI 重放不依赖它）
    trace_id = Column(Integer, ForeignKey("retrieval_traces.id"), nullable=True)

    pipeline_version = Column(String(32), nullable=True)
    kb_version = Column(String(64), nullable=True)
    prompt_version = Column(String(32), nullable=True)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SampleReview(Base):
    """样本审核轨迹 — 标尺的任何一次移动都必须留痕。"""

    __tablename__ = "sample_reviews"

    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey("golden_samples.id"), nullable=False, index=True)
    sample_version = Column(Integer, nullable=False, default=1)

    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_name = Column(String(50), nullable=True)
    role = Column(String(20), nullable=True)      # test / developer / admin / submitter
    action = Column(String(20), nullable=False)   # submit / approve / reject / revise / supersede
    reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class RegressionRun(Base):
    """一次 CI 回归结果（每次提交一条）。"""

    __tablename__ = "regression_runs"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    commit_sha = Column(String(64), nullable=True, index=True)
    triggered_by = Column(String(50), nullable=True)   # ci / manual

    golden_version = Column(String(64), nullable=True)  # approved 集合的版本指纹
    pipeline_version = Column(String(32), nullable=True)
    kb_version = Column(String(64), nullable=True)

    total_samples = Column(Integer, nullable=False, default=0)
    passed = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    # {recall_at_5, hit_at_30, pattern_hit_rate, conclusion_accuracy, refusal_accuracy, p95_first_token_ms}
    metrics = Column(JSON, nullable=True)

    status = Column(String(20), nullable=False, default="running", index=True)  # running/passed/failed/error
    failure_detail = Column(JSON, nullable=True)   # 失败样本明细（问题/期望/实际/trace_id）
    report_ref = Column(String(512), nullable=True)

    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    finished_at = Column(DateTime, nullable=True)
