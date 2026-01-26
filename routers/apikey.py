# routers/apikey.py
"""
FastAPI API Key Router for RealAlgo
Handles API key management routes.
Requirements: 4.1, 4.2, 4.3, 4.4
"""

import secrets
from pathlib import Path

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from database.auth_db import (
    get_api_key,
    get_api_key_for_tradingview,
    get_order_mode,
    update_order_mode,
    upsert_api_key,
    verify_api_key,
)
from dependencies_fastapi import check_session_validity
from utils.logging import get_logger

# Path to React frontend
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

logger = get_logger(__name__)

apikey_router = APIRouter(prefix="", tags=["apikey"])
templates = Jinja2Templates(directory="templates")

# Initialize Argon2 hasher
ph = PasswordHasher()


def generate_api_key():
    """Generate a secure random API key."""
    return secrets.token_hex(32)


@apikey_router.get("/apikey")
async def get_api_key_page(request: Request, session: dict = Depends(check_session_validity)):
    """Get API key management page or data."""
    login_username = session["user"]
    api_key = get_api_key_for_tradingview(login_username)
    has_api_key = api_key is not None
    order_mode = get_order_mode(login_username) or "auto"
    logger.info(f"Checking API key status for user: {login_username}, order_mode: {order_mode}")

    # Return JSON if Accept header requests it (for React frontend)
    if request.headers.get("Accept") == "application/json":
        return JSONResponse({
            "login_username": login_username,
            "has_api_key": has_api_key,
            "api_key": api_key,
            "order_mode": order_mode,
        })

    # Serve React app for browser navigation
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")

    # Fallback to old template if React build not available
    return templates.TemplateResponse("apikey.html", {
        "request": request,
        "login_username": login_username,
        "has_api_key": has_api_key,
        "api_key": api_key,
        "order_mode": order_mode,
    })


@apikey_router.post("/apikey")
async def update_api_key(request: Request, session: dict = Depends(check_session_validity)):
    """Update or create API key."""
    data = await request.json()
    user_id = data.get("user_id")

    if not user_id:
        logger.error("API key update attempted without user ID")
        return JSONResponse({"error": "User ID is required"}, status_code=400)

    # Generate new API key
    api_key = generate_api_key()

    # Store the API key (auth_db will handle both hashing and encryption)
    key_id = upsert_api_key(user_id, api_key)

    if key_id is not None:
        logger.info(f"API key updated successfully for user: {user_id}")
        return JSONResponse({
            "message": "API key updated successfully.",
            "api_key": api_key,
            "key_id": key_id
        })
    else:
        logger.error(f"Failed to update API key for user: {user_id}")
        return JSONResponse({"error": "Failed to update API key"}, status_code=500)


@apikey_router.post("/apikey/mode")
async def update_api_key_mode(request: Request, session: dict = Depends(check_session_validity)):
    """Update order mode (auto/semi_auto) for a user."""
    try:
        data = await request.json()
        user_id = data.get("user_id")
        mode = data.get("mode")

        if not user_id:
            logger.error("Order mode update attempted without user ID")
            return JSONResponse({"error": "User ID is required"}, status_code=400)

        if not mode or mode not in ["auto", "semi_auto"]:
            logger.error(f"Invalid order mode: {mode}")
            return JSONResponse({"error": 'Invalid mode. Must be "auto" or "semi_auto"'}, status_code=400)

        # Update the order mode
        success = update_order_mode(user_id, mode)

        if success:
            logger.info(f"Order mode updated successfully for user: {user_id}, new mode: {mode}")
            return JSONResponse({"message": f"Order mode updated to {mode}", "mode": mode})
        else:
            logger.error(f"Failed to update order mode for user: {user_id}")
            return JSONResponse({"error": "Failed to update order mode"}, status_code=500)

    except Exception as e:
        logger.error(f"Error updating order mode: {e}")
        return JSONResponse({"error": "An error occurred while updating order mode"}, status_code=500)
