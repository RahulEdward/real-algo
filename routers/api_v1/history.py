# routers/api_v1/history.py
"""FastAPI History Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import HistoryRequest
from services.history_service import get_history
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

history_router = APIRouter(prefix="/api/v1/history", tags=["history"])


@history_router.post("")
@history_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def history_endpoint(request: Request):
    """Get historical OHLCV data"""
    try:
        data = await request.json()
        try:
            HistoryRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_history(history_data=data, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in History endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
