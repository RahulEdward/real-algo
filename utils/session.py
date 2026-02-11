"""
Session utilities for RealAlgo.

This module provides session-related utilities that work with
Starlette's session middleware (used by FastAPI).

For FastAPI route dependencies, use dependencies_fastapi.py instead.
This module is kept for backward compatibility with code that imports
session utilities directly.
"""

import os
from datetime import datetime, timedelta

import pytz

from utils.logging import get_logger

logger = get_logger(__name__)


def get_session_expiry_time():
    """Get session expiry time set to 3 AM IST next day"""
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


def is_session_valid(session: dict = None) -> bool:
    """
    Check if a session is valid.

    Args:
        session: Session dictionary. Required for FastAPI usage.

    Returns:
        True if session is valid, False otherwise.
    """
    if session is None:
        logger.debug("Session invalid: no session provided")
        return False

    if not session.get("logged_in"):
        logger.debug("Session invalid: 'logged_in' flag not set")
        return False

    if "login_time" not in session:
        logger.debug("Session invalid: 'login_time' not in session")
        return False

    now_utc = datetime.now(pytz.timezone("UTC"))
    now_ist = now_utc.astimezone(pytz.timezone("Asia/Kolkata"))

    login_time = datetime.fromisoformat(session["login_time"])

    expiry_time = os.getenv("SESSION_EXPIRY_TIME", "03:00")
    hour, minute = map(int, expiry_time.split(":"))

    daily_expiry = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if now_ist > daily_expiry and login_time < daily_expiry:
        logger.info(f"Session expired at {daily_expiry} IST")
        return False

    logger.debug(
        f"Session valid. Current time: {now_ist}, Login time: {login_time}, Daily expiry: {daily_expiry}"
    )
    return True


def set_session_login_time(session: dict):
    """Set the session login time in IST"""
    now_utc = datetime.now(pytz.timezone("UTC"))
    now_ist = now_utc.astimezone(pytz.timezone("Asia/Kolkata"))
    session["login_time"] = now_ist.isoformat()
    logger.info(f"Session login time set to: {now_ist}")


def revoke_user_tokens(session: dict, revoke_db_tokens=True):
    """
    Revoke auth tokens for the current user when session expires.

    Args:
        session: Session dictionary containing user info.
        revoke_db_tokens: If True, revokes the token in the database.
    """
    if "user" in session:
        username = session.get("user")
        try:
            from database.auth_db import auth_cache, feed_token_cache, upsert_auth

            cache_key_auth = f"auth-{username}"
            cache_key_feed = f"feed-{username}"
            if cache_key_auth in auth_cache:
                del auth_cache[cache_key_auth]
            if cache_key_feed in feed_token_cache:
                del feed_token_cache[cache_key_feed]

            try:
                from database.master_contract_cache_hook import clear_cache_on_logout
                clear_cache_on_logout()
            except Exception as cache_error:
                logger.error(f"Error clearing symbol cache: {cache_error}")

            try:
                from database.settings_db import clear_settings_cache
                clear_settings_cache()
            except Exception as cache_error:
                logger.error(f"Error clearing settings cache: {cache_error}")

            try:
                from database.strategy_db import clear_strategy_cache
                clear_strategy_cache()
            except Exception as cache_error:
                logger.error(f"Error clearing strategy cache: {cache_error}")

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
