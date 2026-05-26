from typing import Optional

from fastapi import APIRouter, Query

from .registry import list_registered_tools


router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(enabled: Optional[str] = Query(default=None)) -> list[dict]:
    enabled_names = None
    if enabled:
        enabled_names = [name.strip() for name in enabled.split(",") if name.strip()]

    return list_registered_tools(enabled_names)
