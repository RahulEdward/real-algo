# routers/api_v1/modify_order.py
"""FastAPI Modify Order Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import ModifyOrderRequest
from services.modify_order_service import modify_order
from utils.logging import get_logger

logger = get_logger(__name__)
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

modify_order_router = APIRouter(prefix="/api/v1/modifyorder", tags=["modify_order"])


@modify_order_router.post("")
@modify_order_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def modify_order_endpoint(request: Request):
    """Modify an existing order"""
    try:
        data = await request.json()
        try:
            ModifyOrderRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = modify_order(order_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in ModifyOrder endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
