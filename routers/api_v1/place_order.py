# routers/api_v1/place_order.py
"""
FastAPI Place Order Router for RealAlgo REST API
Requirements: 5.1, 5.3, 5.4
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import PlaceOrderRequest
from services.place_order_service import place_order
from utils.logging import get_logger

logger = get_logger(__name__)

ORDER_RATE_LIMIT = os.getenv("ORDER_RATE_LIMIT", "10/second")

place_order_router = APIRouter(prefix="/api/v1/placeorder", tags=["place_order"])


@place_order_router.post("")
@place_order_router.post("/")
@limiter.limit(ORDER_RATE_LIMIT)
async def place_order_endpoint(request: Request):
    """Place an order with the broker"""
    try:
        # Get the request data
        data = await request.json()
        
        # Validate with Pydantic
        try:
            order_request = PlaceOrderRequest(**data)
        except ValidationError as e:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": e.errors()}
            )
        
        # Extract API key
        api_key = data.get("apikey")
        
        # Call the service function to place the order
        success, response_data, status_code = place_order(order_data=data, api_key=api_key)
        
        return JSONResponse(content=response_data, status_code=status_code)
        
    except Exception as e:
        logger.exception("An unexpected error occurred in PlaceOrder endpoint.")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "An unexpected error occurred in the API endpoint",
            }
        )
