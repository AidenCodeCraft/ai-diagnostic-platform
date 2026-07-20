from fastapi import APIRouter

from app.api.agent_tasks import router as agent_tasks_router
from app.api.agents import router as agents_router
from app.api.analyses import router as analyses_router
from app.api.analysis_result import router as analysis_result_router
from app.api.logs import router as logs_router
from app.api.parser import router as parser_router
from app.api.parsing import router as parsing_router
from app.api.reports import router as reports_router

api_router = APIRouter()

api_router.include_router(logs_router)
api_router.include_router(parser_router)
api_router.include_router(parsing_router)
api_router.include_router(analyses_router)
api_router.include_router(analysis_result_router)
api_router.include_router(reports_router)
api_router.include_router(agents_router)
api_router.include_router(agent_tasks_router)


@api_router.get("/test")
def test():
    return {"message": "API working"}
