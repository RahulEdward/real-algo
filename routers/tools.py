# routers/tools.py
"""
FastAPI Tools Router for RealAlgo

Converted from Flask blueprints: gex, ivchart, ivsmile, oiprofile, oitracker,
straddle_chart, vol_surface.

All endpoint paths match the frontend API calls exactly.
"""

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from database.auth_db import get_api_key_for_tradingview
from dependencies_fastapi import check_session_validity
from limiter_fastapi import limiter, API_RATE_LIMIT
from utils.logging import get_logger

logger = get_logger(__name__)

tools_router = APIRouter(prefix="", tags=["tools"])

ALLOWED_OI_INTERVALS = {"1m", "5m", "15m"}


def _get_api_key(session: dict):
    """Get API key from session, return (api_key, error_response) tuple."""
    login_username = session.get("user")
    if not login_username:
        return None, JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)
    api_key = get_api_key_for_tradingview(login_username)
    if not api_key:
        return None, JSONResponse({"status": "error", "message": "API key not configured. Please generate an API key in /apikey"}, status_code=401)
    return api_key, None


def _validate_ue(underlying: str, exchange: str):
    """Validate underlying and exchange format."""
    if not underlying or not exchange:
        return "underlying and exchange are required"
    # Allow alphanumeric, &, -, _ for underlying (e.g., M&M, NIFTY-I)
    # Allow alphanumeric and _ for exchange
    if not re.match(r"^[A-Z0-9&\-_]+$", underlying, re.IGNORECASE) or not re.match(r"^[A-Z0-9_]+$", exchange, re.IGNORECASE):
        return "Invalid input format"
    return None


def _validate_expiry(expiry_date: str):
    """Validate expiry date format (DDMMMYY)."""
    if not expiry_date:
        return "expiry_date is required"
    if not re.match(r"^\d{2}[A-Z]{3}\d{2}$", expiry_date):
        return "Invalid expiry_date format. Expected DDMMMYY"
    return None


# ============================================================
# GEX (Gamma Exposure) API
# Frontend: POST /gex/api/gex-data
# ============================================================

