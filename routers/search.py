# routers/search.py
"""
FastAPI Search Router for RealAlgo
Handles symbol search routes with FNO filters.
Requirements: 4.1, 4.2, 4.3, 4.4
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from database.symbol import enhanced_search_symbols
from database.token_db_enhanced import fno_search_symbols
from database.token_db_enhanced import get_distinct_expiries_cached as get_distinct_expiries
from database.token_db_enhanced import get_distinct_underlyings_cached as get_distinct_underlyings
from dependencies_fastapi import check_session_validity
from utils.logging import get_logger

logger = get_logger(__name__)

search_router = APIRouter(prefix="/search", tags=["search"])
templates = Jinja2Templates(directory="templates")

# FNO exchanges that support advanced filters
FNO_EXCHANGES = ["NFO", "BFO", "MCX", "CDS"]


@search_router.get("/token")
async def token(request: Request, session: dict = Depends(check_session_validity)):
    """Route for the search form page."""
    return templates.TemplateResponse("token.html", {"request": request})


@search_router.get("/")
async def search(
    request: Request,
    symbol: str = Query("", alias="symbol"),
    exchange: Optional[str] = Query(None),
    expiry: str = Query(""),
    instrumenttype: str = Query(""),
    underlying: str = Query(""),
    strike_min: str = Query(""),
    strike_max: str = Query(""),
    session: dict = Depends(check_session_validity)
):
    """Main search route for full results page with FNO filters."""
    query = symbol.strip() or None
    expiry_val = expiry.strip() or None
    instrumenttype_val = instrumenttype.strip() or None
    underlying_val = underlying.strip() or None

    # Parse strike range
    strike_min_val = float(strike_min.strip()) if strike_min.strip() else None
    strike_max_val = float(strike_max.strip()) if strike_max.strip() else None

    # Check if any FNO filters are applied
    has_fno_filters = any([expiry_val, instrumenttype_val, underlying_val, strike_min_val, strike_max_val])

    # For non-FNO exchanges, query is required
    if not query and not (exchange in FNO_EXCHANGES and has_fno_filters):
        logger.info("Empty search query received without FNO filters")
        return templates.TemplateResponse("token.html", {
            "request": request,
            "flash_message": "Please enter a search term or select FNO filters.",
            "flash_category": "error"
        })

    # Use FNO search if any FNO filters are applied or it's an FNO exchange
    if has_fno_filters or exchange in FNO_EXCHANGES:
        logger.info(
            f"FNO search: query={query}, exchange={exchange}, expiry={expiry_val}, "
            f"type={instrumenttype_val}, underlying={underlying_val}, strike={strike_min_val}-{strike_max_val}"
        )
        results_dicts = fno_search_symbols(
            query=query,
            exchange=exchange,
            expiry=expiry_val,
            instrumenttype=instrumenttype_val,
            strike_min=strike_min_val,
            strike_max=strike_max_val,
            underlying=underlying_val,
        )
    else:
        logger.info(f"Standard search: query={query}, exchange={exchange}")
        results = enhanced_search_symbols(query, exchange)
        from database.qty_freeze_db import get_freeze_qty_for_option

        results_dicts = [
            {
                "symbol": result.symbol,
                "brsymbol": result.brsymbol,
                "name": result.name,
                "exchange": result.exchange,
                "brexchange": result.brexchange,
                "token": result.token,
                "expiry": result.expiry,
                "strike": result.strike,
                "lotsize": result.lotsize,
                "instrumenttype": result.instrumenttype,
                "tick_size": result.tick_size,
                "freeze_qty": get_freeze_qty_for_option(result.symbol, result.exchange),
            }
            for result in results
        ]

    if not results_dicts:
        logger.info(f"No results found for query: {query}")
        return templates.TemplateResponse("token.html", {
            "request": request,
            "flash_message": "No matching symbols found.",
            "flash_category": "error"
        })

    logger.info(f"Found {len(results_dicts)} results for query: {query}")
    return templates.TemplateResponse("search.html", {"request": request, "results": results_dicts})


@search_router.get("/api/search")
async def api_search(
    request: Request,
    q: str = Query(""),
    exchange: Optional[str] = Query(None),
    expiry: str = Query(""),
    instrumenttype: str = Query(""),
    underlying: str = Query(""),
    strike_min: str = Query(""),
    strike_max: str = Query(""),
    session: dict = Depends(check_session_validity)
):
    """API endpoint for AJAX search suggestions with FNO filters."""
    query = q.strip() or None
    expiry_val = expiry.strip() or None
    instrumenttype_val = instrumenttype.strip() or None
    underlying_val = underlying.strip() or None

    strike_min_val = float(strike_min.strip()) if strike_min.strip() else None
    strike_max_val = float(strike_max.strip()) if strike_max.strip() else None

    has_fno_filters = any([expiry_val, instrumenttype_val, underlying_val, strike_min_val, strike_max_val])

    if not query and not (exchange in FNO_EXCHANGES and has_fno_filters):
        logger.debug("Empty API search query received without FNO filters")
        return JSONResponse({"results": []})

    if has_fno_filters or exchange in FNO_EXCHANGES:
        logger.debug(f"FNO API search: query={query}, exchange={exchange}, filters={has_fno_filters}")
        results_dicts = fno_search_symbols(
            query=query,
            exchange=exchange,
            expiry=expiry_val,
            instrumenttype=instrumenttype_val,
            strike_min=strike_min_val,
            strike_max=strike_max_val,
            underlying=underlying_val,
        )
        results_dicts = [
            {
                "symbol": r["symbol"],
                "brsymbol": r["brsymbol"],
                "name": r["name"],
                "exchange": r["exchange"],
                "brexchange": r.get("brexchange", ""),
                "token": r["token"],
                "expiry": r["expiry"],
                "strike": r["strike"],
                "lotsize": r.get("lotsize"),
                "instrumenttype": r["instrumenttype"],
                "freeze_qty": r.get("freeze_qty", 1),
            }
            for r in results_dicts
        ]
    else:
        logger.debug(f"Standard API search: query={query}, exchange={exchange}")
        results = enhanced_search_symbols(query, exchange)
        from database.qty_freeze_db import get_freeze_qty_for_option

        results_dicts = [
            {
                "symbol": result.symbol,
                "brsymbol": result.brsymbol,
                "name": result.name,
                "exchange": result.exchange,
                "brexchange": result.brexchange,
                "token": result.token,
                "expiry": result.expiry,
                "strike": result.strike,
                "lotsize": result.lotsize,
                "instrumenttype": result.instrumenttype,
                "freeze_qty": get_freeze_qty_for_option(result.symbol, result.exchange),
            }
            for result in results
        ]

    logger.debug(f"API search found {len(results_dicts)} results")
    return JSONResponse({"results": results_dicts})


@search_router.get("/api/expiries")
async def api_expiries(
    request: Request,
    exchange: str = Query(""),
    underlying: str = Query(""),
    session: dict = Depends(check_session_validity)
):
    """API endpoint to get available expiry dates for FNO symbols."""
    exchange_val = exchange.strip() or None
    underlying_val = underlying.strip() or None

    logger.debug(f"Fetching expiries: exchange={exchange_val}, underlying={underlying_val}")
    expiries = get_distinct_expiries(exchange=exchange_val, underlying=underlying_val)

    return JSONResponse({"status": "success", "expiries": expiries})


@search_router.get("/api/underlyings")
async def api_underlyings(
    request: Request,
    exchange: str = Query(""),
    session: dict = Depends(check_session_validity)
):
    """API endpoint to get available underlying symbols for FNO."""
    exchange_val = exchange.strip() or None

    logger.debug(f"Fetching underlyings: exchange={exchange_val}")
    underlyings = get_distinct_underlyings(exchange=exchange_val)

    return JSONResponse({"status": "success", "underlyings": underlyings})
