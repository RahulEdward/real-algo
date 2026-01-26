# routers/api_v1/openposition.py
"""FastAPI Open Position Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OpenPositionRequest
from services.openposition_service import get_open_position
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

openposition_router = APIRouter(prefix="/api/v1/openposition", tags=["openposition"])


@openposition_router.post("")
@openposition_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def openposition_endpoint(request: Request):
    """Get open position for a symbol"""
    try:
        data = await request.json()
        try:
            OpenPositionRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_open_position(position_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in OpenPosition endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
