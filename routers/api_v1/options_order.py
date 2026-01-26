# routers/api_v1/options_order.py
"""FastAPI Options Order Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import OptionsOrderRequest
from services.place_options_order_service import place_options_order
from utils.logging import get_logger

logger = get_logger(__name__)
ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

options_order_router = APIRouter(prefix="/api/v1/optionsorder", tags=["optionsorder"])


@options_order_router.post("")
@options_order_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def options_order_endpoint(request: Request):
    """Place an options order by resolving the symbol based on underlying and offset"""
    try:
        data = await request.json()
        try:
            OptionsOrderRequest(**data)
        except ValidationError as e:
            logger.warning(f"Validation error in options order request: {e.errors()}")
            return JSONResponse(status_code=400, content={"status": "error", "message": "Validation error", "errors": e.errors()})
        
        api_key = data.get("apikey")
        
        logger.info(
            f"Options order API request: underlying={data.get('underlying')}, "
            f"offset={data.get('offset')}, action={data.get('action')}"
        )
        
        success, response_data, status_code = place_options_order(
            options_data=data, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("An unexpected error occurred in OptionsOrder endpoint.")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred in the API endpoint"})
