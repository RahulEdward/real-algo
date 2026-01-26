# routers/api_v1/market_holidays.py
"""FastAPI Market Holidays Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import MarketHolidaysRequest
from services.market_calendar_service import get_holidays
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

market_holidays_router = APIRouter(prefix="/api/v1/market/holidays", tags=["market"])


@market_holidays_router.post("")
@market_holidays_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def market_holidays_endpoint(request: Request):
    """Get market holidays for a specific year"""
    try:
        data = await request.json()
        try:
            MarketHolidaysRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        year = data.get("year")
        
        success, response_data, status_code = get_holidays(year=year)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in market holidays endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
