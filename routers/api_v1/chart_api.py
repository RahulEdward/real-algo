# routers/api_v1/chart_api.py
"""FastAPI Chart API Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import ChartRequest
from services.chart_service import get_chart_preferences, update_chart_preferences
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

chart_api_router = APIRouter(prefix="/api/v1/chart", tags=["chart"])


@chart_api_router.get("")
@chart_api_router.get("/")
@limiter.limit(API_RATE_LIMIT)
async def get_chart_prefs(request: Request):
    """
    Get chart preferences.
    Pass apikey as query parameter: /api/v1/chart?apikey=your-api-key
    """
    try:
        api_key = request.query_params.get("apikey")
        if not api_key:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Missing apikey parameter"})
        
        logger.info(f"[ChartAPI] GET preferences request. API Key present: {bool(api_key)}")
        success, response_data, status_code = get_chart_preferences(api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Unexpected error in chart GET endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})


@chart_api_router.post("")
@chart_api_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def update_chart_prefs(request: Request):
    """
    Update chart preferences.
    Send apikey and preferences in JSON body.
    """
    try:
        data = await request.json()
        if not data:
            return JSONResponse(status_code=400, content={"status": "error", "message": "No data provided"})
        
        try:
            ChartRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        preferences = {k: v for k, v in data.items() if k != "apikey"}
        
        if not preferences:
            return JSONResponse(status_code=400, content={"status": "error", "message": "No preferences provided to update"})
        
        logger.info(f"[ChartAPI] POST update request. Keys: {list(preferences.keys())}")
        success, response_data, status_code = update_chart_preferences(api_key, preferences)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Unexpected error in chart POST endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
