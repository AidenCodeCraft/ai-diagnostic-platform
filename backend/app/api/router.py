"""Aggregate all API routers by functional domain."""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin, require_auth

# ── Auth ─────────────────────────────────────────────────────
from app.api.auth import router as auth_router
from app.api.auth.api_keys import router as api_keys_router

# ── Admin ────────────────────────────────────────────────────
from app.api.admin import router as admin_router
from app.api.admin.users import router as users_router
from app.api.admin.knowledge_review import router as knowledge_review_router

# ── Chat ─────────────────────────────────────────────────────
from app.api.chat.chat_sessions import router as chat_sessions_router
from app.api.chat.agents import router as agents_router
from app.api.chat.agent_tasks import router as agent_tasks_router
from app.api.chat.function_calling import router as function_calling_router
from app.api.chat.supervisor import router as supervisor_router
from app.api.chat.images import router as images_router

# ── Diagnostics ──────────────────────────────────────────────
from app.api.diagnostics.logs import router as logs_router
from app.api.diagnostics.parser import router as parser_router
from app.api.diagnostics.parsing import router as parsing_router
from app.api.diagnostics.analyses import router as analyses_router
from app.api.diagnostics.reports import router as reports_router

# ── Knowledge ────────────────────────────────────────────────
from app.api.knowledge import router as knowledge_router
from app.api.knowledge.vector import router as vector_router

# ── Quality（黄金集标注 / 三级审核 / 回归导出） ──────────────
from app.api.quality import router as quality_router

# ── System ───────────────────────────────────────────────────
from app.api.system.organizations import router as organizations_router
from app.api.system.projects import router as projects_router
from app.api.system.rules import router as rules_router
from app.api.system.bug_cases import router as bug_cases_router
from app.api.system.client_logs import router as client_logs_router
from app.api.system.dashboard import router as dashboard_router
from app.api.system.search import router as search_router


api_router = APIRouter()

# Auth
api_router.include_router(auth_router)
api_router.include_router(api_keys_router)

# Admin
api_router.include_router(admin_router)
api_router.include_router(users_router)
api_router.include_router(knowledge_review_router, dependencies=[Depends(require_admin)])

# Chat
api_router.include_router(chat_sessions_router)
api_router.include_router(agents_router)
api_router.include_router(agent_tasks_router)
api_router.include_router(function_calling_router)
api_router.include_router(supervisor_router)
api_router.include_router(images_router, dependencies=[Depends(require_auth)])

# Diagnostics（日志/解析/分析/报告均需登录）
api_router.include_router(logs_router, dependencies=[Depends(require_auth)])
api_router.include_router(parser_router, dependencies=[Depends(require_auth)])
api_router.include_router(parsing_router, dependencies=[Depends(require_auth)])
api_router.include_router(analyses_router, dependencies=[Depends(require_auth)])
api_router.include_router(reports_router, dependencies=[Depends(require_auth)])

# Knowledge
api_router.include_router(knowledge_router)
api_router.include_router(vector_router)

# Quality（黄金集：登录即可标注；审核权限由 review_policy 按角色决定）
api_router.include_router(quality_router)

# System（管理域：仅 admin / developer）
api_router.include_router(organizations_router, dependencies=[Depends(require_admin)])
api_router.include_router(projects_router, dependencies=[Depends(require_admin)])
api_router.include_router(rules_router, dependencies=[Depends(require_admin)])
api_router.include_router(bug_cases_router, dependencies=[Depends(require_admin)])
api_router.include_router(client_logs_router, dependencies=[Depends(require_admin)])
api_router.include_router(dashboard_router, dependencies=[Depends(require_admin)])
api_router.include_router(search_router, dependencies=[Depends(require_admin)])
