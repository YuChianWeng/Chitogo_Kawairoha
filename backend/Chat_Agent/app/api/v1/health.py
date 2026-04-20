from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter(tags=["health"])

_DATA_SERVICE_PROBE_PATH = "/api/v1/places/stats"
_PROBE_TIMEOUT_SECONDS = 1.0


async def probe_data_service(settings: Settings) -> bool:
    """Check whether the external Data Service is reachable."""
    url = f"{str(settings.data_service_base_url).rstrip('/')}{_DATA_SERVICE_PROBE_PATH}"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    data_service_reachable = await probe_data_service(settings)
    return {
        "status": "ok" if data_service_reachable else "degraded",
        "service": "agent-orchestration-backend",
        "data_service": "reachable" if data_service_reachable else "degraded",
    }
