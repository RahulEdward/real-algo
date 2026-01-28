"""
Traffic Logger Middleware for FastAPI

This module provides traffic logging middleware that logs all HTTP requests
to the traffic database for monitoring and analytics.
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from database.traffic_db import TrafficLog, logs_session
from utils.ip_helper import get_real_ip
from utils.logging import get_logger

logger = get_logger(__name__)


class TrafficLoggerMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for logging HTTP traffic.
    
    Logs all requests except:
    - Static files and favicon
    - Traffic monitoring endpoints themselves
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Skip logging for:
        # 1. Static files and favicon
        # 2. Traffic monitoring endpoints themselves
        if (
            path.startswith("/static/")
            or path == "/favicon.ico"
            or path.startswith("/api/v1/latency/logs")
            or path.startswith("/traffic/")
            or path.startswith("/traffic/api/")
        ):
            return await call_next(request)
        
        # Record start time
        start_time = time.time()
        
        # Process the request
        error_message = None
        status_code = 500
        
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as e:
            error_message = str(e)
            raise
        finally:
            # Log the request
            try:
                duration_ms = (time.time() - start_time) * 1000
                
                # Get user_id from session if available
                user_id = None
                try:
                    user_id = request.session.get("user")
                except Exception:
                    pass
                
                TrafficLog.log_request(
                    client_ip=get_real_ip(request),
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    host=request.headers.get("host", ""),
                    error=error_message,
                    user_id=user_id,
                )
            except Exception as e:
                logger.error(f"Error logging traffic: {e}")
            finally:
                logs_session.remove()


def init_traffic_logging(app):
    """
    Initialize traffic logging middleware for FastAPI.
    
    Args:
        app: FastAPI application instance
    """
    # Initialize the logs database
    from database.traffic_db import init_logs_db
    init_logs_db()
    
    # Add middleware
    app.add_middleware(TrafficLoggerMiddleware)
