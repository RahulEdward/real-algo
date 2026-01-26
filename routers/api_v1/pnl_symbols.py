# routers/api_v1/pnl_symbols.py
"""FastAPI PnL Symbols Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import PnlSymbolsRequest
from services.sandbox_service import is_sandbox_mode, sandbox_get_pnl_symbols
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

pnl_symbols_router = APIRouter(prefix="/api/v1/pnl", tags=["pnl"])


@pnl_symbols_router.post("/symbols")
@pnl_symbols_router.post("/symbols/")
@limiter.limit(API_RATE_LIMIT)
async def pnl_symbols_endpoint(request: Request):
    """Get day P&L breakdown by symbol (Sandbox mode only)"""
    try:
        if not is_sandbox_mode():
            return JSONResponse(status_code=400, content={
                "status": "error",
                "message": "This endpoint is only available in sandbox/analyzer mode"
            })
        
        data = await request.json()
        try:
            PnlSymbolsRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        
        success, response_data, status_code = sandbox_get_pnl_symbols(api_key, data)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.error(f"Unexpected error in pnl/symbols endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
