# routers/api_v1/expiry.py
"""FastAPI Expiry Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import ExpiryRequest
from services.expiry_service import get_expiry_dates
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

expiry_router = APIRouter(prefix="/api/v1/expiry", tags=["expiry"])


@expiry_router.post("")
@expiry_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def expiry_endpoint(request: Request):
    """Get expiry dates for F&O symbols (futures or options) for a given underlying symbol"""
    try:
        data = await request.json()
        try:
            ExpiryRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        instrumenttype = data.get("instrumenttype")
        
        success, response_data, status_code = get_expiry_dates(
            symbol=symbol, exchange=exchange, instrumenttype=instrumenttype, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in expiry endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
