from fastapi import APIRouter

from app.api.agent_tasks import router as agent_tasks_router
from app.api.agents import router as agents_router
from app.api.analyses import router as analyses_router
from app.api.api_keys import router as api_keys_router
from app.api.auth import router as auth_router
from app.api.bug_cases import router as bug_cases_router
from app.api.chat_sessions import router as chat_sessions_router
from app.api.knowledge import router as knowledge_router
from app.api.logs import router as logs_router
from app.api.organizations import router as organizations_router
from app.api.parser import router as parser_router
from app.api.parsing import router as parsing_router
from app.api.plugins import router as plugins_router
from app.api.projects import router as projects_router
from app.api.reports import router as reports_router
from app.api.rules import router as rules_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(organizations_router)
api_router.include_router(projects_router)
api_router.include_router(logs_router)
api_router.include_router(parser_router)
api_router.include_router(parsing_router)
api_router.include_router(analyses_router)
api_router.include_router(reports_router)
api_router.include_router(agents_router)
api_router.include_router(agent_tasks_router)
api_router.include_router(knowledge_router)
api_router.include_router(plugins_router)
api_router.include_router(rules_router)
api_router.include_router(bug_cases_router)
api_router.include_router(chat_sessions_router)
api_router.include_router(api_keys_router)


@api_router.get("/test")
def test():
    return {"message": "API working"}
