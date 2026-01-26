# routers/api_v1/multi_option_greeks.py
"""FastAPI Multi Option Greeks Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from database.auth_db import verify_api_key
from limiter_fastapi import limiter
from restx_api.pydantic_schemas import MultiOptionGreeksRequest
from services.option_greeks_service import get_multi_option_greeks
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

multi_option_greeks_router = APIRouter(prefix="/api/v1/multioptiongreeks", tags=["multioptiongreeks"])


@multi_option_greeks_router.post("")
@multi_option_greeks_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def multi_option_greeks_endpoint(request: Request):
    """Calculate Option Greeks for multiple symbols in a single request"""
    try:
        data = await request.json()
        if data is None:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Request body is missing or invalid JSON"})
        
        try:
            MultiOptionGreeksRequest(**data)
        except ValidationError as e:
            logger.warning(f"Validation error in multi option greeks request: {e.errors()}")
            return JSONResponse(status_code=400, content={"status": "error", "message": "Validation failed", "errors": e.errors()})
        
        api_key = data.get("apikey")
        symbols = data.get("symbols")
        interest_rate = data.get("interest_rate")
        expiry_time = data.get("expiry_time")
        
        if not verify_api_key(api_key):
            logger.warning(f"Invalid API key used for multi option greeks: {api_key[:10] if api_key else 'None'}...")
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid realalgo apikey"})
        
        logger.info(f"Calculating Greeks for {len(symbols)} symbols")
        
        success, response, status_code = get_multi_option_greeks(
            symbols=symbols,
            interest_rate=interest_rate,
            expiry_time=expiry_time,
            api_key=api_key,
        )
        
        if success:
            logger.info(f"Multi Greeks calculated: {response.get('summary', {})}")
        else:
            logger.error(f"Failed to calculate multi Greeks: {response.get('message')}")
        
        return JSONResponse(content=response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in multi option greeks endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error while calculating option Greeks"})
