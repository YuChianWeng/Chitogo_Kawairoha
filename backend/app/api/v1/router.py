from fastapi import APIRouter

from app.api.v1.itinerary import router as itinerary_router

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


router.include_router(itinerary_router)
