"""审核链策略测试 —— 规则来自定稿：

    管理员提交  → 直接生效
    开发提交    → 管理员终审
    测试提交    → 开发复审 → 管理员终审
    用户提交    → 测试初审 → 开发复审 → 管理员终审
"""

import pytest

from app.services.quality.review_policy import (
    REVIEW_CHAINS,
    STATUS_APPROVED,
    STATUS_IN_REVIEW,
    STATUS_REJECTED,
    apply_review,
    can_review,
    initial_status,
    next_reviewer,
    normalize_role,
    required_review_roles,
    reset_for_revision,
)


@pytest.mark.parametrize(
    "role,expected",
    [
        ("admin", ()),
        ("developer", ("admin",)),
        ("engineer", ("developer", "admin")),
        ("user", ("engineer", "developer", "admin")),
    ],
)
def test_required_review_roles(role, expected):
    assert required_review_roles(role) == expected


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("管理员", "admin"),
        ("开发", "developer"),
        ("研发", "developer"),
        ("测试", "engineer"),
        ("qa", "engineer"),
        ("售后", "user"),
        ("产品", "user"),
        ("USER", "user"),
        (None, "user"),
        ("unknown-role", "user"),   # 未知角色按最低权限处理，宁可多审
    ],
)
def test_role_aliases_normalize(alias, expected):
    assert normalize_role(alias) == expected


def test_initial_status_admin_takes_effect_immediately():
    assert initial_status("admin") == STATUS_APPROVED
    assert initial_status("developer") == STATUS_IN_REVIEW
    assert initial_status("engineer") == STATUS_IN_REVIEW
    assert initial_status("user") == STATUS_IN_REVIEW


def test_submitter_role_never_reviews_own_sample():
    """链上永远不出现提交人自己的角色 —— 「不得自审」由构造保证。"""
    for submitter_role in REVIEW_CHAINS:
        assert normalize_role(submitter_role) not in required_review_roles(submitter_role)


def test_full_walk_engineer_submission():
    chain = required_review_roles("engineer")
    status, step = STATUS_IN_REVIEW, 0
    assert next_reviewer(chain, step) == "developer"

    # 管理员此时无权抢先审
    assert not can_review(chain=chain, step=step, actor_role="admin")
    assert can_review(chain=chain, step=step, actor_role="developer")

    status, step = apply_review(chain=chain, step=step, approve=True)
    assert (status, step) == (STATUS_IN_REVIEW, 1)
    assert next_reviewer(chain, step) == "admin"

    status, step = apply_review(chain=chain, step=step, approve=True)
    assert (status, step) == (STATUS_APPROVED, 2)
    assert next_reviewer(chain, step) is None


def test_full_walk_user_submission_is_three_levels():
    chain = required_review_roles("user")
    status, step = STATUS_IN_REVIEW, 0
    for index, expected_role in enumerate(("engineer", "developer", "admin")):
        assert next_reviewer(chain, step) == expected_role
        assert can_review(chain=chain, step=step, actor_role=expected_role)
        status, step = apply_review(chain=chain, step=step, approve=True)
        assert step == index + 1
    assert status == STATUS_APPROVED


def test_admin_submission_chain_is_empty():
    chain = required_review_roles("admin")
    assert chain == ()
    assert next_reviewer(chain, 0) is None
    assert initial_status("admin") == STATUS_APPROVED


def test_reject_does_not_advance_step():
    chain = required_review_roles("engineer")
    status, step = apply_review(chain=chain, step=0, approve=False)
    assert (status, step) == (STATUS_REJECTED, 0)


def test_reset_for_revision_sends_sample_back_to_first_reviewer():
    assert reset_for_revision(required_review_roles("user")) == (STATUS_IN_REVIEW, 0)
    # 管理员样本没有审核人，改动后仍直接生效
    assert reset_for_revision(()) == (STATUS_APPROVED, 0)
