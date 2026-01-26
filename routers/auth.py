# routers/auth.py
"""
FastAPI Auth Router for RealAlgo

This module provides the FastAPI router equivalent of blueprints/auth.py.
It handles all authentication-related routes including:
- Login/logout
- Password reset (TOTP and email)
- Session management
- SMTP configuration
- Profile management
- Analyzer mode toggle

All URL patterns and response formats are preserved for frontend compatibility.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.6
"""

import os
import re
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from database.auth_db import auth_cache, feed_token_cache, upsert_auth
from database.settings_db import get_smtp_settings, set_smtp_settings
from database.user_db import (
    User,
    authenticate_user,
    db_session,
    find_user_by_email,
    find_user_by_username,
)
from dependencies_fastapi import check_session_validity, get_session
from limiter_fastapi import (
    limiter,
    LOGIN_RATE_LIMIT_MIN,
    LOGIN_RATE_LIMIT_HOUR,
    RESET_RATE_LIMIT,
)
from utils.email_debug import debug_smtp_connection
from utils.email_utils import send_password_reset_email, send_test_email
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

# Create FastAPI router with same prefix as Flask blueprint
auth_router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================================
# Rate Limit Error Handler
# ============================================================


@auth_router.get("/csrf-token")
async def get_csrf_token(request: Request):
    """
    Return a CSRF token for React SPA to use in form submissions.
    
    This endpoint generates a new CSRF token and stores it in the session.
    The token should be included in subsequent POST/PUT/DELETE requests.
    """
    token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = token
    return JSONResponse(content={"csrf_token": token})


