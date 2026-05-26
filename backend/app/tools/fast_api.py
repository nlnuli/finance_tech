from typing import Optional

from fastapi import APIRouter, Query

from .registry import get_enabled_tools, serialize_tool


router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools(enabled: Optional[str] = Query(default=None)) -> list[dict]:
    enabled_names = None
    if enabled:
        enabled_names = [name.strip() for name in enabled.split(",") if name.strip()]

    return [serialize_tool(tool_config) for tool_config in get_enabled_tools(enabled_names)]
