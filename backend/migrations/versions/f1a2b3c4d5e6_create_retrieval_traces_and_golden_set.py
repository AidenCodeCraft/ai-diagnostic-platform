"""create retrieval traces and regression golden set

Revision ID: f1a2b3c4d5e6
Revises: d5e9f3a7b2c4
Create Date: 2026-11-18

新增四张表，服务「可度量的检索质量」：
  - retrieval_traces  每次提问的检索轨迹（黄金集标注与故障复盘的数据源）
  - golden_samples    回归样本（问题/槽位/期望章节/期望日志时段/期望结论）
  - sample_reviews    三级审核轨迹（提交人 → 测试初审 → 开发复审 → 管理员终审）
  - regression_runs   每次 CI 回归的结果与指标
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d5e9f3a7b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retrieval_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id"), nullable=True),
        sa.Column("log_id", sa.Integer(), sa.ForeignKey("logs.id"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("slots", sa.JSON(), nullable=True),
        sa.Column("kb_candidates", sa.JSON(), nullable=True),
        sa.Column("log_patterns", sa.JSON(), nullable=True),
        sa.Column("log_blocks", sa.JSON(), nullable=True),
        sa.Column("timings", sa.JSON(), nullable=True),
        sa.Column("conclusion", sa.String(24), nullable=True),
        sa.Column("pipeline_version", sa.String(32), nullable=True),
        sa.Column("kb_version", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_retrieval_traces_session_id", "retrieval_traces", ["session_id"])
    op.create_index("ix_retrieval_traces_message_id", "retrieval_traces", ["message_id"])
    op.create_index("ix_retrieval_traces_created_at", "retrieval_traces", ["created_at"])

    op.create_table(
        "golden_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("slots", sa.JSON(), nullable=True),
        sa.Column("kb_expected", sa.JSON(), nullable=True),
        sa.Column("log_expected", sa.JSON(), nullable=True),
        sa.Column("expected_conclusion", sa.String(24), nullable=False, server_default="answered"),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("device_model", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("sample_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_chain", sa.JSON(), nullable=True),
        sa.Column("review_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("replay_snapshot_ref", sa.String(512), nullable=True),
        sa.Column("trace_id", sa.Integer(), sa.ForeignKey("retrieval_traces.id"), nullable=True),
        sa.Column("pipeline_version", sa.String(32), nullable=True),
        sa.Column("kb_version", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_golden_samples_category", "golden_samples", ["category"])
    op.create_index("ix_golden_samples_device_model", "golden_samples", ["device_model"])
    op.create_index("ix_golden_samples_status", "golden_samples", ["status"])
    op.create_index("ix_golden_samples_submitted_by", "golden_samples", ["submitted_by"])

    op.create_table(
        "sample_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sample_id", sa.Integer(),
            sa.ForeignKey("golden_samples.id"), nullable=False,
        ),
        sa.Column("sample_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name", sa.String(50), nullable=True),
        sa.Column("role", sa.String(20), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sample_reviews_sample_id", "sample_reviews", ["sample_id"])
    op.create_index("ix_sample_reviews_actor_id", "sample_reviews", ["actor_id"])
    op.create_index("ix_sample_reviews_created_at", "sample_reviews", ["created_at"])

    op.create_table(
        "regression_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column("triggered_by", sa.String(50), nullable=True),
        sa.Column("golden_version", sa.String(64), nullable=True),
        sa.Column("pipeline_version", sa.String(32), nullable=True),
        sa.Column("kb_version", sa.String(64), nullable=True),
        sa.Column("total_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("failure_detail", sa.JSON(), nullable=True),
        sa.Column("report_ref", sa.String(512), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_regression_runs_run_id", "regression_runs", ["run_id"], unique=True)
    op.create_index("ix_regression_runs_commit_sha", "regression_runs", ["commit_sha"])
    op.create_index("ix_regression_runs_status", "regression_runs", ["status"])
    op.create_index("ix_regression_runs_started_at", "regression_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_regression_runs_started_at", table_name="regression_runs")
    op.drop_index("ix_regression_runs_status", table_name="regression_runs")
    op.drop_index("ix_regression_runs_commit_sha", table_name="regression_runs")
    op.drop_index("ix_regression_runs_run_id", table_name="regression_runs")
    op.drop_table("regression_runs")

    op.drop_index("ix_sample_reviews_created_at", table_name="sample_reviews")
    op.drop_index("ix_sample_reviews_actor_id", table_name="sample_reviews")
    op.drop_index("ix_sample_reviews_sample_id", table_name="sample_reviews")
    op.drop_table("sample_reviews")

    op.drop_index("ix_golden_samples_submitted_by", table_name="golden_samples")
    op.drop_index("ix_golden_samples_status", table_name="golden_samples")
    op.drop_index("ix_golden_samples_device_model", table_name="golden_samples")
    op.drop_index("ix_golden_samples_category", table_name="golden_samples")
    op.drop_table("golden_samples")

    op.drop_index("ix_retrieval_traces_created_at", table_name="retrieval_traces")
    op.drop_index("ix_retrieval_traces_message_id", table_name="retrieval_traces")
    op.drop_index("ix_retrieval_traces_session_id", table_name="retrieval_traces")
    op.drop_table("retrieval_traces")
