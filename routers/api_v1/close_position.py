# routers/api_v1/close_position.py
"""FastAPI Close Position Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import ClosePositionRequest
from services.close_position_service import close_position
from utils.logging import get_logger

logger = get_logger(__name__)
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

close_position_router = APIRouter(prefix="/api/v1/closeposition", tags=["close_position"])


@close_position_router.post("")
@close_position_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def close_position_endpoint(request: Request):
    """Close all open positions"""
    try:
        data = await request.json()
        try:
            ClosePositionRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = close_position(position_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in ClosePosition endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
