# app_fastapi.py
"""
FastAPI Application Core for RealAlgo

This module provides the FastAPI application initialization with:
- Lifespan context manager for startup/shutdown
- Environment variable configuration
- Basic middleware setup (expanded in later tasks)
- Exception handlers for 400, 401, 403, 404, 429, 500

Requirements: 3.1, 3.2, 3.4, 3.5, 3.6
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from cors_fastapi import get_fastapi_cors_config, is_cors_enabled
from csp_fastapi import CSPMiddleware, is_csp_enabled
from csrf_fastapi import CSRFMiddleware, get_csrf_config
from extensions_fastapi import sio, socket_app
from limiter_fastapi import limiter
from security_middleware_fastapi import SecurityMiddleware
from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)


# Environment configuration
def get_app_config() -> Dict[str, Any]:
    """
    Get application configuration from environment variables.
    Mirrors Flask app configuration for consistency.
    """
    host_server = os.getenv("HOST_SERVER", "http://127.0.0.1:5000")
    use_https = host_server.startswith("https://")
    
    session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "session")
    csrf_cookie_name = os.getenv("CSRF_COOKIE_NAME", "csrf_token")
    
    # Add cookie prefix for HTTPS environments
    if use_https:
        session_cookie_name = f"__Secure-{session_cookie_name}"
        csrf_cookie_name = f"__Secure-{csrf_cookie_name}"
    
    return {
        "secret_key": os.getenv("APP_KEY"),
        "database_uri": os.getenv("DATABASE_URL"),
        "host_server": host_server,
        "use_https": use_https,
        "session_cookie_name": session_cookie_name,
        "session_cookie_httponly": True,
        "session_cookie_samesite": "lax",
        "session_cookie_secure": use_https,
        "csrf_enabled": os.getenv("CSRF_ENABLED", "TRUE").upper() == "TRUE",
        "csrf_cookie_name": csrf_cookie_name,
        "csrf_cookie_httponly": True,
        "csrf_cookie_samesite": "lax",
        "csrf_cookie_secure": use_https,
    }


# Store app configuration globally for access by other modules
app_config = get_app_config()


# Path to the pre-built React frontend
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


def is_react_frontend_available() -> bool:
    """Check if the React frontend build exists."""
    index_html = FRONTEND_DIST / "index.html"
    return FRONTEND_DIST.exists() and index_html.exists()


def serve_react_app():
    """
    Serve the React app's index.html.
    Used for 404 handling and SPA routing.
    """
    if not is_react_frontend_available():
        return HTMLResponse(
            content="""
        <html>
        <head><title>RealAlgo - Frontend Not Available</title></head>
        <body style="font-family: system-ui; padding: 40px; max-width: 600px; margin: 0 auto;">
            <h1>Frontend Not Built</h1>
            <p>The React frontend is not available. To build it:</p>
            <pre style="background: #f4f4f4; padding: 16px; border-radius: 8px;">
