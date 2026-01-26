# routers/api_v1/multiquotes.py
"""FastAPI Multi-Quotes Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import MultiQuotesRequest
from services.quotes_service import get_multiquotes
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

multiquotes_router = APIRouter(prefix="/api/v1/multiquotes", tags=["multiquotes"])


@multiquotes_router.post("")
@multiquotes_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def multiquotes_endpoint(request: Request):
    """Get real-time quotes for multiple symbols"""
    try:
        data = await request.json()
        try:
            MultiQuotesRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        symbols = data.get("symbols")
        success, response_data, status_code = get_multiquotes(symbols=symbols, api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in MultiQuotes endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
