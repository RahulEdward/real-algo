# routers/gc_json.py
"""
FastAPI GoCharting JSON Router for RealAlgo
Generates webhook JSON for GoCharting alerts.
Requirements: 4.7
"""

import os
from collections import OrderedDict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from database.auth_db import get_api_key_for_tradingview
from database.symbol import enhanced_search_symbols
from dependencies_fastapi import check_session_validity, get_session
from utils.logging import get_logger

logger = get_logger(__name__)

host = os.getenv("HOST_SERVER")

templates = Jinja2Templates(directory="templates")

gc_json_router = APIRouter(prefix="/gocharting", tags=["gc_json"])


@gc_json_router.get("/")
async def gocharting_json_get(
    request: Request,
    _: None = Depends(check_session_validity)
):
    """Render GoCharting configuration page."""
    return templates.TemplateResponse("gocharting.html", {"request": request, "host": host})


@gc_json_router.post("/")
async def gocharting_json_post(
    request: Request,
    session: dict = Depends(get_session),
    _: None = Depends(check_session_validity)
):
    """Generate GoCharting webhook JSON."""
    try:
        data = await request.json()
        symbol_input = data.get("symbol")
        exchange = data.get("exchange")
        product = data.get("product")
        action = data.get("action")
        quantity = data.get("quantity")

        if not all([symbol_input, exchange, product, action, quantity]):
            logger.error("Missing required fields in GoCharting request")
            return JSONResponse(content={"error": "Missing required fields"}, status_code=400)

        logger.info(
            f"Processing GoCharting request - Symbol: {symbol_input}, Exchange: {exchange}, "
            f"Product: {product}, Action: {action}, Quantity: {quantity}"
        )

        api_key = get_api_key_for_tradingview(session.get("user"))

        if not api_key:
            logger.error(f"API key not found for user: {session.get('user')}")
            return JSONResponse(content={"error": "API key not found"}, status_code=404)

        symbols = enhanced_search_symbols(symbol_input, exchange)
        if not symbols:
            logger.warning(f"Symbol not found: {symbol_input}")
            return JSONResponse(content={"error": "Symbol not found"}, status_code=404)

        symbol_data = symbols[0]
        logger.info(f"Found matching symbol: {symbol_data.symbol}")

        json_data = OrderedDict([
            ("apikey", api_key),
            ("strategy", "GoCharting"),
            ("symbol", symbol_data.symbol),
            ("action", action.upper()),
            ("exchange", symbol_data.exchange),
            ("pricetype", "MARKET"),
            ("product", product),
            ("quantity", str(quantity)),
        ])

        logger.info("Successfully generated GoCharting webhook data")
        return JSONResponse(content=dict(json_data))

    except Exception as e:
        logger.error(f"Error processing GoCharting request: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
