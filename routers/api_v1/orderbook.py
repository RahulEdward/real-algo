# routers/api_v1/orderbook.py
"""FastAPI Orderbook Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OrderbookRequest
from services.orderbook_service import get_orderbook
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

orderbook_router = APIRouter(prefix="/api/v1/orderbook", tags=["orderbook"])


@orderbook_router.post("")
@orderbook_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def orderbook_endpoint(request: Request):
    """Get order book details"""
    try:
        data = await request.json()
        try:
            OrderbookRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_orderbook(api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in Orderbook endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
