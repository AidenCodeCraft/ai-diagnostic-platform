from fastapi import APIRouter

from app.api.quality.golden_samples import router as golden_samples_router
from app.api.quality.traces import router as traces_router

router = APIRouter()
router.include_router(golden_samples_router)
router.include_router(traces_router)

__all__ = ["router"]
