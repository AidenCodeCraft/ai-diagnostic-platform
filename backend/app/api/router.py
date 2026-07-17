from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/test")
def test():
    return {"message": "API working"}
