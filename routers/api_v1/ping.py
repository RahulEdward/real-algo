# routers/api_v1/ping.py
"""FastAPI Ping Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import PingRequest
from services.ping_service import get_ping
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

ping_router = APIRouter(prefix="/api/v1/ping", tags=["ping"])


@ping_router.post("")
@ping_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def ping_endpoint(request: Request):
    """Check API connectivity and authentication"""
    try:
        data = await request.json()
        try:
            PingRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        
        success, response_data, status_code = get_ping(api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Unexpected error in ping endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