@tools_router.post("/gex/api/gex-data")
@limiter.limit(API_RATE_LIMIT)
async def gex_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()[:20]
        exchange = data.get("exchange", "").strip()[:20]
        expiry_date = data.get("expiry_date", "").strip()[:10]

        if e := _validate_ue(underlying, exchange):
            return JSONResponse({"status": "error", "message": e}, status_code=400)
        if e := _validate_expiry(expiry_date):
            return JSONResponse({"status": "error", "message": e}, status_code=400)

        from services.gex_service import get_gex_data
        success, response, status_code = get_gex_data(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in GEX data API: {e}")
        return JSONResponse({"status": "error", "message": "An error occurred"}, status_code=500)


# ============================================================
# IV Chart API
# Frontend: POST /ivchart/api/iv-data
#           POST /ivchart/api/default-symbols
#           GET  /ivchart/api/intervals
# ============================================================

@tools_router.post("/ivchart/api/iv-data")
@limiter.limit(API_RATE_LIMIT)
async def iv_chart_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()
        exchange = data.get("exchange", "").strip()
        expiry_date = data.get("expiry_date", "").strip()
        interval = data.get("interval", "5m").strip()
        days = int(data.get("days", 1))

        if not underlying or not exchange or not expiry_date:
            return JSONResponse({"status": "error", "message": "underlying, exchange, and expiry_date are required"}, status_code=400)

        from services.iv_chart_service import get_iv_chart_data
        success, response, status_code = get_iv_chart_data(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date,
            interval=interval, api_key=api_key, days=days,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in IV chart API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@tools_router.post("/ivchart/api/default-symbols")
@limiter.limit(API_RATE_LIMIT)
async def iv_default_symbols(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()
        exchange = data.get("exchange", "").strip()
        expiry_date = data.get("expiry_date", "").strip()

        if not underlying or not exchange or not expiry_date:
            return JSONResponse({"status": "error", "message": "underlying, exchange, and expiry_date are required"}, status_code=400)

        from services.iv_chart_service import get_default_symbols
        success, response, status_code = get_default_symbols(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in default symbols API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@tools_router.get("/ivchart/api/intervals")
@limiter.limit(API_RATE_LIMIT)
async def iv_intervals(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        from services.intervals_service import get_intervals
        success, response, status_code = get_intervals(api_key=api_key)
        if success:
            data = response.get("data", {})
            intraday = {
                "seconds": data.get("seconds", []),
                "minutes": data.get("minutes", []),
                "hours": data.get("hours", []),
            }
            return JSONResponse({"status": "success", "data": intraday})
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error fetching intervals: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================
# IV Smile API
# Frontend: POST /ivsmile/api/iv-smile-data
# ============================================================

@tools_router.post("/ivsmile/api/iv-smile-data")
@limiter.limit(API_RATE_LIMIT)
async def iv_smile_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()[:20]
        exchange = data.get("exchange", "").strip()[:20]
        expiry_date = data.get("expiry_date", "").strip()[:10]

        if e := _validate_ue(underlying, exchange):
            return JSONResponse({"status": "error", "message": e}, status_code=400)

        from services.iv_smile_service import get_iv_smile_data
        success, response, status_code = get_iv_smile_data(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in IV smile API: {e}")
        return JSONResponse({"status": "error", "message": "An error occurred"}, status_code=500)


# ============================================================
# OI Profile API
# Frontend: POST /oiprofile/api/profile-data
#           GET  /oiprofile/api/intervals
# ============================================================

@tools_router.post("/oiprofile/api/profile-data")
@limiter.limit(API_RATE_LIMIT)
async def oi_profile_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()[:20]
        exchange = data.get("exchange", "").strip()[:20]
        expiry_date = data.get("expiry_date", "").strip()[:10]
        interval = data.get("interval", "5m").strip()[:5]
        days = min(int(data.get("days", 5)), 30)

        if e := _validate_ue(underlying, exchange):
            return JSONResponse({"status": "error", "message": e}, status_code=400)
        if e := _validate_expiry(expiry_date):
            return JSONResponse({"status": "error", "message": e}, status_code=400)
        if interval not in ALLOWED_OI_INTERVALS:
            return JSONResponse({"status": "error", "message": f"Invalid interval. Allowed: {', '.join(sorted(ALLOWED_OI_INTERVALS))}"}, status_code=400)

        from services.oi_profile_service import get_oi_profile_data
        success, response, status_code = get_oi_profile_data(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date,
            interval=interval, days=days, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in OI Profile API: {e}")
        return JSONResponse({"status": "error", "message": "An error occurred"}, status_code=500)


@tools_router.get("/oiprofile/api/intervals")
@limiter.limit(API_RATE_LIMIT)
async def oi_profile_intervals(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        from services.intervals_service import get_intervals
        success, response, status_code = get_intervals(api_key=api_key)
        if success:
            data = response.get("data", {})
            all_minutes = data.get("minutes", [])
            supported = [i for i in all_minutes if i in ALLOWED_OI_INTERVALS]
            return JSONResponse({"status": "success", "data": {"intervals": supported}})
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error fetching intervals: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================
# OI Tracker API
# Frontend: POST /oitracker/api/oi-data
#           POST /oitracker/api/maxpain
# ============================================================

@tools_router.post("/oitracker/api/oi-data")
@limiter.limit(API_RATE_LIMIT)
async def oi_tracker_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()[:20]
        exchange = data.get("exchange", "").strip()[:20]
        expiry_date = data.get("expiry_date", "").strip()[:10]

        if e := _validate_ue(underlying, exchange):
            return JSONResponse({"status": "error", "message": e}, status_code=400)
        if e := _validate_expiry(expiry_date):
            return JSONResponse({"status": "error", "message": e}, status_code=400)

        from services.oi_tracker_service import get_oi_data
        success, response, status_code = get_oi_data(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in OI data API: {e}")
        return JSONResponse({"status": "error", "message": "An error occurred"}, status_code=500)


@tools_router.post("/oitracker/api/maxpain")
@limiter.limit(API_RATE_LIMIT)
async def maxpain_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()[:20]
        exchange = data.get("exchange", "").strip()[:20]
        expiry_date = data.get("expiry_date", "").strip()[:10]

        if e := _validate_ue(underlying, exchange):
            return JSONResponse({"status": "error", "message": e}, status_code=400)
        if e := _validate_expiry(expiry_date):
            return JSONResponse({"status": "error", "message": e}, status_code=400)

        from services.oi_tracker_service import calculate_max_pain
        success, response, status_code = calculate_max_pain(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in Max Pain API: {e}")
        return JSONResponse({"status": "error", "message": "An error occurred"}, status_code=500)


# ============================================================
# Straddle Chart API
# Frontend: POST /straddle/api/straddle-data
#           GET  /straddle/api/intervals
# ============================================================

@tools_router.post("/straddle/api/straddle-data")
@limiter.limit(API_RATE_LIMIT)
async def straddle_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()
        exchange = data.get("exchange", "").strip()
        expiry_date = data.get("expiry_date", "").strip()
        interval = data.get("interval", "1m").strip()
        days = int(data.get("days", 5))

        if not underlying or not exchange or not expiry_date:
            return JSONResponse({"status": "error", "message": "underlying, exchange, and expiry_date are required"}, status_code=400)

        from services.straddle_chart_service import get_straddle_chart_data
        success, response, status_code = get_straddle_chart_data(
            underlying=underlying, exchange=exchange, expiry_date=expiry_date,
            interval=interval, api_key=api_key, days=days,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in straddle chart API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@tools_router.get("/straddle/api/intervals")
@limiter.limit(API_RATE_LIMIT)
async def straddle_intervals(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        from services.intervals_service import get_intervals
        success, response, status_code = get_intervals(api_key=api_key)
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error fetching intervals: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================
# Vol Surface API
# Frontend: POST /volsurface/api/surface-data
# ============================================================

@tools_router.post("/volsurface/api/surface-data")
@limiter.limit(API_RATE_LIMIT)
async def vol_surface_data(request: Request, session: dict = Depends(check_session_validity)):
    try:
        api_key, err = _get_api_key(session)
        if err: return err

        data = await request.json()
        underlying = data.get("underlying", "").strip()
        exchange = data.get("exchange", "").strip()
        expiry_dates = data.get("expiry_dates", [])
        strike_count = int(data.get("strike_count", 15))

        if not underlying or not exchange:
            return JSONResponse({"status": "error", "message": "underlying and exchange are required"}, status_code=400)
        if not expiry_dates or not isinstance(expiry_dates, list):
            return JSONResponse({"status": "error", "message": "expiry_dates must be a non-empty list"}, status_code=400)

        expiry_dates = expiry_dates[:8]
        strike_count = min(max(5, strike_count), 40)

        from services.vol_surface_service import get_vol_surface_data
        success, response, status_code = get_vol_surface_data(
            underlying=underlying, exchange=exchange, expiry_dates=expiry_dates,
            strike_count=strike_count, api_key=api_key,
        )
        return JSONResponse(response, status_code=status_code)
    except Exception as e:
        logger.exception(f"Error in vol surface API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
