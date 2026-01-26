# routers/api_v1/search.py
"""FastAPI Search Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import SearchRequest
from services.search_service import search_symbols
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

search_router = APIRouter(prefix="/api/v1/search", tags=["search"])


@search_router.post("")
@search_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def search_endpoint(request: Request):
    """Search for symbols in the database"""
    try:
        data = await request.json()
        try:
            SearchRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        query = data.get("query")
        exchange = data.get("exchange")
        
        success, response_data, status_code = search_symbols(
            query=query, exchange=exchange, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in search endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
