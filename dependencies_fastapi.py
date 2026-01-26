#!/usr/bin/env python3
"""
FastAPI Dependencies for RealAlgo

This module provides FastAPI dependencies for:
- Session management (get_session, check_session_validity)
- Authentication (verify_api_key)

These dependencies replace Flask decorators and session access patterns.

Requirements: 4.5, 5.1, 7.3
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pytz
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Session Dependencies
# ============================================================


async def get_session(request: Request) -> Dict[str, Any]:
    """
    Get the session dictionary from the request.
    
    This is the FastAPI equivalent of accessing Flask's session object.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Session dictionary
    """
    return request.session


def get_session_expiry_time() -> timedelta:
    """
    Get session expiry time set to configured time (default 3 AM IST) next day.
    
    Returns:
        timedelta: Remaining time until session expiry
    """
    now_utc = datetime.now(pytz.timezone("UTC"))
    now_ist = now_utc.astimezone(pytz.timezone("Asia/Kolkata"))

    # Get configured expiry time or default to 3 AM
    expiry_time = os.getenv("SESSION_EXPIRY_TIME", "03:00")
    hour, minute = map(int, expiry_time.split(":"))

    target_time_ist = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If current time is past target time, set expiry to next day
    if now_ist > target_time_ist:
        target_time_ist += timedelta(days=1)

    remaining_time = target_time_ist - now_ist
    logger.debug(f"Session expiry time set to: {target_time_ist}")
    return remaining_time


def set_session_login_time(session: Dict[str, Any]) -> None:
    """
    Set the session login time in IST.
    
    Args:
        session: Session dictionary to update
    """
    now_utc = datetime.now(pytz.timezone("UTC"))
    now_ist = now_utc.astimezone(pytz.timezone("Asia/Kolkata"))
    session["login_time"] = now_ist.isoformat()
    logger.info(f"Session login time set to: {now_ist}")


def is_session_valid(session: Dict[str, Any]) -> bool:
    """
    Check if the current session is valid.
    
    Args:
        session: Session dictionary to check
        
    Returns:
        True if session is valid, False otherwise
    """
    if not session.get("logged_in"):
        logger.debug("Session invalid: 'logged_in' flag not set")
        return False

    # If no login time is set, consider session invalid
    if "login_time" not in session:
        logger.debug("Session invalid: 'login_time' not in session")
        return False

    now_utc = datetime.now(pytz.timezone("UTC"))
    now_ist = now_utc.astimezone(pytz.timezone("Asia/Kolkata"))

    # Parse login time
    login_time = datetime.fromisoformat(session["login_time"])

    # Get configured expiry time
    expiry_time = os.getenv("SESSION_EXPIRY_TIME", "03:00")
    hour, minute = map(int, expiry_time.split(":"))

    # Get today's expiry time
    daily_expiry = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If current time is past expiry time and login was before expiry time
    if now_ist > daily_expiry and login_time < daily_expiry:
        logger.info(f"Session expired at {daily_expiry} IST")
        return False

    logger.debug(
        f"Session valid. Current time: {now_ist}, Login time: {login_time}, Daily expiry: {daily_expiry}"
    )
    return True


def revoke_user_tokens(session: Dict[str, Any], revoke_db_tokens: bool = True) -> None:
    """
    Revoke auth tokens for the current user when session expires.
    
    Args:
        session: Session dictionary containing user info
        revoke_db_tokens: If True, revokes the token in the database.
                         If False, only clears local caches.
    """
    if "user" in session:
        username = session.get("user")
        try:
            from database.auth_db import auth_cache, feed_token_cache, upsert_auth

            # Clear cache entries first
            cache_key_auth = f"auth-{username}"
            cache_key_feed = f"feed-{username}"
            if cache_key_auth in auth_cache:
                del auth_cache[cache_key_auth]
            if cache_key_feed in feed_token_cache:
                del feed_token_cache[cache_key_feed]

            # Clear symbol cache
            try:
                from database.master_contract_cache_hook import clear_cache_on_logout
                clear_cache_on_logout()
            except Exception as cache_error:
                logger.error(f"Error clearing symbol cache: {cache_error}")

            # Clear settings cache
            try:
                from database.settings_db import clear_settings_cache
                clear_settings_cache()
            except Exception as cache_error:
                logger.error(f"Error clearing settings cache: {cache_error}")

            # Clear strategy cache
            try:
                from database.strategy_db import clear_strategy_cache
                clear_strategy_cache()
            except Exception as cache_error:
                logger.error(f"Error clearing strategy cache: {cache_error}")

            # Clear telegram cache
            try:
                from database.telegram_db import clear_telegram_cache
                clear_telegram_cache()
            except Exception as cache_error:
                logger.error(f"Error clearing telegram cache: {cache_error}")

            if revoke_db_tokens:
                inserted_id = upsert_auth(username, "", "", revoke=True)
                if inserted_id is not None:
                    logger.info(f"Auto-expiry: Revoked auth tokens for user: {username}")
                else:
                    logger.error(f"Auto-expiry: Failed to revoke auth tokens for user: {username}")
            else:
                logger.info(f"Auto-expiry: Skipped DB revocation for user: {username}")

        except Exception as e:
            logger.error(f"Error revoking tokens during auto-expiry for user {username}: {e}")


async def check_session_validity(
    request: Request,
    session: Dict[str, Any] = Depends(get_session)
) -> Dict[str, Any]:
    """
    FastAPI dependency to check session validity.
    
    This replaces the Flask @check_session_validity decorator.
    
    Args:
        request: FastAPI Request object
        session: Session dictionary from get_session dependency
        
    Returns:
        Session dictionary if valid
        
    Raises:
        HTTPException: 401 if session is invalid (for AJAX requests)
        RedirectResponse: Redirects to login for non-AJAX requests
    """
    if not is_session_valid(session):
        # Revoke tokens before clearing session
        revoke_user_tokens(session)
        session.clear()

        # Check if this is an AJAX/fetch request
        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.headers.get("Accept", "").startswith("application/json")
            or request.headers.get("Content-Type") == "application/json"
        )

        if is_ajax:
            logger.info("Invalid session detected - returning 401 for AJAX request")
            raise HTTPException(
                status_code=401,
                detail={
                    "status": "error",
                    "error": "session_expired",
                    "message": "Your session has expired. Please log in again.",
                }
            )

        logger.info("Invalid session detected - redirecting to login")
        # For non-AJAX requests, we need to return a redirect
        # This is handled by raising an HTTPException that the route can catch
        raise HTTPException(
            status_code=307,
            headers={"Location": "/auth/login"}
        )

    logger.debug("Session validated successfully")
    return session


async def optional_session_check(
    request: Request,
    session: Dict[str, Any] = Depends(get_session)
) -> Dict[str, Any]:
    """
    FastAPI dependency to invalidate session if invalid without raising exception.
    
    This replaces the Flask @invalidate_session_if_invalid decorator.
    
    Args:
        request: FastAPI Request object
        session: Session dictionary from get_session dependency
        
    Returns:
        Session dictionary (may be cleared if invalid)
    """
    if not is_session_valid(session):
        logger.info("Invalid session detected - clearing session")
        revoke_user_tokens(session)
        session.clear()
    return session


# Alias for backward compatibility with Flask naming convention
invalidate_session_if_invalid = optional_session_check


# ============================================================
# API Key Authentication Dependency
# ============================================================


class APIKeyAuth:
    """Container for API key authentication result"""
    def __init__(self, api_key: str, auth_token: str, broker: str):
        self.api_key = api_key
        self.auth_token = auth_token
        self.broker = broker


async def verify_api_key(request: Request) -> str:
    """
    FastAPI dependency to verify API key authentication.
    
    This is used for /api/v1/ endpoints that use API key auth instead of session.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        The validated API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    from database.auth_db import get_auth_token_broker

    # Get API key from request body or query params
    api_key = None
    
    # Try to get from JSON body
    if request.headers.get("Content-Type") == "application/json":
        try:
            body = await request.json()
            api_key = body.get("apikey")
        except Exception:
            pass
    
    # Try to get from form data
    if not api_key:
        try:
            form = await request.form()
            api_key = form.get("apikey")
        except Exception:
            pass
    
    # Try to get from query params
    if not api_key:
        api_key = request.query_params.get("apikey")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "API key is required"}
        )
    
    # Validate API key
    auth_token, broker = get_auth_token_broker(api_key)
    
    if auth_token is None:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Invalid API key"}
        )
    
    return api_key


