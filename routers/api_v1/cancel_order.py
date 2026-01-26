# routers/api_v1/cancel_order.py
"""FastAPI Cancel Order Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import CancelOrderRequest
from services.cancel_order_service import cancel_order
from utils.logging import get_logger

logger = get_logger(__name__)
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

cancel_order_router = APIRouter(prefix="/api/v1/cancelorder", tags=["cancel_order"])


@cancel_order_router.post("")
@cancel_order_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def cancel_order_endpoint(request: Request):
    """Cancel an existing order"""
    try:
        data = await request.json()
        try:
            CancelOrderRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = cancel_order(order_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in CancelOrder endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
