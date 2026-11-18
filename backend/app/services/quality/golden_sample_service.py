"""黄金集服务 — 提交、审核、打回、失效、导出。

审核链由 services/quality/review_policy.py 决定（按提交人角色），本层只负责：
  1. 权限与状态校验（谁能动、此刻能不能动）；
  2. 状态与 review_step 推进；
  3. 每一次动作都写 sample_reviews 审计。

纪律（防污染）：
  - 提交人不得审自己的样本；
  - approved 样本被改动必须回到链路起点重审，不允许原地生效；
  - 只有 approved 样本进入回归导出。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.quality.golden_sample import (
    EXPECTED_CONCLUSIONS,
    STATUS_TRANSITIONS,
    GoldenSample,
    SampleReview,
)
from app.services.quality.review_policy import (
    STATUS_APPROVED,
    STATUS_IN_REVIEW,
    STATUS_SUPERSEDED,
    apply_review,
    can_review,
    initial_status,
    next_reviewer,
    normalize_role,
    required_review_roles,
    reset_for_revision,
)

# 允许通过 update 修改的业务字段（状态/审核相关字段只能走流程）
_EDITABLE_FIELDS = (
    "question", "slots", "kb_expected", "log_expected", "expected_conclusion",
    "category", "device_model", "note", "replay_snapshot_ref",
)


class GoldenSampleError(ValueError):
    """业务校验失败（映射为 400）。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class GoldenSampleService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 提交
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        question: str,
        actor_id: Optional[int],
        actor_role: Optional[str],
        actor_name: Optional[str] = None,
        slots: Optional[Dict[str, Any]] = None,
        kb_expected: Optional[List[Dict[str, Any]]] = None,
        log_expected: Optional[Dict[str, Any]] = None,
        expected_conclusion: str = "answered",
        category: Optional[str] = None,
        device_model: Optional[str] = None,
        note: Optional[str] = None,
        replay_snapshot_ref: Optional[str] = None,
        trace_id: Optional[int] = None,
        submit: bool = True,
    ) -> GoldenSample:
        if not (question or "").strip():
            raise GoldenSampleError("question 不能为空")
        if expected_conclusion not in EXPECTED_CONCLUSIONS:
            raise GoldenSampleError(
                f"expected_conclusion 必须是 {EXPECTED_CONCLUSIONS} 之一"
            )

        chain = list(required_review_roles(actor_role))
        sample = GoldenSample(
            question=question.strip(),
            slots=slots,
            kb_expected=kb_expected,
            log_expected=log_expected,
            expected_conclusion=expected_conclusion,
            category=category,
            device_model=device_model,
            note=note,
            replay_snapshot_ref=replay_snapshot_ref,
            trace_id=trace_id,
            submitted_by=actor_id,
            submitted_at=datetime.now(timezone.utc),
            review_chain=chain,
            review_step=0,
            status=initial_status(actor_role) if submit else "draft",
        )
        # 管理员提交无审核链：落库即生效，同时记录终审人
        if sample.status == STATUS_APPROVED:
            sample.approved_by = actor_id
            sample.approved_at = datetime.now(timezone.utc)

        self.db.add(sample)
        self.db.flush()
        self._audit(
            sample, actor_id, actor_name, normalize_role(actor_role),
            "submit" if submit else "draft",
            reason=None,
        )
        self.db.commit()
        self.db.refresh(sample)
        return sample

    def submit_sample(
        self,
        sample_id: int,
        *,
        actor_id: Optional[int],
        actor_role: Optional[str],
        actor_name: Optional[str] = None,
    ) -> GoldenSample:
        """draft / rejected 样本重新提交审核（回到链路第 0 步）。"""
        sample = self.get(sample_id)
        role = normalize_role(actor_role)
        if role != "admin" and sample.submitted_by != actor_id:
            raise GoldenSampleError("只有提交人或管理员可以提交该样本", status_code=403)
        if sample.status not in ("draft", "rejected"):
            raise GoldenSampleError(f"当前状态 {sample.status} 不可提交审核")

        new_status, new_step = reset_for_revision(sample.review_chain)
        self._assert_transition(sample.status, new_status)
        sample.status = new_status
        sample.review_step = new_step
        sample.submitted_at = datetime.now(timezone.utc)
        self._audit(sample, actor_id, actor_name, role, "submit", reason=None)
        self.db.commit()
        self.db.refresh(sample)
        return sample

    # ------------------------------------------------------------------
    # 修改
    # ------------------------------------------------------------------
    def update(
        self,
        sample_id: int,
        *,
        actor_id: Optional[int],
        actor_role: Optional[str],
        actor_name: Optional[str] = None,
        **changes: Any,
    ) -> GoldenSample:
        sample = self.get(sample_id)
        role = normalize_role(actor_role)

        # 只有提交人本人或管理员可以改内容
        if role != "admin" and sample.submitted_by != actor_id:
            raise GoldenSampleError("只有提交人或管理员可以修改该样本", status_code=403)

        applied = {k: v for k, v in changes.items() if k in _EDITABLE_FIELDS and v is not None}
        if not applied:
            raise GoldenSampleError("没有可修改的字段")
        if "expected_conclusion" in applied and applied["expected_conclusion"] not in EXPECTED_CONCLUSIONS:
            raise GoldenSampleError(
                f"expected_conclusion 必须是 {EXPECTED_CONCLUSIONS} 之一"
            )

        for field, value in applied.items():
            setattr(sample, field, value)
        sample.sample_version = (sample.sample_version or 1) + 1

        # 任何内容变更都使既有审核失效：回到链路起点重审
        if sample.status in (STATUS_APPROVED, STATUS_IN_REVIEW):
            new_status, new_step = reset_for_revision(sample.review_chain)
            sample.status = new_status
            sample.review_step = new_step
            sample.approved_by = None
            sample.approved_at = None

        self._audit(sample, actor_id, actor_name, role, "revise", reason=None)
        self.db.commit()
        self.db.refresh(sample)
        return sample

    # ------------------------------------------------------------------
    # 审核
    # ------------------------------------------------------------------

    def review(
        self,
        sample_id: int,
        *,
        actor_id: Optional[int],
        actor_role: Optional[str],
        approve: bool,
        actor_name: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> GoldenSample:
        sample = self.get(sample_id)
        role = normalize_role(actor_role)

        if sample.status != STATUS_IN_REVIEW:
            raise GoldenSampleError(f"当前状态 {sample.status} 不接受审核")
        if sample.submitted_by is not None and sample.submitted_by == actor_id:
            raise GoldenSampleError("不能审核自己提交的样本", status_code=403)
        if not can_review(chain=sample.review_chain, step=sample.review_step, actor_role=role):
            expect = next_reviewer(sample.review_chain, sample.review_step)
            raise GoldenSampleError(
                f"当前应由 {expect} 审核，{role} 无权处理", status_code=403,
            )
        if not approve and not (reason or "").strip():
            raise GoldenSampleError("驳回必须填写原因")

        new_status, new_step = apply_review(
            chain=sample.review_chain, step=sample.review_step, approve=approve,
        )
        self._assert_transition(sample.status, new_status)

        sample.status = new_status
        sample.review_step = new_step
        if new_status == STATUS_APPROVED:
            sample.approved_by = actor_id
            sample.approved_at = datetime.now(timezone.utc)

        self._audit(
            sample, actor_id, actor_name, role,
            "approve" if approve else "reject", reason=reason,
        )
        self.db.commit()
        self.db.refresh(sample)
        return sample

    def supersede(
        self,
        sample_id: int,
        *,
        actor_id: Optional[int],
        actor_role: Optional[str],
        actor_name: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> GoldenSample:
        sample = self.get(sample_id)
        if normalize_role(actor_role) != "admin":
            raise GoldenSampleError("只有管理员可以标记样本失效", status_code=403)
        if not (reason or "").strip():
            raise GoldenSampleError("标记失效必须填写原因")
        self._assert_transition(sample.status, STATUS_SUPERSEDED)
        sample.status = STATUS_SUPERSEDED
        self._audit(sample, actor_id, actor_name, "admin", "supersede", reason=reason)
        self.db.commit()
        self.db.refresh(sample)
        return sample

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, sample_id: int) -> GoldenSample:
        sample = self.db.query(GoldenSample).filter(GoldenSample.id == sample_id).first()
        if not sample:
            raise GoldenSampleError("样本不存在", status_code=404)
        return sample

    def list(
        self,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        device_model: Optional[str] = None,
        submitted_by: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        query = self.db.query(GoldenSample)
        if status:
            query = query.filter(GoldenSample.status == status)
        if category:
            query = query.filter(GoldenSample.category == category)
        if device_model:
            query = query.filter(GoldenSample.device_model == device_model)
        if submitted_by:
            query = query.filter(GoldenSample.submitted_by == submitted_by)
        total = query.count()
        items = (
            query.order_by(GoldenSample.updated_at.desc(), GoldenSample.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def pending_for(self, actor_role: Optional[str], *, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """待我审核的样本（按当前 review_step 指向的角色过滤）。"""
        role = normalize_role(actor_role)
        query = self.db.query(GoldenSample).filter(GoldenSample.status == STATUS_IN_REVIEW)
        items = query.order_by(GoldenSample.id.asc()).all()
        mine = [
            s for s in items
            if next_reviewer(s.review_chain, s.review_step) == role
        ]
        total = len(mine)
        start = (page - 1) * page_size
        return {"items": mine[start:start + page_size], "total": total, "page": page, "page_size": page_size}

    def export_approved(self) -> List[Dict[str, Any]]:
        """导出 CI 用的 approved 样本（不含审核内部字段）。"""
        rows = (
            self.db.query(GoldenSample)
            .filter(GoldenSample.status == STATUS_APPROVED)
            .order_by(GoldenSample.id.asc())
            .all()
        )
        return [
            {
                "id": s.id,
                "question": s.question,
                "slots": s.slots,
                "kb_expected": s.kb_expected,
                "log_expected": s.log_expected,
                "expected_conclusion": s.expected_conclusion,
                "category": s.category,
                "device_model": s.device_model,
                "replay_snapshot_ref": s.replay_snapshot_ref,
                "sample_version": s.sample_version,
            }
            for s in rows
        ]

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_transition(old: str, new: str) -> None:
        allowed = STATUS_TRANSITIONS.get(old, ())
        if new not in allowed:
            raise GoldenSampleError(f"非法状态流转：{old} → {new}")

    def _audit(
        self,
        sample: GoldenSample,
        actor_id: Optional[int],
        actor_name: Optional[str],
        role: str,
        action: str,
        reason: Optional[str],
    ) -> None:
        self.db.add(SampleReview(
            sample_id=sample.id,
            sample_version=sample.sample_version or 1,
            actor_id=actor_id,
            actor_name=actor_name,
            role=role,
            action=action,
            reason=reason,
        ))
