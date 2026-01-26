# routers/api_v1/place_smart_order.py
"""FastAPI Place Smart Order Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import SmartOrderRequest
from services.place_smart_order_service import place_smart_order
from utils.logging import get_logger

logger = get_logger(__name__)
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

place_smart_order_router = APIRouter(prefix="/api/v1/placesmartorder", tags=["place_smart_order"])


@place_smart_order_router.post("")
@place_smart_order_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def place_smart_order_endpoint(request: Request):
    """Place a smart order with position management"""
    try:
        data = await request.json()
        try:
            SmartOrderRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = place_smart_order(order_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in PlaceSmartOrder endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
