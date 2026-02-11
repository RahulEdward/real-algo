# utils/auth_utils_fastapi.py
"""
FastAPI-compatible authentication utilities.
These replace the Flask-specific functions in auth_utils.py.
"""

from datetime import datetime
from threading import Thread

import pytz
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from database.auth_db import upsert_auth
from database.master_contract_status_db import init_broker_status, update_status
from utils.logging import get_logger

logger = get_logger(__name__)


def set_session_login_time_fastapi(session: dict):
    """Set the session login time in IST for FastAPI sessions."""
    now_utc = datetime.now(pytz.timezone("UTC"))
    now_ist = now_utc.astimezone(pytz.timezone("Asia/Kolkata"))
    session["login_time"] = now_ist.isoformat()
    logger.info(f"Session login time set to: {now_ist}")


def is_ajax_request(request: Request) -> bool:
    """Check if the current request is an AJAX/fetch request from React."""
    # Check for common AJAX indicators
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    # Check if request accepts JSON (React fetch typically sends this)
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return True
    # Check content type for form submissions from React
    content_type = request.headers.get("Content-Type", "")
    if request.method == "POST" and "multipart/form-data" in content_type:
        return True
    return False


def async_master_contract_download(broker: str):
    """
    Asynchronously download the master contract.
    This runs in a background thread after successful broker authentication.
    """
    import importlib
    
    logger.info(f"async_master_contract_download started for broker: {broker}")
    
    # Update status to downloading
    update_status(broker, "downloading", "Master contract download in progress")

    # Dynamically construct the module path based on the broker
    module_path = f"broker.{broker}.database.master_contract_db"

    # Dynamically import the module
    try:
        master_contract_module = importlib.import_module(module_path)
    except ImportError as error:
        logger.error(f"Error importing {module_path}: {error}")
        update_status(broker, "error", f"Failed to import master contract module: {str(error)}")
        return {"status": "error", "message": "Failed to import master contract module"}

    # Use the dynamically imported module's master_contract_download function
    try:
        master_contract_status = master_contract_module.master_contract_download()

        # Try to get the symbol count from the database
        try:
            from database.token_db import get_symbol_count
            total_symbols = get_symbol_count()
        except:
            total_symbols = None

        update_status(
            broker, "success", "Master contract download completed successfully", total_symbols
        )
        logger.info(f"Master contract download completed for {broker}")

        # Load symbols into memory cache after successful download
        try:
            from database.master_contract_cache_hook import hook_into_master_contract_download
            logger.info(f"Loading symbols into memory cache for broker: {broker}")
            hook_into_master_contract_download(broker)
        except Exception as cache_error:
            logger.error(f"Failed to load symbols into cache: {cache_error}")

        # Run catch-up tasks for sandbox mode (T+1 settlement, daily PnL reset)
        try:
            from sandbox.catch_up_processor import run_catch_up_tasks
            run_catch_up_tasks()
        except Exception as catch_up_error:
            logger.error(f"Failed to run catch-up tasks: {catch_up_error}")

    except Exception as e:
        logger.error(f"Error during master contract download for {broker}: {str(e)}")
        update_status(broker, "error", f"Master contract download error: {str(e)}")
        return {"status": "error", "message": str(e)}

    logger.info("Master Contract Database Processing Completed")
    return master_contract_status


def handle_auth_success_fastapi(
    request: Request,
    auth_token: str,
    user_session_key: str,
    broker: str,
    feed_token: str = None,
    user_id: str = None,
):
    """
    Handles common tasks after successful authentication for FastAPI.
    - Sets session parameters
    - Stores auth token in the database
    - Initiates asynchronous master contract download
    Returns JSON for AJAX requests, redirect for OAuth callbacks.
    """
    logger.info(f"handle_auth_success_fastapi called for user {user_session_key} with broker {broker}")
    session = request.session
    
    # Store auth token in database
    result = upsert_auth(user_session_key, auth_token, broker, feed_token, user_id)
    
    if result:
        # Update session
        session["logged_in"] = True
        session["broker"] = broker
        session["user_session_key"] = user_session_key
        session["AUTH_TOKEN"] = auth_token
        
        if feed_token:
            session["FEED_TOKEN"] = feed_token
        if user_id:
            session["USER_ID"] = user_id
            
        # Set session login time for expiry tracking
        set_session_login_time_fastapi(session)
        
        # Initialize broker status and start master contract download
        init_broker_status(broker)
        
        # Start master contract download in background thread
        # Populate thread-local session for broker modules that need session data
        from utils.session_compat import populate_session_for_thread
        session_data = dict(session)
        
        def _download_with_session(broker_name, sess_data):
            populate_session_for_thread(sess_data)
            async_master_contract_download(broker_name)
        
        thread = Thread(target=_download_with_session, args=(broker, session_data))
        thread.start()
        logger.info(f"Started master contract download thread for broker: {broker}")
        
        logger.info(f"Authentication successful for user {user_session_key} with broker {broker}")
        
        if is_ajax_request(request):
            return JSONResponse(content={
                "status": "success",
                "message": "Authentication successful",
                "redirect": "/dashboard"
            })
        else:
            return RedirectResponse(url="/dashboard", status_code=302)
    else:
        logger.error(f"Failed to upsert auth token for user {user_session_key}")
        if is_ajax_request(request):
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Failed to store authentication token. Please try again.",
                }
            )
        else:
            return RedirectResponse(url="/broker", status_code=302)


def handle_auth_failure_fastapi(
    request: Request,
    error_message: str,
    forward_url: str = "broker.html"
):
    """
    Handles common tasks after failed authentication for FastAPI.
    Returns JSON for AJAX requests, redirect for OAuth callbacks.
    """
    logger.error(f"Authentication error: {error_message}")
    
    if is_ajax_request(request):
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": error_message}
        )
    else:
        # For OAuth callbacks, redirect to broker selection with error
        return RedirectResponse(url="/broker", status_code=302)
