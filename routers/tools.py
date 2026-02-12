# routers/tools.py
"""
FastAPI Tools Router for RealAlgo

Tools Hub APIs: GEX, IV Chart, IV Smile, OI Profile, OI Tracker, Straddle, Vol Surface, Health
Converted from Flask blueprints to FastAPI.
"""

import csv
import io
import re
from datetime import datetime
from typing import List, Optional

import pytz
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from database.auth_db import get_api_key_for_tradingview, get_auth_token
from database.health_db import HealthAlert, HealthMetric, health_session
from limiter_fastapi import limiter, API_RATE_LIMIT
from services.gex_service import get_gex_data
from services.intervals_service import get_intervals
from services.iv_chart_service import get_default_symbols, get_iv_chart_data
from services.iv_smile_service import get_iv_smile_data
from services.oi_profile_service import get_oi_profile_data
from services.oi_tracker_service import calculate_max_pain, get_oi_data
from services.straddle_chart_service import get_straddle_chart_data
from services.vol_surface_service import get_vol_surface_data
from utils.health_monitor import check_db_connectivity, get_cached_health_status
from utils.logging import get_logger
from utils.session_compat import session as thread_session

logger = get_logger(__name__)

tools_router = APIRouter(prefix="", tags=["tools"])

ALLOWED_OI_INTERVALS = {"1m", "5m", "15m"}


def get_session_data(request: Request) -> dict:
    """Get session data from request."""
    return dict(request.session) if hasattr(request, "session") else {}


# ============================================================================
# Pydantic Models
# ============================================================================

class GexRequest(BaseModel):
    underlying: str = Field(..., max_length=20)
    exchange: str = Field(..., max_length=20)
    expiry_date: str = Field(..., max_length=10)


class IVChartRequest(BaseModel):
    underlying: str
    exchange: str
    expiry_date: str
    interval: str = "5m"
    days: int = 1


class IVSmileRequest(BaseModel):
    underlying: str = Field(..., max_length=20)
    exchange: str = Field(..., max_length=20)
    expiry_date: str = Field(..., max_length=10)


class OIProfileRequest(BaseModel):
    underlying: str = Field(..., max_length=20)
    exchange: str = Field(..., max_length=20)
    expiry_date: str = Field(..., max_length=10)
    interval: str = Field(default="5m", max_length=5)
    days: int = 5


class OITrackerRequest(BaseModel):
    underlying: str = Field(..., max_length=20)
    exchange: str = Field(..., max_length=20)
    expiry_date: str = Field(..., max_length=10)


class StraddleRequest(BaseModel):
    underlying: str
    exchange: str
    expiry_date: str
    interval: str = "1m"
    days: int = 5


class VolSurfaceRequest(BaseModel):
    underlying: str
    exchange: str
    expiry_dates: List[str]
    strike_count: int = 15


# ============================================================================
# Helper Functions
# ============================================================================

def _get_api_key(session: dict):
    """Get API key from session."""
    login_username = session.get("user")
    if not login_username:
        return None, JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)
    api_key = get_api_key_for_tradingview(login_username)
    if not api_key:
        return None, JSONResponse({"status": "error", "message": "API key not configured"}, status_code=401)
    return api_key, None


def _validate_params(underlying: str, exchange: str):
    """Validate underlying and exchange."""
    if not underlying or not exchange:
        return "underlying and exchange are required"
    if not re.match(r"^[A-Z0-9&\-_]+$", underlying, re.IGNORECASE):
        return "Invalid underlying format"
    if not re.match(r"^[A-Z0-9_]+$", exchange, re.IGNORECASE):
        return "Invalid exchange format"
    return None


def _validate_expiry(expiry_date: str):
    """Validate expiry date format (DDMMMYY)."""
    if not expiry_date:
        return "expiry_date is required"
    if not re.match(r"^\d{2}[A-Z]{3}\d{2}$", expiry_date):
        return "Invalid expiry_date format"
    return None


def convert_to_ist(timestamp):
    """Convert UTC timestamp to IST"""
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    utc = pytz.timezone("UTC")
    ist = pytz.timezone("Asia/Kolkata")
    if timestamp.tzinfo is None:
        timestamp = utc.localize(timestamp)
    return timestamp.astimezone(ist)


def format_ist_time(timestamp):
    """Format timestamp in IST with 12-hour format"""
    ist_time = convert_to_ist(timestamp)
    return ist_time.strftime("%d-%m-%Y %I:%M:%S %p")


