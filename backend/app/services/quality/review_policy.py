"""黄金集审核策略 — 按「提交人角色」决定需要谁审、审几级。

规则（2026-11 定稿）：
    管理员提交  → 无需审核，直接生效
    开发提交    → 管理员终审
    测试提交    → 开发复审 → 管理员终审
    用户(售后/产品)提交 → 测试初审 → 开发复审 → 管理员终审

设计要点：
  - 链上角色天然不等于提交人角色，因此「提交人不得自审」自动成立；
  - 未知/缺省角色按最低权限处理（走三级），宁可多审不可漏审；
  - 纯函数，不依赖数据库，便于单测与前端回显「下一步该谁审」。
"""

from __future__ import annotations

from typing import Tuple

ROLE_ADMIN = "admin"
ROLE_DEVELOPER = "developer"
ROLE_ENGINEER = "engineer"
ROLE_USER = "user"

# 中文与历史命名容错：售后/产品统一按「用户」处理，不单独建角色
_ROLE_ALIASES = {
    "admin": ROLE_ADMIN,
    "管理员": ROLE_ADMIN,
    "developer": ROLE_DEVELOPER,
    "dev": ROLE_DEVELOPER,
    "开发": ROLE_DEVELOPER,
    "研发": ROLE_DEVELOPER,
    "engineer": ROLE_ENGINEER,
    "qa": ROLE_ENGINEER,
    "test": ROLE_ENGINEER,
    "测试": ROLE_ENGINEER,
    "user": ROLE_USER,
    "用户": ROLE_USER,
    "售后": ROLE_USER,
    "产品": ROLE_USER,
}

# 提交人角色 → 需要依次通过审核的角色
REVIEW_CHAINS = {
    ROLE_ADMIN: (),
    ROLE_DEVELOPER: (ROLE_ADMIN,),
    ROLE_ENGINEER: (ROLE_DEVELOPER, ROLE_ADMIN),
    ROLE_USER: (ROLE_ENGINEER, ROLE_DEVELOPER, ROLE_ADMIN),
}

STATUS_DRAFT = "draft"
STATUS_IN_REVIEW = "in_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_SUPERSEDED = "superseded"
# 知识条目上线/改版后，依赖它的 approved 样本需要人工确认期望是否仍成立
STATUS_NEEDS_RECHECK = "needs_recheck"


def normalize_role(role: str | None) -> str:
    """把中文/别名角色归一为四种标准角色；未知取 user（最低权限）。"""
    key = str(role or "").strip().lower()
    return _ROLE_ALIASES.get(key, ROLE_USER)


def required_review_roles(submitter_role: str | None) -> Tuple[str, ...]:
    """提交人角色对应的审核链（有序，最后一个是终审）。"""
    return REVIEW_CHAINS[normalize_role(submitter_role)]


def initial_status(submitter_role: str | None) -> str:
    """提交后的初始状态：管理员直接生效，其余进入审核。"""
    return STATUS_APPROVED if not required_review_roles(submitter_role) else STATUS_IN_REVIEW


def next_reviewer(chain: Tuple[str, ...] | list | None, step: int) -> str | None:
    """当前待审角色；已审完返回 None。"""
    chain = tuple(chain or ())
    if 0 <= step < len(chain):
        return chain[step]
    return None


def can_review(
    *, chain: Tuple[str, ...] | list | None, step: int, actor_role: str | None,
) -> bool:
    """该角色此刻是否有权审这条样本。"""
    return next_reviewer(chain, step) == normalize_role(actor_role)


def apply_review(
    *, chain: Tuple[str, ...] | list | None, step: int, approve: bool,
) -> Tuple[str, int]:
    """执行一次审核，返回 (新状态, 新步骤)。

    驳回不推进步骤（打回后由提交人修改，重新提交会重置到第 0 步）；
    通过则步骤 +1，走完链路即 approved。
    """
    chain = tuple(chain or ())
    if not approve:
        return STATUS_REJECTED, step
    new_step = step + 1
    if new_step >= len(chain):
        return STATUS_APPROVED, new_step
    return STATUS_IN_REVIEW, new_step


def reset_for_revision(chain: Tuple[str, ...] | list | None) -> Tuple[str, int]:
    """修改/打回重审后回到链路起点。

    approved 样本被改动时必须走这里，不允许原地生效——
    否则 CI 红的时候顺手改期望值就能"变绿"。
    """
    if not tuple(chain or ()):
        return STATUS_APPROVED, 0   # 管理员样本仍直接生效
    return STATUS_IN_REVIEW, 0
