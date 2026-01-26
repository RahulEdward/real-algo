# routers/api_v1/orderstatus.py
"""FastAPI Order Status Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OrderStatusRequest
from services.orderstatus_service import get_order_status
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

orderstatus_router = APIRouter(prefix="/api/v1/orderstatus", tags=["orderstatus"])


@orderstatus_router.post("")
@orderstatus_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def orderstatus_endpoint(request: Request):
    """Get order status"""
    try:
        data = await request.json()
        try:
            OrderStatusRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_order_status(order_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in OrderStatus endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