# ============================================================================
# GEX Routes
# ============================================================================

@tools_router.post("/gex/api/gex-data")
@limiter.limit(API_RATE_LIMIT)
async def gex_data(request: Request, data: GexRequest):
    """Get GEX data for all strikes."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        underlying = data.underlying.strip()[:20]
        exchange = data.exchange.strip()[:20]
        expiry_date = data.expiry_date.strip()[:10]

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        if not re.match(r"^[A-Z0-9]+$", underlying) or not re.match(r"^[A-Z0-9_]+$", exchange):
            return JSONResponse({"status": "error", "message": "Invalid input format"}, status_code=400)

        if not re.match(r"^\d{2}[A-Z]{3}\d{2}$", expiry_date):
            return JSONResponse(
                {"status": "error", "message": "Invalid expiry_date format. Expected DDMMMYY"},
                status_code=400
            )

        success, response, status_code = get_gex_data(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            api_key=api_key,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in GEX data API: {e}")
        return JSONResponse(
            {"status": "error", "message": "An error occurred processing your request"},
            status_code=500
        )


# ============================================================================
# IV Chart Routes
# ============================================================================

@tools_router.post("/ivchart/api/iv-data")
@limiter.limit(API_RATE_LIMIT)
async def iv_data(request: Request, data: IVChartRequest):
    """Get intraday IV time series for ATM CE and PE options."""
    try:
        session = get_session_data(request)
        broker = session.get("broker")
        if not broker:
            return JSONResponse({"status": "error", "message": "Broker not set in session"}, status_code=400)

        login_username = session.get("user")
        auth_token = get_auth_token(login_username)
        if auth_token is None:
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        api_key = get_api_key_for_tradingview(login_username)
        if not api_key:
            return JSONResponse(
                {"status": "error", "message": "API key not configured. Please generate an API key in /apikey"},
                status_code=401
            )

        underlying = data.underlying.strip()
        exchange = data.exchange.strip()
        expiry_date = data.expiry_date.strip()
        interval = data.interval.strip()
        days = data.days

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        success, response, status_code = get_iv_chart_data(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            interval=interval,
            api_key=api_key,
            days=days,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in IV chart API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@tools_router.post("/ivchart/api/default-symbols")
@limiter.limit(API_RATE_LIMIT)
async def default_symbols(request: Request, data: GexRequest):
    """Get ATM CE and PE symbol names for the given underlying and expiry."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        underlying = data.underlying.strip()
        exchange = data.exchange.strip()
        expiry_date = data.expiry_date.strip()

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        success, response, status_code = get_default_symbols(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            api_key=api_key,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in default symbols API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@tools_router.get("/ivchart/api/intervals")
@limiter.limit(API_RATE_LIMIT)
async def ivchart_intervals(request: Request):
    """Get broker-supported intraday intervals."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        success, response, status_code = get_intervals(api_key=api_key)

        if success:
            data = response.get("data", {})
            intraday = {
                "seconds": data.get("seconds", []),
                "minutes": data.get("minutes", []),
                "hours": data.get("hours", []),
            }
            return JSONResponse({"status": "success", "data": intraday}, status_code=200)

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error fetching intervals: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================================
# IV Smile Routes
# ============================================================================

@tools_router.post("/ivsmile/api/iv-smile-data")
@limiter.limit(API_RATE_LIMIT)
async def iv_smile_data(request: Request, data: IVSmileRequest):
    """Get IV Smile data for all strikes."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        underlying = data.underlying.strip()[:20]
        exchange = data.exchange.strip()[:20]
        expiry_date = data.expiry_date.strip()[:10]

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        if not re.match(r"^[A-Z0-9]+$", underlying) or not re.match(r"^[A-Z0-9_]+$", exchange):
            return JSONResponse({"status": "error", "message": "Invalid input format"}, status_code=400)

        if not re.match(r"^\d{2}[A-Z]{3}\d{2}$", expiry_date):
            return JSONResponse(
                {"status": "error", "message": "Invalid expiry_date format. Expected DDMMMYY"},
                status_code=400
            )

        success, response, status_code = get_iv_smile_data(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            api_key=api_key,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in IV Smile data API: {e}")
        return JSONResponse(
            {"status": "error", "message": "An error occurred processing your request"},
            status_code=500
        )


# ============================================================================
# OI Profile Routes
# ============================================================================

@tools_router.post("/oiprofile/api/profile-data")
@limiter.limit(API_RATE_LIMIT)
async def profile_data(request: Request, data: OIProfileRequest):
    """Get OI Profile data (futures candles + OI + OI change)."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        underlying = data.underlying.strip()[:20]
        exchange = data.exchange.strip()[:20]
        expiry_date = data.expiry_date.strip()[:10]
        interval = data.interval.strip()[:5]
        days = min(data.days, 30)

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        if not re.match(r"^[A-Z0-9]+$", underlying) or not re.match(r"^[A-Z0-9_]+$", exchange):
            return JSONResponse({"status": "error", "message": "Invalid input format"}, status_code=400)

        if not re.match(r"^\d{2}[A-Z]{3}\d{2}$", expiry_date):
            return JSONResponse(
                {"status": "error", "message": "Invalid expiry_date format. Expected DDMMMYY"},
                status_code=400
            )

        if interval not in ALLOWED_OI_INTERVALS:
            return JSONResponse(
                {"status": "error", "message": f"Invalid interval. Allowed: {', '.join(sorted(ALLOWED_OI_INTERVALS))}"},
                status_code=400
            )

        success, response, status_code = get_oi_profile_data(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            interval=interval,
            days=days,
            api_key=api_key,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in OI Profile data API: {e}")
        return JSONResponse(
            {"status": "error", "message": "An error occurred processing your request"},
            status_code=500
        )


@tools_router.get("/oiprofile/api/intervals")
@limiter.limit(API_RATE_LIMIT)
async def oiprofile_intervals(request: Request):
    """Get broker-supported intervals filtered to 1m, 5m, 15m."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        success, response, status_code = get_intervals(api_key=api_key)

        if success:
            data = response.get("data", {})
            all_minutes = data.get("minutes", [])
            supported = [i for i in all_minutes if i in ALLOWED_OI_INTERVALS]
            return JSONResponse({"status": "success", "data": {"intervals": supported}}, status_code=200)

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error fetching intervals: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================================
# OI Tracker Routes
# ============================================================================

@tools_router.post("/oitracker/api/oi-data")
@limiter.limit(API_RATE_LIMIT)
async def oi_data(request: Request, data: OITrackerRequest):
    """Get Open Interest data for all strikes."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        underlying = data.underlying.strip()[:20]
        exchange = data.exchange.strip()[:20]
        expiry_date = data.expiry_date.strip()[:10]

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        if not re.match(r"^[A-Z0-9]+$", underlying) or not re.match(r"^[A-Z0-9_]+$", exchange):
            return JSONResponse({"status": "error", "message": "Invalid input format"}, status_code=400)

        if not re.match(r"^\d{2}[A-Z]{3}\d{2}$", expiry_date):
            return JSONResponse(
                {"status": "error", "message": "Invalid expiry_date format. Expected DDMMMYY"},
                status_code=400
            )

        success, response, status_code = get_oi_data(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            api_key=api_key,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in OI data API: {e}")
        return JSONResponse(
            {"status": "error", "message": "An error occurred processing your request"},
            status_code=500
        )


@tools_router.post("/oitracker/api/maxpain")
@limiter.limit(API_RATE_LIMIT)
async def maxpain(request: Request, data: OITrackerRequest):
    """Calculate Max Pain for an underlying/expiry."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        underlying = data.underlying.strip()[:20]
        exchange = data.exchange.strip()[:20]
        expiry_date = data.expiry_date.strip()[:10]

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        if not re.match(r"^[A-Z0-9]+$", underlying) or not re.match(r"^[A-Z0-9_]+$", exchange):
            return JSONResponse({"status": "error", "message": "Invalid input format"}, status_code=400)

        if not re.match(r"^\d{2}[A-Z]{3}\d{2}$", expiry_date):
            return JSONResponse(
                {"status": "error", "message": "Invalid expiry_date format. Expected DDMMMYY"},
                status_code=400
            )

        success, response, status_code = calculate_max_pain(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            api_key=api_key,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in Max Pain API: {e}")
        return JSONResponse(
            {"status": "error", "message": "An error occurred processing your request"},
            status_code=500
        )


# ============================================================================
# Straddle Chart Routes
# ============================================================================

@tools_router.post("/straddle/api/straddle-data")
@limiter.limit(API_RATE_LIMIT)
async def straddle_data(request: Request, data: StraddleRequest):
    """Get Dynamic ATM Straddle time series for charting."""
    try:
        session = get_session_data(request)
        broker = session.get("broker")
        if not broker:
            return JSONResponse({"status": "error", "message": "Broker not set in session"}, status_code=400)

        login_username = session.get("user")
        auth_token = get_auth_token(login_username)
        if auth_token is None:
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        api_key = get_api_key_for_tradingview(login_username)
        if not api_key:
            return JSONResponse(
                {"status": "error", "message": "API key not configured. Please generate an API key in /apikey"},
                status_code=401
            )

        underlying = data.underlying.strip()
        exchange = data.exchange.strip()
        expiry_date = data.expiry_date.strip()
        interval = data.interval.strip()
        days = data.days

        if not underlying or not exchange or not expiry_date:
            return JSONResponse(
                {"status": "error", "message": "underlying, exchange, and expiry_date are required"},
                status_code=400
            )

        success, response, status_code = get_straddle_chart_data(
            underlying=underlying,
            exchange=exchange,
            expiry_date=expiry_date,
            interval=interval,
            api_key=api_key,
            days=days,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in straddle chart API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@tools_router.get("/straddle/api/intervals")
@limiter.limit(API_RATE_LIMIT)
async def straddle_intervals(request: Request):
    """Get broker-supported intervals for the straddle chart."""
    try:
        session = get_session_data(request)
        api_key, error = _get_api_key(session)
        if error:
            return error

        success, response, status_code = get_intervals(api_key=api_key)
        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error fetching intervals: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================================
# Vol Surface Routes
# ============================================================================

@tools_router.post("/volsurface/api/surface-data")
@limiter.limit(API_RATE_LIMIT)
async def surface_data(request: Request, data: VolSurfaceRequest):
    """Get 3D volatility surface data across strikes and expiries."""
    try:
        session = get_session_data(request)
        broker = session.get("broker")
        if not broker:
            return JSONResponse({"status": "error", "message": "Broker not set in session"}, status_code=400)

        login_username = session.get("user")
        auth_token = get_auth_token(login_username)
        if auth_token is None:
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        api_key = get_api_key_for_tradingview(login_username)
        if not api_key:
            return JSONResponse(
                {"status": "error", "message": "API key not configured. Please generate an API key in /apikey"},
                status_code=401
            )

        underlying = data.underlying.strip()
        exchange = data.exchange.strip()
        expiry_dates = data.expiry_dates
        strike_count = data.strike_count

        if not underlying or not exchange:
            return JSONResponse(
                {"status": "error", "message": "underlying and exchange are required"},
                status_code=400
            )

        if not expiry_dates or not isinstance(expiry_dates, list):
            return JSONResponse(
                {"status": "error", "message": "expiry_dates must be a non-empty list"},
                status_code=400
            )

        # Limit to 8 expiries max
        expiry_dates = expiry_dates[:8]
        strike_count = min(max(5, strike_count), 40)

        success, response, status_code = get_vol_surface_data(
            underlying=underlying,
            exchange=exchange,
            expiry_dates=expiry_dates,
            strike_count=strike_count,
            api_key=api_key,
        )

        return JSONResponse(response, status_code=status_code)

    except Exception as e:
        logger.exception(f"Error in vol surface API: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================================
# Health Routes
# ============================================================================

@tools_router.get("/health/status")
@limiter.limit("300/minute")
async def simple_health(request: Request):
    """
    Simple health check endpoint for AWS ELB, Kubernetes probes, Docker healthcheck.
    Returns instant 200 OK if service is running.
    Does not require authentication.
    """
    try:
        health_status = get_cached_health_status()

        status_code = 200
        if health_status["status"] == "warn":
            status_code = 200
        elif health_status["status"] == "fail":
            status_code = 503

        return JSONResponse(
            {
                "status": health_status["status"],
                "version": "1.0",
                "serviceId": "openalgo",
                "description": "OpenAlgo Trading Platform",
            },
            status_code=status_code,
        )
    except Exception as e:
        logger.error(f"Error in simple health check: {e}")
        return JSONResponse({"status": "fail", "description": str(e)}, status_code=503)


@tools_router.get("/health/check")
@limiter.limit("60/minute")
async def detailed_health_check(request: Request):
    """
    Detailed health check with component status.
    Includes database connectivity checks.
    Does not require authentication.
    """
    try:
        cached_status = get_cached_health_status()
        db_check = check_db_connectivity()
        current_metric = HealthMetric.get_current_metrics()

        checks = {}

        # Database connectivity checks
        if db_check and "databases" in db_check:
            checks["database:connectivity"] = []
            for db_name, status in db_check["databases"].items():
                checks["database:connectivity"].append(
                    {
                        "componentId": db_name,
                        "status": status,
                        "time": datetime.utcnow().isoformat() + "Z",
                    }
                )

        # File descriptor checks
        if current_metric and current_metric.fd_count is not None:
            checks["system:file-descriptors"] = [
                {
                    "componentId": "fd_count",
                    "status": current_metric.fd_status or "pass",
                    "observedValue": current_metric.fd_count,
                    "observedUnit": "count",
                    "time": current_metric.timestamp.isoformat() + "Z" if current_metric.timestamp else None,
                }
            ]

        # Memory checks
        if current_metric and current_metric.memory_rss_mb is not None:
            checks["system:memory"] = [
                {
                    "componentId": "rss",
                    "status": current_metric.memory_status or "pass",
                    "observedValue": round(current_metric.memory_rss_mb, 2),
                    "observedUnit": "MiB",
                    "time": current_metric.timestamp.isoformat() + "Z" if current_metric.timestamp else None,
                }
            ]

        # WebSocket proxy health
        try:
            from websocket_proxy import get_resource_health
            ws_health = get_resource_health()
            checks["websocket:proxy"] = [
                {
                    "componentId": "websocket_proxy",
                    "status": "pass",
                    "observedValue": ws_health.get("active_pools", {}).get("count", 0),
                    "observedUnit": "count",
                    "time": datetime.utcnow().isoformat() + "Z",
                }
            ]
        except Exception:
            pass

        # Overall status
        overall_status = "pass"
        if db_check["status"] == "fail":
            overall_status = "fail"
        elif cached_status["status"] == "fail":
            overall_status = "fail"
        elif cached_status["status"] == "warn" or db_check["status"] == "warn":
            overall_status = "warn"

        status_code = 200
        if overall_status == "fail":
            status_code = 503

        return JSONResponse(
            {
                "status": overall_status,
                "version": "1.0",
                "serviceId": "openalgo",
                "description": "OpenAlgo Trading Platform",
                "checks": checks,
            },
            status_code=status_code,
        )

    except Exception as e:
        logger.exception(f"Error in detailed health check: {e}")
        return JSONResponse(
            {
                "status": "fail",
                "version": "1.0",
                "serviceId": "openalgo",
                "description": str(e),
            },
            status_code=503,
        )


@tools_router.get("/health/api/current")
@limiter.limit("60/minute")
async def get_current_metrics(request: Request):
    """Get current metrics snapshot"""
    try:
        session = get_session_data(request)
        if not session.get("user"):
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        metric = HealthMetric.get_current_metrics()
        if not metric:
            return JSONResponse({"error": "No metrics available"}, status_code=404)

        return JSONResponse({
            "timestamp": convert_to_ist(metric.timestamp).isoformat(),
            "fd": {
                "count": metric.fd_count,
                "limit": metric.fd_limit,
                "usage_percent": metric.fd_usage_percent,
                "status": metric.fd_status,
            },
            "memory": {
                "rss_mb": metric.memory_rss_mb,
                "vms_mb": metric.memory_vms_mb,
                "percent": metric.memory_percent,
                "available_mb": metric.memory_available_mb,
                "swap_mb": metric.memory_swap_mb,
                "status": metric.memory_status,
            },
            "database": {
                "total": metric.db_connections_total,
                "connections": metric.db_connections,
                "status": metric.db_status,
            },
            "websocket": {
                "total": metric.ws_connections_total,
                "connections": metric.ws_connections,
                "total_symbols": metric.ws_total_symbols,
                "status": metric.ws_status,
            },
            "threads": {
                "count": metric.thread_count,
                "stuck": metric.stuck_threads,
                "status": metric.thread_status,
                "details": metric.thread_details,
            },
            "processes": metric.process_details or [],
            "overall_status": metric.overall_status,
        })
    except Exception as e:
        logger.exception(f"Error fetching current metrics: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@tools_router.get("/health/api/history")
@limiter.limit("60/minute")
async def get_metrics_history(request: Request, hours: int = Query(default=24, ge=1, le=168)):
    """Get metrics history"""
    try:
        session = get_session_data(request)
        if not session.get("user"):
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        metrics = HealthMetric.get_metrics_history(hours=hours)

        return JSONResponse([
            {
                "timestamp": convert_to_ist(m.timestamp).isoformat(),
                "fd_count": m.fd_count,
                "memory_rss_mb": m.memory_rss_mb,
                "db_connections": m.db_connections_total,
                "ws_connections": m.ws_connections_total,
                "threads": m.thread_count,
                "overall_status": m.overall_status,
            }
            for m in metrics
        ])
    except Exception as e:
        logger.exception(f"Error fetching metrics history: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@tools_router.get("/health/api/stats")
@limiter.limit("60/minute")
async def get_health_stats(request: Request, hours: int = Query(default=24, ge=1, le=168)):
    """Get aggregated statistics"""
    try:
        session = get_session_data(request)
        if not session.get("user"):
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        stats = HealthMetric.get_stats(hours=hours)
        return JSONResponse(stats)
    except Exception as e:
        logger.exception(f"Error fetching stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@tools_router.get("/health/api/alerts")
@limiter.limit("60/minute")
async def get_alerts(request: Request):
    """Get active alerts"""
    try:
        session = get_session_data(request)
        if not session.get("user"):
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        alerts = HealthAlert.get_active_alerts()
        return JSONResponse([
            {
                "id": alert.id,
                "timestamp": convert_to_ist(alert.timestamp).isoformat(),
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "metric_name": alert.metric_name,
                "metric_value": alert.metric_value,
                "threshold_value": alert.threshold_value,
                "message": alert.message,
                "acknowledged": alert.acknowledged,
                "resolved": alert.resolved,
            }
            for alert in alerts
        ])
    except Exception as e:
        logger.exception(f"Error fetching alerts: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@tools_router.post("/health/api/alerts/{alert_id}/acknowledge")
@limiter.limit("30/minute")
async def acknowledge_alert(request: Request, alert_id: int):
    """Acknowledge an alert"""
    try:
        session = get_session_data(request)
        if not session.get("user"):
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        success = HealthAlert.acknowledge_alert(alert_id)
        if success:
            return JSONResponse({"status": "success", "message": "Alert acknowledged"})
        return JSONResponse({"status": "error", "message": "Alert not found"}, status_code=404)
    except Exception as e:
        logger.exception(f"Error acknowledging alert: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@tools_router.post("/health/api/alerts/{alert_id}/resolve")
@limiter.limit("30/minute")
async def resolve_alert(request: Request, alert_id: int):
    """Resolve an alert"""
    try:
        session = get_session_data(request)
        if not session.get("user"):
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        success = HealthAlert.resolve_alert(alert_id)
        if success:
            return JSONResponse({"status": "success", "message": "Alert resolved"})
        return JSONResponse({"status": "error", "message": "Alert not found"}, status_code=404)
    except Exception as e:
        logger.exception(f"Error resolving alert: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@tools_router.get("/health/export")
@limiter.limit("10/minute")
async def export_metrics(request: Request, hours: int = Query(default=24, ge=1, le=168)):
    """Export metrics to CSV"""
    try:
        session = get_session_data(request)
        if not session.get("user"):
            return JSONResponse({"status": "error", "message": "Authentication required"}, status_code=401)

        metrics = HealthMetric.get_metrics_history(hours=hours)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Date & Time (IST)",
            "FD Count",
            "FD Limit",
            "FD Status",
            "Memory (MB)",
            "Memory Status",
            "DB Connections",
            "DB Status",
            "WebSocket Connections",
            "WS Status",
            "Threads",
            "Thread Status",
            "Overall Status",
        ])

        for metric in metrics:
            writer.writerow([
                format_ist_time(metric.timestamp),
                metric.fd_count or 0,
                metric.fd_limit or 0,
                metric.fd_status or "unknown",
                round(metric.memory_rss_mb, 2) if metric.memory_rss_mb else 0,
                metric.memory_status or "unknown",
                metric.db_connections_total or 0,
                metric.db_status or "unknown",
                metric.ws_connections_total or 0,
                metric.ws_status or "unknown",
                metric.thread_count or 0,
                metric.thread_status or "unknown",
                metric.overall_status or "unknown",
            ])

        csv_data = output.getvalue()

        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=health_metrics.csv"},
        )

    except Exception as e:
        logger.exception(f"Error exporting metrics: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
