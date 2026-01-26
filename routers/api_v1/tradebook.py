# routers/api_v1/tradebook.py
"""FastAPI Tradebook Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import TradebookRequest
from services.tradebook_service import get_tradebook
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

tradebook_router = APIRouter(prefix="/api/v1/tradebook", tags=["tradebook"])


@tradebook_router.post("")
@tradebook_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def tradebook_endpoint(request: Request):
    """Get trade book details"""
    try:
        data = await request.json()
        try:
            TradebookRequest(**data)
        except ValidationError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = data.get("apikey")
        success, response_data, status_code = get_tradebook(api_key=api_key)
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("Error in Tradebook endpoint")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
