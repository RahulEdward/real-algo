# routers/api_v1/holdings.py
"""FastAPI Holdings Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import HoldingsRequest
from services.holdings_service import get_holdings
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

holdings_router = APIRouter(prefix="/api/v1/holdings", tags=["holdings"])


@holdings_router.post("")
@holdings_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def holdings_endpoint(request: Request):
    """Get holdings details"""
    try:
        data = await request.json()
        try:
            HoldingsRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_holdings(api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in Holdings endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
