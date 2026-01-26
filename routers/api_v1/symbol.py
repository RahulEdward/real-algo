# routers/api_v1/symbol.py
"""FastAPI Symbol Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import SymbolRequest
from services.symbol_service import get_symbol_info
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

symbol_router = APIRouter(prefix="/api/v1/symbol", tags=["symbol"])


@symbol_router.post("")
@symbol_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def symbol_endpoint(request: Request):
    """Get symbol information for a given symbol and exchange"""
    try:
        data = await request.json()
        try:
            SymbolRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        symbol = data.get("symbol")
        exchange = data.get("exchange")
        
        success, response_data, status_code = get_symbol_info(
            symbol=symbol, exchange=exchange, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in symbol endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
