# routers/api_v1/depth.py
"""FastAPI Market Depth Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import DepthRequest
from services.depth_service import get_depth
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

depth_router = APIRouter(prefix="/api/v1/depth", tags=["depth"])


@depth_router.post("")
@depth_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def depth_endpoint(request: Request):
    """Get market depth for a symbol"""
    try:
        data = await request.json()
        try:
            DepthRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        success, response_data, status_code = get_depth(symbol=symbol, exchange=exchange, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in Depth endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
