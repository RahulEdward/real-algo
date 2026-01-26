# routers/api_v1/option_greeks.py
"""FastAPI Option Greeks Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from database.auth_db import verify_api_key
from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OptionGreeksRequest
from services.option_greeks_service import get_option_greeks
from utils.logging import get_logger

logger = get_logger(__name__)
GREEKS_RATE_LIMIT = os.getenv("GREEKS_RATE_LIMIT", "30/minute")

option_greeks_router = APIRouter(prefix="/api/v1/optiongreeks", tags=["optiongreeks"])


@option_greeks_router.post("")
@option_greeks_router.post("/")
@limiter.limit(GREEKS_RATE_LIMIT)
async def option_greeks_endpoint(request: Request):
    """Calculate Option Greeks (Delta, Gamma, Theta, Vega, Rho) and Implied Volatility"""
    try:
        data = await request.json()
        if data is None:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Request body is missing or invalid JSON"})
        
        try:
            OptionGreeksRequest(**data)
        except ValidationError as e:
            logger.warning(f"Validation error in option greeks request: {e.errors()}")
            return JSONResponse(status_code=400, content={"status": "error", "message": "Validation failed", "errors": e.errors()})
        
        api_key = data.get("apikey")
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        interest_rate = data.get("interest_rate")
        forward_price = data.get("forward_price")
        underlying_symbol = data.get("underlying_symbol")
        underlying_exchange = data.get("underlying_exchange")
        expiry_time = data.get("expiry_time")
        
        if not verify_api_key(api_key):
            logger.warning(f"Invalid API key used for option greeks: {api_key[:10] if api_key else 'None'}...")
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid realalgo apikey"})
        
        logger.info(f"Calculating Greeks for {symbol} on {exchange}")
        if forward_price:
            logger.info(f"Using custom forward price: {forward_price}")
        elif underlying_symbol:
            logger.info(f"Using custom underlying: {underlying_symbol} on {underlying_exchange or 'auto-detected'}")
        if expiry_time:
            logger.info(f"Using custom expiry time: {expiry_time}")
        
        success, response, status_code = get_option_greeks(
            option_symbol=symbol,
            exchange=exchange,
            interest_rate=interest_rate,
            forward_price=forward_price,
            underlying_symbol=underlying_symbol,
            underlying_exchange=underlying_exchange,
            expiry_time=expiry_time,
            api_key=api_key,
        )
        
        if success:
            logger.info(f"Greeks calculated successfully: {symbol}")
        else:
            logger.error(f"Failed to calculate Greeks: {response.get('message')}")
        
        return JSONResponse(content=response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in option greeks endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error while calculating option Greeks"})
