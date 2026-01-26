# routers/api_v1/basket_order.py
"""FastAPI Basket Order Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from database.apilog_db import async_log_order
from database.apilog_db import executor as log_executor
from database.settings_db import get_analyze_mode
from limiter_fastapi import limiter
from restx_api.pydantic_schemas import BasketOrderRequest
from services.basket_order_service import emit_analyzer_error, place_basket_order
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

basket_order_router = APIRouter(prefix="/api/v1/basketorder", tags=["basketorder"])


@basket_order_router.post("")
@basket_order_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def basket_order_endpoint(request: Request):
    """Place multiple orders in a basket"""
    data = None
    try:
        data = await request.json()
        try:
            BasketOrderRequest(**data)
        except ValidationError as e:
            error_message = str(e.errors())
            if get_analyze_mode():
                return JSONResponse(content=emit_analyzer_error(data, error_message), status_code=400)
            error_response = {"status": "error", "message": error_message}
            log_executor.submit(async_log_order, "basketorder", data, error_response)
            return JSONResponse(content=error_response, status_code=400)
        
        api_key = data.pop("apikey", None)
        
        success, response_data, status_code = place_basket_order(
            basket_data=data, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error("An unexpected error occurred in BasketOrder endpoint.")
        error_message = "An unexpected error occurred"
        if get_analyze_mode():
            return JSONResponse(content=emit_analyzer_error(data, error_message), status_code=500)
        error_response = {"status": "error", "message": error_message}
        log_executor.submit(async_log_order, "basketorder", data if data else {}, error_response)
        return JSONResponse(content=error_response, status_code=500)
