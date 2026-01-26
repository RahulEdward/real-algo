# routers/api_v1/options_multiorder.py
"""FastAPI Options Multi-Order Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OptionsMultiOrderRequest
from services.options_multiorder_service import place_options_multiorder
from utils.logging import get_logger

logger = get_logger(__name__)
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

options_multiorder_router = APIRouter(prefix="/api/v1/optionsmultiorder", tags=["optionsmultiorder"])


@options_multiorder_router.post("")
@options_multiorder_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def options_multiorder_endpoint(request: Request):
    """Place multiple option legs with common underlying. BUY legs execute first for margin efficiency."""
    try:
        data = await request.json()
        try:
            OptionsMultiOrderRequest(**data)
        except ValidationError as e:
            logger.warning(f"Validation error in options multi-order request: {e.errors()}")
            return JSONResponse(status_code=400, content={"status": "error", "message": "Validation error", "errors": e.errors()})
        
        api_key = data.get("apikey")
        
        logger.info(
            f"Options multi-order API request: underlying={data.get('underlying')}, "
            f"legs={len(data.get('legs', []))}"
        )
        
        success, response_data, status_code = place_options_multiorder(
            multiorder_data=data, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("An unexpected error occurred in OptionsMultiOrder endpoint.")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred in the API endpoint"})
