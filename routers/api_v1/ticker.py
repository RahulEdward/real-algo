# routers/api_v1/ticker.py
"""FastAPI Ticker Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import TickerRequest
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

ticker_router = APIRouter(prefix="/api/v1/ticker", tags=["ticker"])


@ticker_router.post("")
@ticker_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def ticker_endpoint(request: Request):
    """Get ticker data for TradingView charts"""
    try:
        from services.market_data_service import get_ticker
        data = await request.json()
        try:
            TickerRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_ticker(ticker_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in Ticker endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
