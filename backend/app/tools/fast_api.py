from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from ..auth import current_user
from ..runtime import get_app_services


router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(
    request: Request,
    enabled: Optional[str] = Query(default=None),
    user: dict = Depends(current_user),
) -> list[dict]:
    enabled_names = None
    if enabled:
        enabled_names = [name.strip() for name in enabled.split(",") if name.strip()]

    provider = get_app_services(request.app).mcp_provider
    return provider.list_tools(enabled_names)