@auth_router.get("/broker-config")
async def get_broker_config(
    request: Request,
    session: Dict[str, Any] = Depends(get_session)
):
    """Return broker configuration for React SPA."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Not authenticated"}
        )

    BROKER_API_KEY = os.getenv("BROKER_API_KEY")
    REDIRECT_URL = os.getenv("REDIRECT_URL")

    # Extract broker name from redirect URL
    match = re.search(r"/([^/]+)/callback$", REDIRECT_URL) if REDIRECT_URL else None
    broker_name = match.group(1) if match else None

    if not broker_name:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Broker not configured"}
        )

    return JSONResponse(content={
        "status": "success",
        "broker_name": broker_name,
        "broker_api_key": BROKER_API_KEY,
        "redirect_url": REDIRECT_URL,
    })


@auth_router.get("/check-setup")
async def check_setup_required():
    """Check if initial setup is required (no users exist)."""
    needs_setup = find_user_by_username() is None
    return JSONResponse(content={"status": "success", "needs_setup": needs_setup})


@auth_router.api_route("/login", methods=["GET", "POST"])
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
@limiter.limit(LOGIN_RATE_LIMIT_HOUR)
async def login(request: Request, session: Dict[str, Any] = Depends(get_session)):
    """
    Handle login requests.
    
    GET: Redirect to appropriate page based on session state
    POST: Authenticate user and return JSON response
    """
    # Handle POST requests first (for React SPA / AJAX login)
    if request.method == "POST":
        # Check if setup is required
        if find_user_by_username() is None:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Please complete initial setup first.",
                    "redirect": "/setup",
                }
            )

        # Check if already logged in
        if "user" in session:
            return JSONResponse(content={
                "status": "success",
                "message": "Already logged in",
                "redirect": "/broker"
            })

        if session.get("logged_in"):
            return JSONResponse(content={
                "status": "success",
                "message": "Already logged in",
                "redirect": "/dashboard"
            })

        # Get form data
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        
        # Debug logging
        logger.debug(f"Login attempt for user: {username}, password length: {len(password)}")

        if authenticate_user(username, password):
            session["user"] = username  # Set the username in the session
            logger.info(f"Login success for user: {username}")
            # Redirect to broker login without marking as fully logged in
            return JSONResponse(content={"status": "success"})
        else:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Invalid credentials"}
            )

    # Handle GET requests - redirect to React frontend
    if find_user_by_username() is None:
        return RedirectResponse(url="/setup", status_code=302)

    if "user" in session:
        return RedirectResponse(url="/broker", status_code=302)

    if session.get("logged_in"):
        return RedirectResponse(url="/dashboard", status_code=302)

    return RedirectResponse(url="/login", status_code=302)


@auth_router.api_route("/broker", methods=["GET", "POST"])
@limiter.limit(LOGIN_RATE_LIMIT_MIN)
@limiter.limit(LOGIN_RATE_LIMIT_HOUR)
async def broker_login(request: Request, session: Dict[str, Any] = Depends(get_session)):
    """Handle broker login page."""
    if session.get("logged_in"):
        return RedirectResponse(url="/dashboard", status_code=302)
    
    if request.method == "GET":
        if "user" not in session:
            return RedirectResponse(url="/login", status_code=302)

        # Redirect to React broker selection page
        return RedirectResponse(url="/broker", status_code=302)
    
    # POST method - just redirect for now (broker auth handled elsewhere)
    return RedirectResponse(url="/broker", status_code=302)



@auth_router.api_route("/reset-password", methods=["GET", "POST"])
@limiter.limit(RESET_RATE_LIMIT)
async def reset_password(request: Request, session: Dict[str, Any] = Depends(get_session)):
    """
    Handle password reset requests.
    
    GET: Redirect to React frontend
    POST: Process password reset steps (email, totp, password)
    """
    # GET requests are handled by React frontend - redirect there
    if request.method == "GET":
        return RedirectResponse(url="/reset-password", status_code=302)

    # Handle JSON requests from React frontend
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        data = await request.json()
        step = data.get("step")
        email = data.get("email")
    else:
        # Fall back to form data for compatibility
        form = await request.form()
        step = form.get("step")
        email = form.get("email")
        data = dict(form)

    # Debug logging for CSRF issues
    logger.debug(f"Password reset step: {step}, Session keys: {list(session.keys())}")

    if step == "email":
        user = find_user_by_email(email)

        # Always show the same response to prevent user enumeration
        if user:
            session["reset_email"] = email

        # Return success regardless of whether email exists (prevents enumeration)
        return JSONResponse(content={"status": "success", "message": "Email verified"})

    elif step == "select_totp":
        session["reset_method"] = "totp"
        return JSONResponse(content={"status": "success", "method": "totp"})

    elif step == "select_email":
        user = find_user_by_email(email)
        session["reset_method"] = "email"

        # Check if SMTP is configured
        smtp_settings = get_smtp_settings()
        if not smtp_settings or not smtp_settings.get("smtp_server"):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Email reset is not available. Please use TOTP authentication.",
                }
            )

        if user:
            try:
                # Generate a secure token for the email reset
                token = secrets.token_urlsafe(32)
                session["reset_token"] = token
                session["reset_email"] = email

                # Create reset link - construct URL manually for FastAPI
                host_server = os.getenv("HOST_SERVER", "http://127.0.0.1:5000")
                reset_link = f"{host_server}/auth/reset-password-email/{token}"
                send_password_reset_email(email, reset_link, user.username)
                logger.info(f"Password reset email sent to {email}")

            except Exception as e:
                logger.error(f"Failed to send password reset email to {email}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "message": "Failed to send reset email. Please try TOTP authentication instead.",
                    }
                )

        # Return success regardless of whether email exists (prevents enumeration)
        return JSONResponse(content={"status": "success", "message": "Reset email sent if account exists"})

    elif step == "totp":
        totp_code = data.get("totp_code")
        user = find_user_by_email(email)

        if user and user.verify_totp(totp_code):
            # Generate a secure token for the password reset
            token = secrets.token_urlsafe(32)
            session["reset_token"] = token
            session["reset_email"] = email

            return JSONResponse(content={"status": "success", "message": "TOTP verified", "token": token})
        else:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid TOTP code. Please try again."}
            )

    elif step == "password":
        token = data.get("token")
        password = data.get("password")

        # Verify token from session (handles both TOTP and email reset tokens)
        valid_token = token == session.get("reset_token") or token == session.get("email_reset_token")
        if not valid_token or email != session.get("reset_email"):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid or expired reset token."}
            )

        # Validate password strength
        from utils.auth_utils import validate_password_strength

        is_valid, error_message = validate_password_strength(password)
        if not is_valid:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": error_message}
            )

        user = find_user_by_email(email)
        if user:
            user.set_password(password)
            db_session.commit()

            # Clear reset session data for security
            session.pop("reset_token", None)
            session.pop("reset_email", None)
            session.pop("reset_method", None)
            session.pop("email_reset_token", None)

            return JSONResponse(content={
                "status": "success",
                "message": "Your password has been reset successfully."
            })
        else:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Error resetting password."}
            )

    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": "Invalid step"}
    )


@auth_router.get("/reset-password-email/{token}")
async def reset_password_email(token: str, request: Request, session: Dict[str, Any] = Depends(get_session)):
    """
    Handle password reset via email link - validates token and redirects to React.
    """
    try:
        # Validate the token format
        if not token or len(token) != 43:  # URL-safe base64 tokens are 43 chars for 32 bytes
            return RedirectResponse(url="/reset-password?error=invalid_link", status_code=302)

        # Check if this token was issued (stored in session during email send)
        if token != session.get("reset_token"):
            return RedirectResponse(url="/reset-password?error=expired_link", status_code=302)

        # Get the email associated with this reset token
        reset_email = session.get("reset_email")
        if not reset_email:
            return RedirectResponse(url="/reset-password?error=session_expired", status_code=302)

        # Set up session for password reset (email verification counts as verified)
        session["email_reset_token"] = token

        # Redirect to React password reset page with token and email in URL
        # React will read these and show the password form
        return RedirectResponse(
            url=f"/reset-password?token={token}&email={reset_email}&verified=true",
            status_code=302
        )

    except Exception as e:
        logger.error(f"Error processing email reset link: {e}")
        return RedirectResponse(url="/reset-password?error=processing_error", status_code=302)



@auth_router.api_route("/change", methods=["GET", "POST"])
async def change_password(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """
    Handle password change requests.
    
    GET: Redirect to React profile page
    POST: Process password change
    """
    if "user" not in session:
        # If the user is not logged in, redirect to login page
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Not authenticated"}
            )
        return RedirectResponse(url="/login", status_code=302)

    # GET requests redirect to React profile page
    if request.method == "GET":
        return RedirectResponse(url="/profile", status_code=302)

    # Handle POST requests - change password
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        data = await request.json()
        old_password = data.get("old_password") or data.get("current_password")
        new_password = data.get("new_password")
        confirm_password = data.get("confirm_password", new_password)
    else:
        form = await request.form()
        old_password = form.get("old_password") or form.get("current_password")
        new_password = form.get("new_password")
        confirm_password = form.get("confirm_password", new_password)

    username = session["user"]
    user = User.query.filter_by(username=username).first()

    if user and user.check_password(old_password):
        if new_password == confirm_password:
            # Validate password strength
            from utils.auth_utils import validate_password_strength

            is_valid, error_message = validate_password_strength(new_password)
            if not is_valid:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": error_message}
                )

            user.set_password(new_password)
            db_session.commit()
            return JSONResponse(content={
                "status": "success",
                "message": "Your password has been changed successfully."
            })
        else:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "New password and confirm password do not match."}
            )
    else:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Current password is incorrect."}
        )


@auth_router.post("/smtp-config")
async def configure_smtp(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Configure SMTP settings."""
    if "user" not in session:
        # For AJAX requests, return JSON
        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in request.headers.get("content-type", "")
        )
        if is_ajax:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Not authenticated"}
            )
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        form = await request.form()
        smtp_server = form.get("smtp_server")
        smtp_port = int(form.get("smtp_port", 587))
        smtp_username = form.get("smtp_username")
        smtp_password = form.get("smtp_password")
        smtp_use_tls = form.get("smtp_use_tls") == "on"
        smtp_from_email = form.get("smtp_from_email")
        smtp_helo_hostname = form.get("smtp_helo_hostname")

        # Only update password if provided
        if smtp_password and smtp_password.strip():
            set_smtp_settings(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                smtp_use_tls=smtp_use_tls,
                smtp_from_email=smtp_from_email,
                smtp_helo_hostname=smtp_helo_hostname,
            )
        else:
            # Update without password change
            set_smtp_settings(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                smtp_username=smtp_username,
                smtp_use_tls=smtp_use_tls,
                smtp_from_email=smtp_from_email,
                smtp_helo_hostname=smtp_helo_hostname,
            )

        logger.info(f"SMTP settings updated by user: {session['user']}")

        # For AJAX requests, return JSON
        content_type = request.headers.get("content-type", "")
        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in content_type
            or "multipart/form-data" in content_type
        )
        if is_ajax:
            return JSONResponse(content={"status": "success", "message": "SMTP settings updated successfully"})

        return RedirectResponse(url="/auth/change?tab=smtp", status_code=302)

    except Exception as e:
        logger.error(f"Error updating SMTP settings: {str(e)}")
        # For AJAX requests, return JSON
        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in request.headers.get("content-type", "")
        )
        if is_ajax:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": f"Error updating SMTP settings: {str(e)}"}
            )

        return RedirectResponse(url="/auth/change?tab=smtp", status_code=302)


