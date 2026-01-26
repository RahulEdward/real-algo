# routers/api_v1/market_timings.py
"""FastAPI Market Timings Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import MarketTimingsRequest
from services.market_calendar_service import get_timings
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

market_timings_router = APIRouter(prefix="/api/v1/market/timings", tags=["market"])


@market_timings_router.post("")
@market_timings_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def market_timings_endpoint(request: Request):
    """Get market timings for a specific date"""
    try:
        data = await request.json()
        try:
            MarketTimingsRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        date_str = data.get("date")
        
        success, response_data, status_code = get_timings(date_str=date_str)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in market timings endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
