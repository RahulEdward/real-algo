# routers/api_v1/option_symbol.py
"""FastAPI Option Symbol Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OptionSymbolRequest
from services.option_symbol_service import get_option_symbol
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

option_symbol_router = APIRouter(prefix="/api/v1/optionsymbol", tags=["optionsymbol"])


@option_symbol_router.post("")
@option_symbol_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def option_symbol_endpoint(request: Request):
    """Get option symbol based on underlying, expiry, strike offset, and option type"""
    try:
        data = await request.json()
        try:
            OptionSymbolRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Validation error", "errors": e.errors()})
        
        api_key = data.get("apikey")
        underlying = data.get("underlying")
        exchange = data.get("exchange")
        expiry_date = data.get("expiry_date")
        strike_int = data.get("strike_int")
        offset = data.get("offset")
        option_type = data.get("option_type")
        
        logger.info(
            f"Option symbol request: underlying={underlying}, exchange={exchange}, "
            f"expiry={expiry_date}, strike_int={strike_int}, offset={offset}, type={option_type}"
        )
        
        success, response, status_code = get_option_symbol(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            strike_int=strike_int,
            offset=offset,
            option_type=option_type,
            api_key=api_key,
        )
        return JSONResponse(content=response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in option symbol endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
