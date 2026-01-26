# routers/api_v1/analyzer.py
"""FastAPI Analyzer Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from database.apilog_db import async_log_order
from database.apilog_db import executor as log_executor
from limiter_fastapi import limiter
from restx_api.pydantic_schemas import AnalyzerRequest, AnalyzerToggleRequest
from services.analyzer_service import get_analyzer_status, toggle_analyzer_mode
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

analyzer_router = APIRouter(prefix="/api/v1/analyzer", tags=["analyzer"])


@analyzer_router.post("")
@analyzer_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def analyzer_status_endpoint(request: Request):
    """Get analyzer mode status and statistics"""
    data = None
    try:
        data = await request.json()
        try:
            AnalyzerRequest(**data)
        except ValidationError as e:
            error_message = str(e.errors())
            error_response = {"status": "error", "message": error_message}
            log_executor.submit(async_log_order, "analyzer_status", data, error_response)
            return JSONResponse(content=error_response, status_code=400)
        
        api_key = data.pop("apikey", None)
        
        success, response_data, status_code = get_analyzer_status(
            analyzer_data=data, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("An unexpected error occurred in Analyzer status endpoint.")
        error_response = {"status": "error", "message": "An unexpected error occurred"}
        log_executor.submit(async_log_order, "analyzer_status", data if data else {}, error_response)
        return JSONResponse(content=error_response, status_code=500)


@analyzer_router.post("/toggle")
@limiter.limit(API_RATE_LIMIT)
async def analyzer_toggle_endpoint(request: Request):
    """Toggle analyzer mode on/off"""
    data = None
    try:
        data = await request.json()
        try:
            AnalyzerToggleRequest(**data)
        except ValidationError as e:
            error_message = str(e.errors())
            error_response = {"status": "error", "message": error_message}
            log_executor.submit(async_log_order, "analyzer_toggle", data, error_response)
            return JSONResponse(content=error_response, status_code=400)
        
        api_key = data.pop("apikey", None)
        
        success, response_data, status_code = toggle_analyzer_mode(
            analyzer_data=data, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("An unexpected error occurred in Analyzer toggle endpoint.")
        error_response = {"status": "error", "message": "An unexpected error occurred"}
        log_executor.submit(async_log_order, "analyzer_toggle", data if data else {}, error_response)
        return JSONResponse(content=error_response, status_code=500)
