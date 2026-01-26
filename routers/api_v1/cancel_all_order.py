# routers/api_v1/cancel_all_order.py
"""FastAPI Cancel All Orders Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import CancelAllOrderRequest
from services.cancel_all_order_service import cancel_all_orders
from utils.logging import get_logger

logger = get_logger(__name__)
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

cancel_all_order_router = APIRouter(prefix="/api/v1/cancelallorder", tags=["cancel_all_order"])


@cancel_all_order_router.post("")
@cancel_all_order_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def cancel_all_order_endpoint(request: Request):
    """Cancel all pending orders"""
    try:
        data = await request.json()
        try:
            CancelAllOrderRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = cancel_all_orders(order_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in CancelAllOrder endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
