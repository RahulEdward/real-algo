# routers/api_v1/instruments.py
"""FastAPI Instruments Router for RealAlgo REST API"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from limiter_fastapi import limiter
from restx_api.pydantic_schemas import InstrumentsRequest
from services.instruments_service import get_instruments
from utils.logging import get_logger

logger = get_logger(__name__)
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10/second")

instruments_router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


@instruments_router.get("")
@instruments_router.get("/")
@limiter.limit(API_RATE_LIMIT)
async def instruments_endpoint(request: Request):
    """
    Download all instruments/symbols from the database
    
    Query Parameters:
        - apikey (required): API key for authentication
        - exchange (optional): Filter by exchange
        - format (optional): Output format - 'json' (default) or 'csv'
    """
    try:
        query_params = {
            "apikey": request.query_params.get("apikey"),
            "exchange": request.query_params.get("exchange"),
            "format": request.query_params.get("format", "json").lower(),
        }
        
        try:
            InstrumentsRequest(**query_params)
        except ValidationError as e:
            format_type = query_params.get("format", "json")
            if format_type == "csv":
                return Response(content=str(e.errors()), status_code=400, media_type="text/plain")
            return JSONResponse(status_code=400, content={"status": "error", "message": e.errors()})
        
        api_key = query_params.get("apikey")
        exchange = query_params.get("exchange")
        format_type = query_params.get("format", "json")
        
        success, response_data, status_code, headers = get_instruments(
            exchange=exchange, api_key=api_key, format=format_type
        )
        
        # Handle CSV response
        if format_type == "csv":
            if success:
                return Response(
                    content=response_data,
                    status_code=status_code,
                    media_type=headers.get("Content-Type", "text/csv"),
                    headers=headers
                )
            else:
                error_message = response_data.get("message", "An error occurred") if isinstance(response_data, dict) else str(response_data)
                return Response(content=error_message, status_code=status_code, media_type="text/plain")
        
        return JSONResponse(content=response_data, status_code=status_code)
    except Exception as e:
        logger.exception(f"Unexpected error in instruments endpoint: {e}")
        format_type = request.query_params.get("format", "json").lower()
        if format_type == "csv":
            return Response(content="An unexpected error occurred", status_code=500, media_type="text/plain")
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})
