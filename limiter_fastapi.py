# limiter_fastapi.py
"""
FastAPI Rate Limiter Configuration using slowapi

This module provides rate limiting for FastAPI using slowapi,
which is the FastAPI equivalent of Flask-Limiter.

Configuration:
- Uses memory storage (same as Flask-Limiter)
- Uses moving-window strategy (same as Flask-Limiter)
- Preserves all rate limit values from .env

Rate limits from .env:
- LOGIN_RATE_LIMIT_MIN = "5 per minute"
- LOGIN_RATE_LIMIT_HOUR = "25 per hour"
- RESET_RATE_LIMIT = "15 per hour"
- API_RATE_LIMIT = "50 per second"
- ORDER_RATE_LIMIT = "10 per second"
- SMART_ORDER_RATE_LIMIT = "2 per second"
- WEBHOOK_RATE_LIMIT = "100 per minute"
- STRATEGY_RATE_LIMIT = "200 per minute"

Requirements: 7.2
"""

import os
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_real_ip(request: Request) -> str:
    """
    Get the real client IP address from FastAPI Request, handling proxy headers.
    
    This function checks headers in order of preference to handle various
    proxy configurations (Cloudflare, nginx, etc.):
    
    1. CF-Connecting-IP (Cloudflare - highest priority)
    2. True-Client-IP (Cloudflare Enterprise)
    3. X-Real-IP (commonly set by nginx)
    4. X-Forwarded-For (standard proxy header, uses first IP if multiple)
    5. X-Client-IP (some proxies)
    6. request.client.host (fallback to direct connection)
    
    Args:
        request: FastAPI Request object
        
    Returns:
        str: The most likely real client IP address
    """
    # Try Cloudflare header first
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    
    # Try Cloudflare Enterprise header
    true_client = request.headers.get("True-Client-IP")
    if true_client:
        return true_client
    
    # Try X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Try X-Forwarded-For
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
        # The first IP should be the original client
        ips = [ip.strip() for ip in forwarded_for.split(",")]
        if ips and ips[0]:
            return ips[0]
    
    # Try X-Client-IP
    client_ip = request.headers.get("X-Client-IP")
    if client_ip:
        return client_ip
    
    # Fallback to slowapi's default get_remote_address
    return get_remote_address(request)


# Initialize slowapi Limiter with same configuration as Flask-Limiter
# - key_func: Function to extract client identifier (IP address)
# - storage_uri: "memory://" for in-memory storage (same as Flask-Limiter)
# - strategy: "moving-window" for sliding window rate limiting (same as Flask-Limiter)
limiter = Limiter(
    key_func=get_real_ip,
    storage_uri="memory://",
    strategy="moving-window",
)


# ============================================================
# Rate Limit Values from Environment Variables
# These match the Flask-Limiter configuration exactly
# ============================================================


def get_login_rate_limit_min() -> str:
    """
    Get login rate limit per minute.
    Default: "5 per minute" (5/minute in slowapi format)
    """
    limit = os.getenv("LOGIN_RATE_LIMIT_MIN", "5 per minute")
    return _convert_to_slowapi_format(limit)


def get_login_rate_limit_hour() -> str:
    """
    Get login rate limit per hour.
    Default: "25 per hour" (25/hour in slowapi format)
    """
    limit = os.getenv("LOGIN_RATE_LIMIT_HOUR", "25 per hour")
    return _convert_to_slowapi_format(limit)


def get_reset_rate_limit() -> str:
    """
    Get password reset rate limit.
    Default: "15 per hour" (15/hour in slowapi format)
    """
    limit = os.getenv("RESET_RATE_LIMIT", "15 per hour")
    return _convert_to_slowapi_format(limit)


def get_api_rate_limit() -> str:
    """
    Get general API rate limit.
    Default: "50 per second" (50/second in slowapi format)
    """
    limit = os.getenv("API_RATE_LIMIT", "50 per second")
    return _convert_to_slowapi_format(limit)


