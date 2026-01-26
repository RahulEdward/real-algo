# routers/api_v1/synthetic_future.py
"""FastAPI Synthetic Future Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import SyntheticFutureRequest
from services.synthetic_future_service import calculate_synthetic_future
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

synthetic_future_router = APIRouter(prefix="/api/v1/syntheticfuture", tags=["syntheticfuture"])


@synthetic_future_router.post("")
@synthetic_future_router.post("/")
@limiter.limit(API_RATE_LIMIT)
async def synthetic_future_endpoint(request: Request):
    """Calculate synthetic future price using ATM options. Does NOT place any orders."""
    try:
        data = await request.json()
        try:
            SyntheticFutureRequest(**data)
        except ValidationError as e:
            logger.warning(f"Validation error in synthetic future request: {e.errors()}")
            return JSONResponse(status_code=400, content={"status": "error", "message": "Validation error", "errors": e.errors()})
        
        api_key = data.get("apikey")
        underlying = data.get("underlying")
        exchange = data.get("exchange")
        expiry_date = data.get("expiry_date")
        
        logger.info(
            f"Synthetic future calculation request: underlying={underlying}, "
            f"exchange={exchange}, expiry={expiry_date}"
        )
        
        success, response_data, status_code = calculate_synthetic_future(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date, api_key=api_key
        )
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception("An unexpected error occurred in SyntheticFuture endpoint.")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred in the API endpoint"})
