# routers/api_v1/funds.py
"""FastAPI Funds Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import FundsRequest
from services.funds_service import get_funds
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

funds_router = APIRouter(prefix="/api/v1/funds", tags=["funds"])


@funds_router.post("")
@funds_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def funds_endpoint(request: Request):
    """Get account funds and margin details"""
    try:
        data = await request.json()
        try:
            FundsRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_funds(api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in Funds endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