@auth_router.post("/test-smtp")
async def test_smtp(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Test SMTP configuration by sending a test email."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "You must be logged in to test SMTP settings."}
        )

    try:
        form = await request.form()
        test_email = form.get("test_email")
        if not test_email:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Please provide a test email address."}
            )

        # Validate email format
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, test_email):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Please provide a valid email address."}
            )

        # Send test email
        result = send_test_email(test_email, sender_name=session["user"])

        if result["success"]:
            logger.info(f"Test email sent successfully by user: {session['user']} to {test_email}")
            return JSONResponse(content={"success": True, "message": result["message"]})
        else:
            logger.warning(f"Test email failed for user: {session['user']} - {result['message']}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": result["message"]}
            )

    except Exception as e:
        error_msg = f"Error sending test email: {str(e)}"
        logger.error(f"Test email error for user {session['user']}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": error_msg}
        )


@auth_router.post("/debug-smtp")
async def debug_smtp(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Debug SMTP connection."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "You must be logged in to debug SMTP settings."}
        )

    try:
        logger.info(f"SMTP debug requested by user: {session['user']}")
        result = debug_smtp_connection()

        return JSONResponse(content={
            "success": result["success"],
            "message": result["message"],
            "details": result["details"],
        })

    except Exception as e:
        error_msg = f"Error debugging SMTP: {str(e)}"
        logger.error(f"SMTP debug error for user {session['user']}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": error_msg, "details": [f"Unexpected error: {e}"]}
        )



