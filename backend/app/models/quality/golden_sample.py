"""回归黄金集 — 检索与问答质量的唯一标尺。

审核链按「提交人角色」决定（见 services/quality/review_policy.py）：
    管理员提交   → 直接生效
    开发提交     → 管理员终审
    测试提交     → 开发复审 → 管理员终审
    用户(售后/产品)提交 → 测试初审 → 开发复审 → 管理员终审

硬规则：
  - 链上角色不等于提交人角色，「提交人不得自审」自动成立；
  - approved 样本不可原地修改，只能打回重审（回到 in_review 第 0 步）或标记 superseded；
  - 每次内容变更 sample_version +1，审核轨迹经 SampleReview 留痕。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base

# 样本状态：draft 填写中 / in_review 审核中（层级由 review_step 指出）/ approved 生效
# needs_recheck：其依赖的知识条目已上线或改版，期望可能失效，需人工确认后才回到 approved
SAMPLE_STATUSES = ("draft", "in_review", "approved", "rejected", "superseded", "needs_recheck")

STATUS_TRANSITIONS = {
    "draft": ("in_review", "approved"),      # 管理员提交直接 approved
    "in_review": ("in_review", "approved", "rejected"),
    "approved": ("in_review", "superseded", "needs_recheck"),  # 打回重审 / 文档失效 / 知识条目变更
    "rejected": ("in_review", "superseded"),
    "superseded": ("in_review",),
    "needs_recheck": ("approved", "in_review", "superseded"),
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
    # 审核链由提交人角色决定（管理员提交为空链）；review_step = 已通过的级数
    review_chain = Column(JSON, nullable=True)
    review_step = Column(Integer, nullable=False, default=0)

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
