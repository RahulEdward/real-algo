# routers/api_v1/margin.py
"""FastAPI Margin Calculator Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from database.apilog_db import async_log_order
from database.apilog_db import executor as log_executor
from limiter_fastapi import limiter
from restx_api.pydantic_schemas import MarginCalculatorRequest
from services.margin_service import calculate_margin
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "50/second")

margin_router = APIRouter(prefix="/api/v1/margin", tags=["margin"])


@margin_router.post("")
@margin_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def margin_endpoint(request: Request):
    """Calculate margin requirement for a basket of positions"""
    data = None
    try:
        data = await request.json()
        try:
            MarginCalculatorRequest(**data)
        except ValidationError as e:
            error_message = str(e.errors())
            error_response = {"status": "error", "message": error_message}
            log_executor.submit(async_log_order, "margin", data, error_response)
            return JSONResponse(content=error_response, status_code=400)
        
        api_key = data.get("apikey")
        
        success, response_data, status_code = calculate_margin(
            margin_data=data, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("An unexpected error occurred in Margin Calculator endpoint.")
        error_response = {"status": "error", "message": "An unexpected error occurred in the API endpoint"}
        try:
            log_executor.submit(async_log_order, "margin", data if data else {}, error_response)
        except:
            pass
        return JSONResponse(content=error_response, status_code=500)
