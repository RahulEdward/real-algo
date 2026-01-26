# routers/dashboard.py
"""
FastAPI Dashboard Router for RealAlgo

This module provides the FastAPI router equivalent of blueprints/dashboard.py.
It handles the dashboard route which displays margin/funds data.

All URL patterns and response formats are preserved for frontend compatibility.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from database.auth_db import get_api_key_for_tradingview, get_auth_token
from database.settings_db import get_analyze_mode
from dependencies_fastapi import check_session_validity, get_session
from services.funds_service import get_funds
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

# Create FastAPI router with same prefix as Flask blueprint
# The Flask blueprint uses url_prefix="/" so we use prefix="" (root)
dashboard_router = APIRouter(prefix="", tags=["dashboard"])


@dashboard_router.get("/dashboard")
async def dashboard(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """
    Dashboard route - serves the React SPA for dashboard.
    
    This is a session-protected route that validates the user session
    and serves the React frontend. The actual data fetching is done 
    via /auth/dashboard-data API endpoint.
    
    Returns:
        FileResponse: Serves the React SPA index.html
        RedirectResponse: Redirects to login/broker if session invalid
    """
    # Check if user is in session (check_session_validity already validates session)
    if "user" not in session:
        logger.warning("No user in session, redirecting to login")
        return RedirectResponse(url="/auth/login", status_code=302)
    
    login_username = session["user"]
    AUTH_TOKEN = get_auth_token(login_username)

    if AUTH_TOKEN is None:
        logger.warning(f"No auth token found for user {login_username}")
        return RedirectResponse(url="/auth/logout", status_code=302)

    broker = session.get("broker")
    if not broker:
        logger.error("Broker not set in session")
        # For React SPA, redirect to broker selection
        return RedirectResponse(url="/broker", status_code=302)

    # For React SPA, serve the index.html - React Router handles the /dashboard route
    import os
    index_path = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    
    # Fallback: return JSON response for API clients
    return JSONResponse(content={
        "status": "success",
        "message": "Dashboard ready",
        "broker": broker,
        "user": login_username
    })