@auth_router.get("/session-status")
async def get_session_status(request: Request, session: Dict[str, Any] = Depends(get_session)):
    """Return current session status for React SPA."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Not authenticated", "authenticated": False}
        )

    # If session claims to be logged in with broker, validate the auth token exists
    if session.get("logged_in") and session.get("broker"):
        from database.auth_db import get_api_key_for_tradingview, get_auth_token

        auth_token = get_auth_token(session.get("user"))
        if auth_token is None:
            logger.warning(
                f"Session status: stale session detected for user {session.get('user')} - no auth token"
            )
            # Clear the stale session
            session.clear()
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Session expired", "authenticated": False}
            )

        # Get API key for the user
        api_key = get_api_key_for_tradingview(session.get("user"))

        return JSONResponse(content={
            "status": "success",
            "authenticated": True,
            "logged_in": session.get("logged_in", False),
            "user": session.get("user"),
            "broker": session.get("broker"),
            "api_key": api_key,
        })

    return JSONResponse(content={
        "status": "success",
        "authenticated": True,
        "logged_in": session.get("logged_in", False),
        "user": session.get("user"),
        "broker": session.get("broker"),
    })


@auth_router.get("/app-info")
async def get_app_info():
    """Return app information including version for React SPA."""
    from utils.version import get_version

    return JSONResponse(content={
        "status": "success",
        "version": get_version(),
        "name": "RealAlgo"
    })


@auth_router.get("/analyzer-mode")
async def get_analyzer_mode_status(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Return current analyzer mode status for React SPA."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Not authenticated"}
        )

    try:
        from database.settings_db import get_analyze_mode

        current_mode = get_analyze_mode()

        return JSONResponse(content={
            "status": "success",
            "data": {
                "mode": "analyze" if current_mode else "live",
                "analyze_mode": current_mode,
            },
        })
    except Exception as e:
        logger.error(f"Error getting analyzer mode: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@auth_router.post("/analyzer-toggle")
async def toggle_analyzer_mode_session(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Toggle analyzer mode for React SPA using session authentication."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Not authenticated"}
        )

    if not session.get("logged_in"):
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Broker not connected"}
        )

    try:
        from database.settings_db import get_analyze_mode, set_analyze_mode

        # Get current mode and toggle it
        current_mode = get_analyze_mode()
        new_mode = not current_mode

        # Set the new mode
        set_analyze_mode(new_mode)

        # Start/stop execution engine and squareoff scheduler based on mode
        from sandbox.execution_thread import start_execution_engine, stop_execution_engine
        from sandbox.squareoff_thread import start_squareoff_scheduler, stop_squareoff_scheduler

        if new_mode:
            # Analyzer mode ON - start both threads
            start_execution_engine()
            start_squareoff_scheduler()

            # Run catch-up settlement for any missed settlements while app was stopped
            from sandbox.position_manager import catchup_missed_settlements

            try:
                catchup_missed_settlements()
                logger.info("Catch-up settlement check completed")
            except Exception as e:
                logger.error(f"Error in catch-up settlement: {e}")

            logger.info("Analyzer mode enabled - Execution engine and square-off scheduler started")
        else:
            # Analyzer mode OFF - stop both threads
            stop_execution_engine()
            stop_squareoff_scheduler()
            logger.info(
                "Analyzer mode disabled - Execution engine and square-off scheduler stopped"
            )

        return JSONResponse(content={
            "status": "success",
            "data": {
                "mode": "analyze" if new_mode else "live",
                "analyze_mode": new_mode,
                "message": f"Switched to {'Analyze' if new_mode else 'Live'} mode",
            },
        })

    except Exception as e:
        logger.error(f"Error toggling analyzer mode: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@auth_router.get("/dashboard-data")
async def get_dashboard_data(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Return dashboard funds data using session authentication for React SPA."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Not authenticated"}
        )

    if not session.get("logged_in"):
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Broker not connected"}
        )

    login_username = session["user"]
    broker = session.get("broker")

    if not broker:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Broker not set in session"}
        )

    try:
        from database.auth_db import get_api_key_for_tradingview, get_auth_token
        from database.settings_db import get_analyze_mode
        from services.funds_service import get_funds

        AUTH_TOKEN = get_auth_token(login_username)

        if AUTH_TOKEN is None:
            logger.warning(f"No auth token found for user {login_username}")
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Session expired"}
            )

        # Check if in analyze mode
        if get_analyze_mode():
            api_key = get_api_key_for_tradingview(login_username)
            if api_key:
                success, response, status_code = get_funds(api_key=api_key)
            else:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": "API key required for analyze mode"}
                )
        else:
            success, response, status_code = get_funds(auth_token=AUTH_TOKEN, broker=broker)

        if not success:
            logger.error(f"Failed to get funds data: {response.get('message', 'Unknown error')}")
            return JSONResponse(
                status_code=status_code,
                content={"status": "error", "message": response.get("message", "Failed to get funds")}
            )

        margin_data = response.get("data", {})

        if not margin_data:
            logger.error(f"Failed to get margin data for user {login_username}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Failed to get margin data"}
            )

        return JSONResponse(content={"status": "success", "data": margin_data})

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error"}
        )



@auth_router.api_route("/logout", methods=["GET", "POST"])
async def logout(request: Request, session: Dict[str, Any] = Depends(get_session)):
    """
    Handle logout requests.
    
    GET: Redirect to login page
    POST: Return JSON response (for AJAX)
    """
    if session.get("logged_in"):
        username = session.get("user", "unknown")

        # Clear cache entries before database update to prevent stale data access
        cache_key_auth = f"auth-{username}"
        cache_key_feed = f"feed-{username}"
        if cache_key_auth in auth_cache:
            del auth_cache[cache_key_auth]
            logger.info(f"Cleared auth cache for user: {username}")
        if cache_key_feed in feed_token_cache:
            del feed_token_cache[cache_key_feed]
            logger.info(f"Cleared feed token cache for user: {username}")

        # Clear symbol cache on logout
        try:
            from database.master_contract_cache_hook import clear_cache_on_logout

            clear_cache_on_logout()
            logger.info("Cleared symbol cache on logout")
        except Exception as cache_error:
            logger.error(f"Error clearing symbol cache on logout: {cache_error}")

        # writing to database
        inserted_id = upsert_auth(username, "", "", revoke=True)
        if inserted_id is not None:
            logger.info(f"Database Upserted record with ID: {inserted_id}")
            logger.info(f"Auth Revoked in the Database for user: {username}")
        else:
            logger.error(f"Failed to upsert auth token for user: {username}")

        # Clear entire session to ensure complete logout
        session.clear()
        logger.info(f"Session cleared for user: {username}")

    # For POST requests (AJAX from React), return JSON
    if request.method == "POST":
        return JSONResponse(content={"status": "success", "message": "Logged out successfully"})

    # For GET requests (traditional), redirect to login page
    return RedirectResponse(url="/auth/login", status_code=302)


@auth_router.get("/profile-data")
async def get_profile_data(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Return profile data for React SPA."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Not authenticated"}
        )

    username = session["user"]

    try:
        # Get SMTP settings
        smtp_settings = get_smtp_settings()

        # Mask SMTP password - just indicate if it's set
        if smtp_settings and smtp_settings.get("smtp_password"):
            smtp_settings = dict(smtp_settings)
            smtp_settings["smtp_password"] = True
        elif smtp_settings:
            smtp_settings = dict(smtp_settings)
            smtp_settings["smtp_password"] = False

        # Generate TOTP QR code
        user = User.query.filter_by(username=username).first()
        qr_code = None
        totp_secret = None

        if user:
            try:
                import base64
                import io

                import qrcode

                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(user.get_totp_uri())
                qr.make(fit=True)

                img_buffer = io.BytesIO()
                qr.make_image(fill_color="black", back_color="white").save(img_buffer, format="PNG")
                qr_code = base64.b64encode(img_buffer.getvalue()).decode()
                totp_secret = user.totp_secret
            except Exception as e:
                logger.error(f"Error generating TOTP QR code: {e}")

        return JSONResponse(content={
            "status": "success",
            "data": {
                "username": username,
                "smtp_settings": smtp_settings,
                "qr_code": qr_code,
                "totp_secret": totp_secret,
            },
        })

    except Exception as e:
        logger.error(f"Error getting profile data: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to get profile data"}
        )


@auth_router.post("/change-password")
async def change_password_api(
    request: Request,
    session: Dict[str, Any] = Depends(check_session_validity)
):
    """Change password API endpoint for React SPA."""
    if "user" not in session:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Not authenticated"}
        )

    username = session["user"]
    
    form = await request.form()
    old_password = form.get("old_password")
    new_password = form.get("new_password")
    confirm_password = form.get("confirm_password")

    if not all([old_password, new_password, confirm_password]):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "All fields are required"}
        )

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(old_password):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Current password is incorrect"}
        )

    if new_password != confirm_password:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "New passwords do not match"}
        )

    # Validate password strength
    from utils.auth_utils import validate_password_strength

    is_valid, error_message = validate_password_strength(new_password)
    if not is_valid:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": error_message}
        )

    try:
        user.set_password(new_password)
        db_session.commit()
        logger.info(f"Password changed successfully for user: {username}")
        return JSONResponse(content={"status": "success", "message": "Password changed successfully"})
    except Exception as e:
        logger.error(f"Error changing password: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to change password"}
        )
