from fastapi import APIRouter

from app.api.logs import router as logs_router

api_router = APIRouter()

api_router.include_router(logs_router)


@api_router.get("/test")
def test():
    return {"message": "API working"}
