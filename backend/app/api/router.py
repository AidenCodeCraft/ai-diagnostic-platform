"""Aggregate all API routers by functional domain."""

from fastapi import APIRouter

# ── Auth ─────────────────────────────────────────────────────
from app.api.auth import router as auth_router
from app.api.auth.api_keys import router as api_keys_router

# ── Admin ────────────────────────────────────────────────────
from app.api.admin import router as admin_router
from app.api.admin.users import router as users_router

# ── Chat ─────────────────────────────────────────────────────
from app.api.chat.chat_sessions import router as chat_sessions_router
from app.api.chat.agents import router as agents_router
from app.api.chat.agent_tasks import router as agent_tasks_router

# ── Diagnostics ──────────────────────────────────────────────
from app.api.diagnostics.logs import router as logs_router
from app.api.diagnostics.parser import router as parser_router
from app.api.diagnostics.parsing import router as parsing_router
from app.api.diagnostics.analyses import router as analyses_router
from app.api.diagnostics.reports import router as reports_router

# ── Knowledge ────────────────────────────────────────────────
from app.api.knowledge import router as knowledge_router
from app.api.knowledge.plugins import router as plugins_router

# ── System ───────────────────────────────────────────────────
from app.api.system.organizations import router as organizations_router
from app.api.system.projects import router as projects_router
from app.api.system.rules import router as rules_router
from app.api.system.bug_cases import router as bug_cases_router
from app.api.system.client_logs import router as client_logs_router


api_router = APIRouter()

# Auth
api_router.include_router(auth_router)
api_router.include_router(api_keys_router)

# Admin
api_router.include_router(admin_router)
api_router.include_router(users_router)

# Chat
api_router.include_router(chat_sessions_router)
api_router.include_router(agents_router)
api_router.include_router(agent_tasks_router)

# Diagnostics
api_router.include_router(logs_router)
api_router.include_router(parser_router)
api_router.include_router(parsing_router)
api_router.include_router(analyses_router)
api_router.include_router(reports_router)

# Knowledge
api_router.include_router(knowledge_router)
api_router.include_router(plugins_router)

# System
api_router.include_router(organizations_router)
api_router.include_router(projects_router)
api_router.include_router(rules_router)
api_router.include_router(bug_cases_router)
api_router.include_router(client_logs_router)


@api_router.get("/test")
def test():
    return {"message": "API working"}