async def verify_api_key_with_broker(request: Request) -> APIKeyAuth:
    """
    FastAPI dependency to verify API key and return auth details.
    
    This is used when the endpoint needs access to the broker and auth token.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        APIKeyAuth object with api_key, auth_token, and broker
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    from database.auth_db import get_auth_token_broker

    # Get API key from request body or query params
    api_key = None
    
    # Try to get from JSON body
    if request.headers.get("Content-Type") == "application/json":
        try:
            body = await request.json()
            api_key = body.get("apikey")
        except Exception:
            pass
    
    # Try to get from form data
    if not api_key:
        try:
            form = await request.form()
            api_key = form.get("apikey")
        except Exception:
            pass
    
    # Try to get from query params
    if not api_key:
        api_key = request.query_params.get("apikey")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "API key is required"}
        )
    
    # Validate API key
    auth_token, broker = get_auth_token_broker(api_key)
    
    if auth_token is None:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Invalid API key"}
        )
    
    return APIKeyAuth(api_key=api_key, auth_token=auth_token, broker=broker)


def validate_api_key_from_data(api_key: str) -> tuple:
    """
    Validate API key from request data (for use with Pydantic models).
    
    Args:
        api_key: The API key to validate
        
    Returns:
        Tuple of (auth_token, broker)
        
    Raises:
        HTTPException: 401 if API key is invalid
    """
    from database.auth_db import get_auth_token_broker
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "API key is required"}
        )
    
    auth_token, broker = get_auth_token_broker(api_key)
    
    if auth_token is None:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Invalid API key"}
        )
    
    return auth_token, broker


# ============================================================
# Utility Functions
# ============================================================


def get_current_user(session: Dict[str, Any]) -> Optional[str]:
    """
    Get the current logged-in username from session.
    
    Args:
        session: Session dictionary
        
    Returns:
        Username if logged in, None otherwise
    """
    return session.get("user") if session.get("logged_in") else None


def is_logged_in(session: Dict[str, Any]) -> bool:
    """
    Check if user is logged in.
    
    Args:
        session: Session dictionary
        
    Returns:
        True if logged in, False otherwise
    """
    return bool(session.get("logged_in"))
