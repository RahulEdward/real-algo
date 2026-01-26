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
from fastapi.responses import JSONResponse, RedirectResponse

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
    Dashboard route - displays margin/funds data.
    
    This is a session-protected route that:
    1. Validates the user has an auth token
    2. Checks if broker is set in session
    3. Gets funds data (from sandbox in analyze mode, or live broker)
    4. Returns margin data or redirects to logout on failure
    
    For the React SPA, this route redirects to the React dashboard page.
    The actual data fetching is done via /auth/dashboard-data API endpoint.
    
    Returns:
        RedirectResponse: Redirects to React dashboard or logout on error
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

    # Check if in analyze mode and route accordingly
    if get_analyze_mode():
        # Get API key for sandbox mode
        api_key = get_api_key_for_tradingview(login_username)
        if api_key:
            success, response, status_code = get_funds(api_key=api_key)
        else:
            logger.error("No API key found for analyze mode")
            # Redirect to dashboard page - React will handle the error display
            return RedirectResponse(url="/dashboard", status_code=302)
    else:
        # Use live broker
        success, response, status_code = get_funds(auth_token=AUTH_TOKEN, broker=broker)

    if not success:
        logger.error(f"Failed to get funds data: {response.get('message', 'Unknown error')}")
        if status_code == 404:
            # Failed to import broker module - serious error
            logger.error("Failed to import broker module")
        return RedirectResponse(url="/auth/logout", status_code=302)

    margin_data = response.get("data", {})

    # Check if margin_data is empty (authentication failed)
    if not margin_data:
        logger.error(
            f"Failed to get margin data for user {login_username} - authentication may have expired"
        )
        return RedirectResponse(url="/auth/logout", status_code=302)

    # Check if all values are zero (but don't log warning during known service hours)
    if (
        margin_data.get("availablecash") == "0.00"
        and margin_data.get("collateral") == "0.00"
        and margin_data.get("utiliseddebits") == "0.00"
    ):
        # This could be service hours or authentication issue
        # The service already logs the appropriate message
        logger.debug(f"All margin data values are zero for user {login_username}")

    # For React SPA, redirect to the React dashboard page
    # The React app will fetch data via /auth/dashboard-data API
    return RedirectResponse(url="/dashboard", status_code=302)
