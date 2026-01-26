#!/usr/bin/env python3
"""
FastAPI Security Middleware

This module provides security middleware for FastAPI that:
- Checks if client IP is banned using IPBan.is_ip_banned()
- Returns 403 Forbidden for banned IPs
- Logs blocked attempts
- Handles proxy headers to get real client IP

Matches Flask SecurityMiddleware behavior exactly.

Requirements: 8.1
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from database.traffic_db import IPBan
from utils.logging import get_logger

logger = get_logger(__name__)


def get_real_ip(request: Request) -> str:
    """
    Get the real client IP address from FastAPI Request, handling proxy headers.
    
    Checks headers in order of preference:
    1. CF-Connecting-IP (Cloudflare - highest priority)
    2. True-Client-IP (Cloudflare Enterprise)
    3. X-Real-IP (commonly set by nginx)
    4. X-Forwarded-For (standard proxy header, uses first IP if multiple)
    5. X-Client-IP (some proxies)
    6. request.client.host (fallback to direct connection)
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
        ips = [ip.strip() for ip in forwarded_for.split(",")]
        if ips and ips[0]:
            return ips[0]
    
    # Try X-Client-IP
    client_ip = request.headers.get("X-Client-IP")
    if client_ip:
        return client_ip
    
    # Fallback to client host
    if request.client:
        return request.client.host
    
    return "unknown"


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check for banned IPs and handle security.
    Matches Flask SecurityMiddleware behavior exactly.
    """
    
    async def dispatch(self, request: Request, call_next):
        client_ip = get_real_ip(request)
        
        if IPBan.is_ip_banned(client_ip):
            logger.warning(f"Blocked banned IP: {client_ip}")
            return PlainTextResponse(
                content="Access Denied: Your IP has been banned",
                status_code=403
            )
        
        return await call_next(request)
