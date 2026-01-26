# routers/core.py
"""
FastAPI Core Router for RealAlgo
Handles setup API endpoint for initial user creation.
Requirements: 4.7

Note: GET routes for /, /download, /faq, /setup are handled by react_router
which serves the React SPA. This router only provides the setup POST API.
"""

import base64
import io
import secrets

import qrcode
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from database.auth_db import upsert_api_key
from database.user_db import add_user, find_user_by_username
from utils.logging import get_logger

logger = get_logger(__name__)

core_router = APIRouter(prefix="", tags=["core"])


def generate_api_key():
    """Generate a secure random API key."""
    return secrets.token_hex(32)


@core_router.post("/setup")
async def setup_post(request: Request):
    """
    Setup API endpoint - Creates the initial admin user.
    
    Accepts both JSON and form data for compatibility with React frontend.
    Returns JSON response with setup result and TOTP QR code data.
    """
    # Check if setup is already complete
    if find_user_by_username() is not None:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Setup already completed. Please login."}
        )

    # Parse request data (support both JSON and form data)
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        data = await request.json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
    else:
        form = await request.form()
        username = form.get("username")
        email = form.get("email")
        password = form.get("password")

    # Validate required fields
    if not username or not email or not password:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Username, email, and password are required"}
        )

    # Validate password strength
    from utils.auth_utils import validate_password_strength

    is_valid, error_message = validate_password_strength(password)
    if not is_valid:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": error_message}
        )

    # Add the new admin user
    user = add_user(username, email, password, is_admin=True)
    if user:
        logger.info(f"New admin user {username} created successfully")

        # Automatically generate and save API key
        api_key = generate_api_key()
        key_id = upsert_api_key(username, api_key)
        if not key_id:
            logger.error(f"Failed to create API key for user {username}")
        else:
            logger.info(f"API key created successfully for user {username}")

        # Generate QR code for TOTP
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(user.get_totp_uri())
        qr.make(fit=True)

        # Create QR code image
        img_buffer = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(img_buffer, format="PNG")
        qr_code = base64.b64encode(img_buffer.getvalue()).decode()

        # Store TOTP setup in session temporarily
        request.session["totp_setup"] = True
        request.session["username"] = username
        request.session["qr_code"] = qr_code
        request.session["totp_secret"] = user.totp_secret

        return JSONResponse(content={
            "status": "success",
            "message": "Admin user created successfully",
            "data": {
                "username": username,
                "qr_code": qr_code,
                "totp_secret": user.totp_secret
            }
        })
    else:
        logger.error(f"Failed to create admin user {username}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "User already exists or an error occurred"}
        )