cd frontend
npm install
npm run build</pre>
            <p>Or use the pre-built version from the repository.</p>
        </body>
        </html>
        """,
            status_code=503,
        )

    index_path = FRONTEND_DIST / "index.html"
    return FileResponse(index_path, media_type="text/html")


async def initialize_databases() -> None:
    """
    Initialize all databases in parallel for faster startup.
    Mirrors Flask setup_environment() database initialization.
    """
    from database.action_center_db import init_db as ensure_action_center_tables_exists
    from database.analyzer_db import init_db as ensure_analyzer_tables_exists
    from database.apilog_db import init_db as ensure_api_log_tables_exists
    from database.auth_db import init_db as ensure_auth_tables_exists
    from database.chart_prefs_db import ensure_chart_prefs_tables_exists
    from database.chartink_db import init_db as ensure_chartink_tables_exists
    from database.flow_db import init_db as ensure_flow_tables_exists
    from database.historify_db import init_database as ensure_historify_tables_exists
    from database.latency_db import init_latency_db as ensure_latency_tables_exists
    from database.market_calendar_db import ensure_market_calendar_tables_exists
    from database.qty_freeze_db import ensure_qty_freeze_tables_exists
    from database.sandbox_db import init_db as ensure_sandbox_tables_exists
    from database.settings_db import init_db as ensure_settings_tables_exists
    from database.strategy_db import init_db as ensure_strategy_tables_exists
    from database.symbol import init_db as ensure_master_contract_tables_exists
    from database.traffic_db import init_logs_db as ensure_traffic_logs_exists
    from database.user_db import init_db as ensure_user_tables_exists

    db_init_functions = [
        ("Auth DB", ensure_auth_tables_exists),
        ("User DB", ensure_user_tables_exists),
        ("Master Contract DB", ensure_master_contract_tables_exists),
        ("API Log DB", ensure_api_log_tables_exists),
        ("Analyzer DB", ensure_analyzer_tables_exists),
        ("Settings DB", ensure_settings_tables_exists),
        ("Chartink DB", ensure_chartink_tables_exists),
        ("Traffic Logs DB", ensure_traffic_logs_exists),
        ("Latency DB", ensure_latency_tables_exists),
        ("Strategy DB", ensure_strategy_tables_exists),
        ("Sandbox DB", ensure_sandbox_tables_exists),
        ("Action Center DB", ensure_action_center_tables_exists),
        ("Chart Prefs DB", ensure_chart_prefs_tables_exists),
        ("Market Calendar DB", ensure_market_calendar_tables_exists),
        ("Qty Freeze DB", ensure_qty_freeze_tables_exists),
        ("Historify DB", ensure_historify_tables_exists),
        ("Flow DB", ensure_flow_tables_exists),
    ]

    db_init_start = time.time()
    
    # Run database initialization in thread pool (sync functions)
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(func): name for name, func in db_init_functions}
        
        for future in as_completed(futures):
            db_name = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Failed to initialize {db_name}: {e}")

    db_init_time = (time.time() - db_init_start) * 1000
    logger.debug(f"All databases initialized in parallel ({db_init_time:.0f}ms)")


def load_broker_plugins() -> Dict[str, Any]:
    """
    Load broker authentication plugins.
    Mirrors Flask load_broker_auth_functions().
    """
    import importlib
    
    auth_functions = {}
    broker_directory = "broker"
    broker_path = os.path.join(os.path.dirname(__file__), broker_directory)
    
    if not os.path.exists(broker_path):
        logger.warning(f"Broker directory not found: {broker_path}")
        return auth_functions
    
    # List all items in broker directory and filter out __pycache__ and non-directories
    broker_names = [
        d
        for d in os.listdir(broker_path)
        if os.path.isdir(os.path.join(broker_path, d)) and d != "__pycache__"
    ]

    for broker_name in broker_names:
        try:
            # Construct module name and import the module
            module_name = f"{broker_directory}.{broker_name}.api.auth_api"
            auth_module = importlib.import_module(module_name)
            # Retrieve the authenticate_broker function
            auth_function = getattr(auth_module, "authenticate_broker", None)
            if auth_function:
                auth_functions[f"{broker_name}_auth"] = auth_function
        except ImportError as e:
            logger.error(f"Failed to import broker plugin {broker_name}: {e}")
        except AttributeError as e:
            logger.error(f"Authentication function not found in broker plugin {broker_name}: {e}")

    return auth_functions


async def restore_caches() -> None:
    """
    Restore caches from database on startup.
    Enables restart without re-login.
    """
    try:
        from database.cache_restoration import restore_all_caches

        cache_result = restore_all_caches()

        if cache_result["success"]:
            symbol_count = cache_result["symbol_cache"].get("symbols_loaded", 0)
            auth_count = cache_result["auth_cache"].get("tokens_loaded", 0)
            if symbol_count > 0 or auth_count > 0:
                logger.debug(f"Cache restoration: {symbol_count} symbols, {auth_count} auth tokens")
    except Exception as e:
        logger.debug(f"Cache restoration skipped: {e}")


async def initialize_schedulers() -> None:
    """
    Initialize Flow and Historify schedulers.
    """
    # Initialize Flow scheduler
    try:
        from services.flow_scheduler_service import init_flow_scheduler
        init_flow_scheduler()
        logger.debug("Flow scheduler initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Flow scheduler: {e}")

    # Initialize Historify scheduler
    try:
        from services.historify_scheduler_service import init_historify_scheduler
        # Note: socketio will be passed when WebSocket migration is complete
        init_historify_scheduler(socketio=None)
        logger.debug("Historify scheduler initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Historify scheduler: {e}")


async def auto_start_services() -> None:
    """
    Auto-start execution engine and squareoff scheduler if in analyzer mode.
    """
    try:
        from database.settings_db import get_analyze_mode
        from sandbox.execution_thread import start_execution_engine
        from sandbox.squareoff_thread import start_squareoff_scheduler

        if get_analyze_mode():
            # Define service startup functions for parallel execution
            def start_engine():
                success, message = start_execution_engine()
                return ("execution_engine", success, message)

            def start_scheduler():
                success, message = start_squareoff_scheduler()
                return ("squareoff_scheduler", success, message)

            def run_catchup():
                from sandbox.position_manager import catchup_missed_settlements
                catchup_missed_settlements()
                return ("catchup_settlement", True, "Completed")

            # Start all services in parallel
            startup_start = time.time()
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(start_engine),
                    executor.submit(start_scheduler),
                    executor.submit(run_catchup),
                ]

                for future in as_completed(futures):
                    try:
                        service_name, success, message = future.result()
                        if service_name == "execution_engine":
                            if success:
                                logger.debug("Execution engine auto-started (Analyzer mode is ON)")
                            else:
                                logger.warning(f"Failed to auto-start execution engine: {message}")
                        elif service_name == "squareoff_scheduler":
                            if success:
                                logger.debug("Square-off scheduler auto-started (Analyzer mode is ON)")
                            else:
                                logger.warning(f"Failed to auto-start square-off scheduler: {message}")
                        elif service_name == "catchup_settlement":
                            logger.debug("Catch-up settlement check completed on startup")
                    except Exception as e:
                        logger.error(f"Error starting service: {e}")

            startup_time = (time.time() - startup_start) * 1000
            logger.debug(f"Services started in parallel ({startup_time:.0f}ms)")
    except Exception as e:
        logger.error(f"Error checking analyzer mode on startup: {e}")


async def setup_environment() -> Dict[str, Any]:
    """
    Setup the application environment on startup.
    Mirrors Flask setup_environment() function.
    
    Returns:
        Dict containing broker_auth_functions and other startup data
    """
    startup_data = {}
    
    # Load broker plugins
    startup_data["broker_auth_functions"] = load_broker_plugins()
    
    # Initialize all databases in parallel
    await initialize_databases()
    
    # Initialize schedulers
    await initialize_schedulers()
    
    # Restore caches from database
    await restore_caches()
    
    # Auto-start services if in analyzer mode
    await auto_start_services()
    
    # Start WebSocket proxy server
    try:
        from websocket_proxy.app_integration_fastapi import start_websocket_proxy_async
        await start_websocket_proxy_async()
        logger.debug("WebSocket proxy server started")
    except Exception as e:
        logger.error(f"Failed to start WebSocket proxy server: {e}")
    
    # Setup ngrok cleanup handlers
    try:
        from utils.ngrok_manager import setup_ngrok_handlers
        setup_ngrok_handlers()
    except Exception as e:
        logger.debug(f"Ngrok handlers setup skipped: {e}")
    
    return startup_data


async def cleanup_resources() -> None:
    """
    Cleanup resources on application shutdown.
    """
    logger.info("Shutting down RealAlgo API...")
    
    # Stop WebSocket proxy server
    try:
        from websocket_proxy.app_integration_fastapi import cleanup_websocket_proxy_async
        await cleanup_websocket_proxy_async()
        logger.debug("WebSocket proxy server stopped")
    except Exception as e:
        logger.debug(f"WebSocket proxy cleanup skipped: {e}")
    
    # Stop Telegram bot if running
    try:
        from services.telegram_bot_service import telegram_bot_service
        if telegram_bot_service.is_running():
            telegram_bot_service.stop_bot()
            logger.debug("Telegram bot stopped")
    except Exception as e:
        logger.debug(f"Telegram bot cleanup skipped: {e}")
    
    # Stop execution engine if running
    try:
        from sandbox.execution_thread import stop_execution_engine
        stop_execution_engine()
        logger.debug("Execution engine stopped")
    except Exception as e:
        logger.debug(f"Execution engine cleanup skipped: {e}")
    
    # Stop squareoff scheduler if running
    try:
        from sandbox.squareoff_thread import stop_squareoff_scheduler
        stop_squareoff_scheduler()
        logger.debug("Squareoff scheduler stopped")
    except Exception as e:
        logger.debug(f"Squareoff scheduler cleanup skipped: {e}")
    
    logger.info("RealAlgo API shutdown complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    
    On startup:
    - Initialize databases (parallel like Flask)
    - Load broker plugins
    - Restore caches
    - Initialize schedulers
    - Auto-start services
    
    On shutdown:
    - Cleanup resources
    """
    # Startup
    logger.info("Starting RealAlgo API...")
    
    try:
        startup_data = await setup_environment()
        # Store startup data in app state for access by routes
        app.state.broker_auth_functions = startup_data.get("broker_auth_functions", {})
        app.state.config = app_config
        logger.info("RealAlgo API startup complete")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise
    
    yield
    
    # Shutdown
    await cleanup_resources()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    # Load environment variables before anything else
    from utils.env_check import load_and_check_env_variables
    load_and_check_env_variables()
    
    app = FastAPI(
        title="RealAlgo API",
        version="1.0",
        description="Your Personal Algo Trading Platform",
        lifespan=lifespan,
        # Disable automatic docs in production if needed
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    
    # Store configuration in app state
    app.state.config = app_config
    
    # Basic middleware setup (will be expanded in later tasks)
    # IMPORTANT: Middleware registration order matters!
    # Middleware is added in REVERSE order of execution.
    # So the LAST middleware added runs FIRST.
    # 
    # Execution order will be:
    # 1. SecurityMiddleware (checks for banned IPs first)
    # 2. CSPMiddleware (adds security headers)
    # 3. CORSMiddleware (handles CORS preflight and headers)
    # 4. SessionMiddleware (runs first to set up session)
    # 5. CSRFMiddleware (runs after session is available)
    # 6. Route handlers
    
    # Task 3.9 - CSPMiddleware
    # Content Security Policy and other security headers
    # - Adds CSP header based on environment configuration
    # - Adds Referrer-Policy and Permissions-Policy headers
    # - Only added if CSP_ENABLED=TRUE (default)
    if is_csp_enabled():
        app.add_middleware(CSPMiddleware)
    
    # Task 3.8 - SecurityMiddleware
    # Security middleware to check for banned IPs
    # - Gets real client IP (handles proxies via CF-Connecting-IP, X-Real-IP, X-Forwarded-For, etc.)
    # - Checks if IP is banned using IPBan.is_ip_banned()
    # - Returns 403 Forbidden for banned IPs
    # - Logs blocked attempts
    # NOTE: Added FIRST so it runs LAST in middleware chain (after all other middleware)
    # This ensures security check happens before any other processing
    app.add_middleware(SecurityMiddleware)
    
    # Task 3.6 - CORSMiddleware
    # CORS configuration from environment variables, matching Flask-CORS behavior
    # - Only added if CORS_ENABLED=TRUE
    # - Reads origins, methods, headers, credentials, max_age from env vars
    # - Applied to all routes (Flask-CORS was configured for /api/* but FastAPI
    #   CORSMiddleware applies globally - routes outside /api/* typically don't
    #   receive cross-origin requests anyway)
    if is_cors_enabled():
        cors_config = get_fastapi_cors_config()
        if cors_config:
            app.add_middleware(CORSMiddleware, **cors_config)
    
    # Task 3.4 - CSRFMiddleware
    # CSRF protection for state-changing requests (POST, PUT, DELETE, PATCH)
    # - Exempt /api/v1/ paths (use API key authentication instead)
    # - Exempt safe methods (GET, HEAD, OPTIONS, TRACE)
    # - Validate token from X-CSRF-Token header or csrf_token form field
    # - Compare tokens using secrets.compare_digest (timing-attack safe)
    # NOTE: Added BEFORE SessionMiddleware so it runs AFTER session is available
    csrf_config = get_csrf_config()
    if csrf_config["enabled"]:
        app.add_middleware(
            CSRFMiddleware,
            secret_key=app_config["secret_key"],
            exempt_paths=csrf_config["exempt_paths"],
            enabled=True,
        )
    
    # Task 3.3 - SessionMiddleware
    # Configure with identical settings to Flask:
    # - HTTPONLY: True (default in Starlette SessionMiddleware)
    # - SAMESITE: "lax" (matches Flask SESSION_COOKIE_SAMESITE)
    # - SECURE: USE_HTTPS (matches Flask SESSION_COOKIE_SECURE)
    # - Cookie name: session_cookie_name with __Secure- prefix for HTTPS
    # - max_age: None (session expires when browser closes, like Flask default)
    # NOTE: Added AFTER CSRFMiddleware so it runs BEFORE (session must be available for CSRF)
    app.add_middleware(
        SessionMiddleware,
        secret_key=app_config["secret_key"],
        session_cookie=app_config["session_cookie_name"],
        same_site=app_config["session_cookie_samesite"],
        https_only=app_config["session_cookie_secure"],
        max_age=None,  # Session expires when browser closes (matches Flask behavior)
    )
    
    return app


# Create the FastAPI application instance
app = create_app()

# ============================================================
# Register Routers (Task 5.2+)
# ============================================================

# Register the limiter with the app state (required for slowapi)
app.state.limiter = limiter

# Import all routers from the routers package
from routers import (
    admin_router,
    analyzer_router,
    apikey_router,
    auth_router,
    brlogin_router,
    broker_credentials_router,
    chartink_router,
    core_router,
    dashboard_router,
    flow_router,
    gc_json_router,
    historify_router,
    latency_router,
    log_router,
    logging_router,
    master_contract_status_router,
    orders_router,
    platforms_router,
    playground_router,
    pnltracker_router,
    python_strategy_router,
    react_router,
    sandbox_router,
    search_router,
    security_router,
    settings_router,
    strategy_router,
    system_permissions_router,
    telegram_router,
    traffic_router,
    tv_json_router,
)

# Register all routers with the app
# Order matters for route matching - more specific routes should come first

# Auth and session management
app.include_router(auth_router)

# Dashboard and core functionality
app.include_router(dashboard_router)
app.include_router(core_router)

# Trading operations
app.include_router(orders_router)
app.include_router(search_router)

# API key management
app.include_router(apikey_router)

# Broker authentication
app.include_router(brlogin_router)
app.include_router(broker_credentials_router)

# Strategy management
app.include_router(strategy_router)
app.include_router(python_strategy_router)
app.include_router(chartink_router)

# Monitoring and analytics
app.include_router(analyzer_router)
app.include_router(latency_router)
app.include_router(traffic_router)
app.include_router(security_router)
app.include_router(pnltracker_router)

# Logging
app.include_router(log_router)
app.include_router(logging_router)

# Settings and admin
app.include_router(settings_router)
app.include_router(admin_router)
app.include_router(master_contract_status_router)
app.include_router(system_permissions_router)

# Sandbox and playground
app.include_router(sandbox_router)
app.include_router(playground_router)

# Telegram integration
app.include_router(telegram_router)

# External platform integrations
app.include_router(platforms_router)
app.include_router(tv_json_router)
app.include_router(gc_json_router)

# Flow automation
app.include_router(flow_router)

# Historical data
app.include_router(historify_router)

# Tools Hub (GEX, IV Chart, IV Smile, OI Profile, OI Tracker, Straddle, Vol Surface, Health)
from routers.tools import tools_router
app.include_router(tools_router)

# ============================================================
# REST API v1 Routers (Task 7.3+)
# These replace Flask-RESTX namespaces under /api/v1/
# ============================================================

from routers.api_v1 import (
    place_order_router,
    place_smart_order_router,
    modify_order_router,
    cancel_order_router,
    cancel_all_order_router,
    close_position_router,
    funds_router,
    orderbook_router,
    tradebook_router,
    positionbook_router,
    holdings_router,
    orderstatus_router,
    openposition_router,
    quotes_router,
    multiquotes_router,
    depth_router,
    history_router,
    intervals_router,
    ticker_router,
    symbol_router,
    search_router as api_search_router,
    expiry_router,
    instruments_router,
    option_chain_router,
    option_symbol_router,
    option_greeks_router,
    multi_option_greeks_router,
    options_order_router,
    options_multiorder_router,
    synthetic_future_router,
    basket_order_router,
    split_order_router,
    margin_router,
    api_analyzer_router,
    ping_router,
    telegram_bot_router,
    chart_api_router,
    market_holidays_router,
    market_timings_router,
    pnl_symbols_router,
)

# Order management endpoints
app.include_router(place_order_router)
app.include_router(place_smart_order_router)
app.include_router(modify_order_router)
app.include_router(cancel_order_router)
app.include_router(cancel_all_order_router)
app.include_router(close_position_router)

# Account endpoints
app.include_router(funds_router)
app.include_router(orderbook_router)
app.include_router(tradebook_router)
app.include_router(positionbook_router)
app.include_router(holdings_router)
app.include_router(orderstatus_router)
app.include_router(openposition_router)

# Market data endpoints
app.include_router(quotes_router)
app.include_router(multiquotes_router)
app.include_router(depth_router)
app.include_router(history_router)
app.include_router(intervals_router)
app.include_router(ticker_router)

# Symbol and search endpoints
app.include_router(symbol_router)
app.include_router(api_search_router)
app.include_router(expiry_router)
app.include_router(instruments_router)

# Options endpoints
app.include_router(option_chain_router)
app.include_router(option_symbol_router)
app.include_router(option_greeks_router)
app.include_router(multi_option_greeks_router)
app.include_router(options_order_router)
app.include_router(options_multiorder_router)
app.include_router(synthetic_future_router)

# Basket and split order endpoints
app.include_router(basket_order_router)
app.include_router(split_order_router)

# Utility endpoints
app.include_router(margin_router)
app.include_router(api_analyzer_router)
app.include_router(ping_router)
app.include_router(telegram_bot_router)
app.include_router(chart_api_router)
app.include_router(market_holidays_router)
app.include_router(market_timings_router)
app.include_router(pnl_symbols_router)

# React frontend routes (should be last to catch all unmatched routes)
app.include_router(react_router)


# ============================================================
# WebSocket / Socket.IO Mount (Task 9.2)
# Mount python-socketio ASGI app at /socket.io
# This replaces Flask-SocketIO integration
# Requirements: 6.1
# ============================================================

# Mount Socket.IO ASGI app
# Clients connect to ws://host:port/socket.io/
app.mount("/socket.io", socket_app)

logger.debug("Socket.IO ASGI app mounted at /socket.io")


# ============================================================
# Exception Handlers (Task 3.5)
# Match Flask error response formats exactly
# Requirements: 3.5, 3.6
# ============================================================


@app.exception_handler(400)
async def bad_request_handler(request: Request, exc: HTTPException):
    """
    Custom handler for 400 Bad Request errors.
    Handles CSRF errors and other 400 errors.
    Matches Flask csrf_error() handler behavior.
    """
    error_description = str(exc.detail) if hasattr(exc, "detail") else str(exc)
    
    logger.warning(f"Bad Request on {request.url.path}: {error_description}")
    
    # Check if it's a CSRF error
    if "CSRF" in error_description or "csrf" in error_description.lower():
        # For API requests, return JSON
        if request.headers.get("content-type") == "application/json" or str(request.url.path).startswith("/api"):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "CSRF validation failed",
                    "message": "Security token expired or invalid. Please refresh the page and try again.",
                },
            )
        else:
            # For web requests, redirect to login with flash message
            # Note: Flash messages require session support, handled by frontend
            referer = request.headers.get("referer")
            redirect_url = referer if referer else "/auth/login"
            return RedirectResponse(url=redirect_url, status_code=303)
    
    # For other 400 errors
    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": error_description},
    )


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc: HTTPException):
    """
    Custom handler for 401 Unauthorized errors.
    Matches Flask session expiry behavior.
    """
    error_detail = exc.detail if hasattr(exc, "detail") else "Unauthorized"
    
    logger.warning(f"Unauthorized access on {request.url.path}")
    
    return JSONResponse(
        status_code=401,
        content={
            "status": "error",
            "error": "session_expired",
            "message": str(error_detail),
        },
    )


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc: HTTPException):
    """
    Custom handler for 403 Forbidden errors.
    Used for IP bans and access denied scenarios.
    """
    error_detail = exc.detail if hasattr(exc, "detail") else "Access Denied"
    
    logger.warning(f"Forbidden access on {request.url.path}")
    
    return JSONResponse(
        status_code=403,
        content={"error": str(error_detail)},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """
    Custom handler for 404 Not Found errors.
    Tracks 404 errors for security monitoring and serves React app.
    Matches Flask not_found_error() handler behavior.
    """
    from database.traffic_db import Error404Tracker
    
    # Get real client IP from request headers (handles proxies)
    client_ip = _get_real_ip_from_request(request)
    path = str(request.url.path)
    
    # Track 404 error for security monitoring
    Error404Tracker.track_404(client_ip, path)
    
    # Serve React app (React Router handles 404)
    return serve_react_app()


def _get_real_ip_from_request(request: Request) -> str:
    """
    Get the real client IP address from FastAPI Request, handling proxy headers.
    
    Checks headers in order of preference:
    1. CF-Connecting-IP (Cloudflare - highest priority)
    2. True-Client-IP (Cloudflare Enterprise)
    3. X-Real-IP (commonly set by nginx)
    4. X-Forwarded-For (standard proxy header, uses first IP if multiple)
    5. X-Client-IP (some proxies)
    6. request.client.host (fallback to direct connection)
    
    Args:
        request: FastAPI Request object
        
    Returns:
        str: The most likely real client IP address
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
        # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
        # The first IP should be the original client
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


@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc: HTTPException):
    """
    Custom handler for 429 Too Many Requests errors.
    Matches Flask rate_limit_exceeded() handler behavior.
    """
    logger.warning(f"Rate limit exceeded for {request.client.host if request.client else 'unknown'}: {request.url.path}")
    
    # For API requests, return JSON response
    if str(request.url.path).startswith("/api/"):
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "message": "Rate limit exceeded. Please slow down your requests.",
                "retry_after": 60,
            },
        )
    
    # For web requests, redirect to React rate-limited page
    return RedirectResponse(url="/rate-limited", status_code=303)


@app.exception_handler(RateLimitExceeded)
async def slowapi_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for slowapi RateLimitExceeded exceptions.
    This handles rate limits from the slowapi limiter.
    """
    logger.warning(f"Rate limit exceeded for {request.client.host if request.client else 'unknown'}: {request.url.path}")
    
    # For API requests, return JSON response
    if str(request.url.path).startswith("/api/"):
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "message": "Rate limit exceeded. Please slow down your requests.",
                "retry_after": 60,
            },
        )
    
    # For web requests, redirect to React rate-limited page
    return RedirectResponse(url="/rate-limited", status_code=303)


