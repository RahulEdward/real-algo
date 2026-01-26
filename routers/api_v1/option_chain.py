# routers/api_v1/option_chain.py
"""FastAPI Option Chain Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OptionChainRequest
from services.option_chain_service import get_option_chain
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

option_chain_router = APIRouter(prefix="/api/v1/optionchain", tags=["optionchain"])


@option_chain_router.post("")
@option_chain_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def option_chain_endpoint(request: Request):
    """Get option chain for underlying with real-time quotes"""
    try:
        data = await request.json()
        try:
            OptionChainRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Validation error", "errors": e.errors()})
        
        api_key = data.get("apikey")
        underlying = data.get("underlying")
        exchange = data.get("exchange")
        expiry_date = data.get("expiry_date")
        strike_count = data.get("strike_count")
        
        logger.info(
            f"Option chain request: underlying={underlying}, exchange={exchange}, "
            f"expiry={expiry_date}, strike_count={'all' if strike_count is None else strike_count}"
        )
        
        success, response, status_code = get_option_chain(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            strike_count=strike_count,
            api_key=api_key,
        )
        return JSONResponse(content=response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in option chain endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