def get_order_rate_limit() -> str:
    """
    Get order placement rate limit.
    Default: "10 per second" (10/second in slowapi format)
    """
    limit = os.getenv("ORDER_RATE_LIMIT", "10 per second")
    return _convert_to_slowapi_format(limit)


def get_smart_order_rate_limit() -> str:
    """
    Get smart order rate limit.
    Default: "2 per second" (2/second in slowapi format)
    """
    limit = os.getenv("SMART_ORDER_RATE_LIMIT", "2 per second")
    return _convert_to_slowapi_format(limit)


def get_webhook_rate_limit() -> str:
    """
    Get webhook rate limit.
    Default: "100 per minute" (100/minute in slowapi format)
    """
    limit = os.getenv("WEBHOOK_RATE_LIMIT", "100 per minute")
    return _convert_to_slowapi_format(limit)


def get_strategy_rate_limit() -> str:
    """
    Get strategy rate limit.
    Default: "200 per minute" (200/minute in slowapi format)
    """
    limit = os.getenv("STRATEGY_RATE_LIMIT", "200 per minute")
    return _convert_to_slowapi_format(limit)


def _convert_to_slowapi_format(limit: str) -> str:
    """
    Convert Flask-Limiter format to slowapi format.
    
    Flask-Limiter format: "5 per minute", "10 per second", "25 per hour"
    slowapi format: "5/minute", "10/second", "25/hour"
    
    Args:
        limit: Rate limit string in Flask-Limiter format
        
    Returns:
        Rate limit string in slowapi format
    """
    if not limit:
        return limit
    
    # Handle already converted format (e.g., "5/minute")
    if "/" in limit:
        return limit
    
    # Convert "X per Y" to "X/Y"
    # Handle variations: "5 per minute", "5per minute", "5 perminute"
    limit = limit.strip().lower()
    
    # Replace "per" with "/" and clean up spaces
    if " per " in limit:
        parts = limit.split(" per ")
        if len(parts) == 2:
            count = parts[0].strip()
            period = parts[1].strip()
            return f"{count}/{period}"
    
    # Handle "Xper Y" format
    if "per " in limit:
        parts = limit.split("per ")
        if len(parts) == 2:
            count = parts[0].strip()
            period = parts[1].strip()
            return f"{count}/{period}"
    
    # Return as-is if format is not recognized
    return limit


# ============================================================
# Rate Limit Constants (for convenience)
# These can be used directly in route decorators
# ============================================================

# Login rate limits
LOGIN_RATE_LIMIT_MIN = get_login_rate_limit_min()
LOGIN_RATE_LIMIT_HOUR = get_login_rate_limit_hour()

# Password reset rate limit
RESET_RATE_LIMIT = get_reset_rate_limit()

# API rate limits
API_RATE_LIMIT = get_api_rate_limit()
ORDER_RATE_LIMIT = get_order_rate_limit()
SMART_ORDER_RATE_LIMIT = get_smart_order_rate_limit()

# Webhook and strategy rate limits
WEBHOOK_RATE_LIMIT = get_webhook_rate_limit()
STRATEGY_RATE_LIMIT = get_strategy_rate_limit()


# ============================================================
# Usage Examples
# ============================================================
#
# from limiter_fastapi import limiter, LOGIN_RATE_LIMIT_MIN, LOGIN_RATE_LIMIT_HOUR
#
# @router.post("/login")
# @limiter.limit(LOGIN_RATE_LIMIT_MIN)
# @limiter.limit(LOGIN_RATE_LIMIT_HOUR)
# async def login(request: Request):
#     ...
#
# @router.post("/api/v1/placeorder")
# @limiter.limit(ORDER_RATE_LIMIT)
# async def place_order(request: Request):
#     ...
#
# Note: The limiter must be added to the FastAPI app state:
#
# from limiter_fastapi import limiter
# from slowapi import _rate_limit_exceeded_handler
# from slowapi.errors import RateLimitExceeded
#
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
#
# Or use the custom handler in app_fastapi.py (already implemented)