@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: HTTPException):
    """
    Custom handler for 500 Internal Server Error.
    Matches Flask internal_server_error() handler behavior.
    """
    logger.error(f"Server Error on {request.url.path}: {exc}")
    
    # Redirect to React error page
    return RedirectResponse(url="/error", status_code=303)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Generic exception handler for unhandled exceptions.
    Logs the error and redirects to error page.
    """
    logger.error(f"Unhandled exception on {request.url.path}: {exc}")
    
    # Redirect to React error page
    return RedirectResponse(url="/error", status_code=303)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom handler for request validation errors.
    Returns a 400 response with validation error details.
    """
    logger.warning(f"Validation error on {request.url.path}: {exc}")
    
    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": str(exc)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Generic HTTP exception handler.
    Handles any HTTPException not caught by specific handlers.
    """
    # Handle 404 specially - serve React app
    if exc.status_code == 404:
        return await not_found_handler(request, exc)
    
    # Handle rate limiting
    if exc.status_code == 429:
        return await rate_limit_handler(request, exc)
    
    # Handle other HTTP exceptions
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


# Development server entry point
if __name__ == "__main__":
    import uvicorn
    
    # Get environment variables
    host_ip = os.getenv("FLASK_HOST_IP", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
    
    # Run with uvicorn
    uvicorn.run(
        "app_fastapi:app",
        host=host_ip,
        port=port,
        reload=debug,
        log_level="debug" if debug else "info",
    )
