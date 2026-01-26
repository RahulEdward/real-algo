# routers/chartink.py
"""
FastAPI Chartink Router for RealAlgo
Handles Chartink strategy management and webhooks.
Requirements: 4.7
"""

import json
import os
import queue
import threading
import time as time_module
import uuid
from collections import deque
from datetime import datetime, time
from time import time
from typing import Optional

import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database.auth_db import get_api_key_for_tradingview
from database.chartink_db import (
    ChartinkStrategy,
    ChartinkSymbolMapping,
    add_symbol_mapping,
    bulk_add_symbol_mappings,
    create_strategy,
    db_session,
    delete_strategy,
    delete_symbol_mapping,
    get_all_strategies,
    get_strategy,
    get_strategy_by_webhook_id,
    get_symbol_mappings,
    get_user_strategies,
    toggle_strategy,
    update_strategy_times,
)
from database.symbol import enhanced_search_symbols
from dependencies_fastapi import check_session_validity, get_session
from limiter_fastapi import limiter
from utils.logging import get_logger

logger = get_logger(__name__)

# Rate limiting configuration
WEBHOOK_RATE_LIMIT = os.getenv("WEBHOOK_RATE_LIMIT", "100/minute")
STRATEGY_RATE_LIMIT = os.getenv("STRATEGY_RATE_LIMIT", "200/minute")

chartink_router = APIRouter(prefix="/chartink", tags=["chartink"])
templates = Jinja2Templates(directory="templates")

# Initialize scheduler for time-based controls
scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))
scheduler.start()

# Get base URL from environment or default to localhost
BASE_URL = os.getenv("HOST_SERVER", "http://127.0.0.1:5000")

# Valid exchanges
VALID_EXCHANGES = ["NSE", "BSE"]

# Separate queues for different order types
regular_order_queue = queue.Queue()
smart_order_queue = queue.Queue()

# Order processor state
order_processor_running = False
order_processor_lock = threading.Lock()

# Rate limiting state for regular orders
last_regular_orders = deque(maxlen=10)


def process_orders():
    """Background task to process orders from both queues with rate limiting."""
    global order_processor_running

    while True:
        try:
            try:
                smart_order = smart_order_queue.get_nowait()
                if smart_order is None:
                    break

                try:
                    response = requests.post(f"{BASE_URL}/api/v1/placesmartorder", json=smart_order["payload"])
                    if response.ok:
                        logger.info(f"Smart order placed for {smart_order['payload']['symbol']}")
                    else:
                        logger.error(f"Error placing smart order: {response.text}")
                except Exception as e:
                    logger.error(f"Error placing smart order: {str(e)}")

                time_module.sleep(1)
                continue

            except queue.Empty:
                pass

            now = time()
            while last_regular_orders and now - last_regular_orders[0] > 1:
                last_regular_orders.popleft()

            if len(last_regular_orders) < 10:
                try:
                    regular_order = regular_order_queue.get_nowait()
                    if regular_order is None:
                        break

                    try:
                        response = requests.post(f"{BASE_URL}/api/v1/placeorder", json=regular_order["payload"])
                        if response.ok:
                            logger.info(f"Regular order placed for {regular_order['payload']['symbol']}")
                            last_regular_orders.append(now)
                        else:
                            logger.error(f"Error placing regular order: {response.text}")
                    except Exception as e:
                        logger.error(f"Error placing regular order: {str(e)}")

                except queue.Empty:
                    time_module.sleep(0.1)
            else:
                time_module.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in order processor: {str(e)}")
            time_module.sleep(0.1)

    with order_processor_lock:
        order_processor_running = False


def ensure_order_processor():
    """Ensure order processor is running."""
    global order_processor_running

    with order_processor_lock:
        if not order_processor_running:
            order_processor_running = True
            thread = threading.Thread(target=process_orders, daemon=True)
            thread.start()


def queue_order(endpoint, payload):
    """Add order to appropriate processing queue."""
    ensure_order_processor()

    if endpoint == "placesmartorder":
        smart_order_queue.put({"endpoint": endpoint, "payload": payload})
    else:
        regular_order_queue.put({"endpoint": endpoint, "payload": payload})


def validate_strategy_times(start_time, end_time, squareoff_time):
    """Validate strategy time settings."""
    try:
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        squareoff = datetime.strptime(squareoff_time, "%H:%M").time()

        if start >= end:
            return False, "Start time must be before end time"
        if end >= squareoff:
            return False, "End time must be before square off time"

        return True, None
    except ValueError:
        return False, "Invalid time format"


def validate_strategy_name(name):
    """Validate strategy name format."""
    if not name:
        return False, "Strategy name is required"

    if not name.startswith("chartink_"):
        name = f"chartink_{name}"

    if not all(c.isalnum() or c in ["-", "_", " "] for c in name.replace("chartink_", "")):
        return False, "Strategy name can only contain letters, numbers, spaces, hyphens and underscores"

    return True, name


def schedule_squareoff(strategy_id):
    """Schedule squareoff for intraday strategy."""
    strategy = get_strategy(strategy_id)
    if not strategy or not strategy.is_intraday or not strategy.squareoff_time:
        return

    try:
        hours, minutes = map(int, strategy.squareoff_time.split(":"))
        job_id = f"squareoff_{strategy_id}"

        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        scheduler.add_job(
            squareoff_positions,
            "cron",
            hour=hours,
            minute=minutes,
            args=[strategy_id],
            id=job_id,
            timezone=pytz.timezone("Asia/Kolkata"),
        )
        logger.info(f"Scheduled squareoff for strategy {strategy_id} at {hours}:{minutes}")
    except Exception as e:
        logger.error(f"Error scheduling squareoff for strategy {strategy_id}: {str(e)}")


def squareoff_positions(strategy_id):
    """Square off all positions for intraday strategy."""
    try:
        strategy = get_strategy(strategy_id)
        if not strategy or not strategy.is_intraday:
            return

        api_key = get_api_key_for_tradingview(strategy.user_id)
        if not api_key:
            logger.error(f"No API key found for strategy {strategy_id}")
            return

        mappings = get_symbol_mappings(strategy_id)

        for mapping in mappings:
            payload = {
                "apikey": api_key,
                "strategy": strategy.name,
                "symbol": mapping.chartink_symbol,
                "exchange": mapping.exchange,
                "action": "SELL",
                "product": mapping.product_type,
                "pricetype": "MARKET",
                "quantity": "0",
                "position_size": "0",
                "price": "0",
                "trigger_price": "0",
                "disclosed_quantity": "0",
            }
            queue_order("placesmartorder", payload)

    except Exception as e:
        logger.error(f"Error in squareoff_positions for strategy {strategy_id}: {str(e)}")



@chartink_router.get("/")
async def index(request: Request, session: dict = Depends(check_session_validity)):
    """List all strategies."""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    strategies = get_user_strategies(user_id)
    return templates.TemplateResponse("chartink/index.html", {"request": request, "strategies": strategies})


@chartink_router.get("/new")
async def new_strategy_get(request: Request, session: dict = Depends(check_session_validity)):
    """Create new strategy - GET."""
    return templates.TemplateResponse("chartink/new_strategy.html", {"request": request})


@chartink_router.post("/new")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def new_strategy_post(request: Request, session: dict = Depends(check_session_validity)):
    """Create new strategy - POST."""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        form = await request.form()
        name = form.get("name", "").strip()
        is_valid_name, name_result = validate_strategy_name(name)
        if not is_valid_name:
            return templates.TemplateResponse("chartink/new_strategy.html", {
                "request": request, "flash_message": name_result, "flash_category": "error"
            })
        name = name_result

        is_intraday = form.get("type") == "intraday"
        start_time = form.get("start_time") if is_intraday else None
        end_time = form.get("end_time") if is_intraday else None
        squareoff_time = form.get("squareoff_time") if is_intraday else None

        if is_intraday:
            if not all([start_time, end_time, squareoff_time]):
                return templates.TemplateResponse("chartink/new_strategy.html", {
                    "request": request, "flash_message": "All time fields are required for intraday strategy", "flash_category": "error"
                })

            is_valid, error_msg = validate_strategy_times(start_time, end_time, squareoff_time)
            if not is_valid:
                return templates.TemplateResponse("chartink/new_strategy.html", {
                    "request": request, "flash_message": error_msg, "flash_category": "error"
                })

        webhook_id = str(uuid.uuid4())

        strategy = create_strategy(
            name=name, webhook_id=webhook_id, user_id=user_id, is_intraday=is_intraday,
            start_time=start_time, end_time=end_time, squareoff_time=squareoff_time,
        )

        if strategy:
            if is_intraday and squareoff_time:
                schedule_squareoff(strategy.id)
            return RedirectResponse(url=f"/chartink/{strategy.id}", status_code=302)
        else:
            return templates.TemplateResponse("chartink/new_strategy.html", {
                "request": request, "flash_message": "Error creating strategy", "flash_category": "error"
            })
    except Exception as e:
        logger.error(f"Error creating strategy: {str(e)}")
        return templates.TemplateResponse("chartink/new_strategy.html", {
            "request": request, "flash_message": "Error creating strategy", "flash_category": "error"
        })


@chartink_router.get("/{strategy_id}")
async def view_strategy(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """View strategy details."""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    strategy = get_strategy(strategy_id)
    if not strategy or strategy.user_id != user_id:
        return JSONResponse({"error": "Strategy not found"}, status_code=404)

    symbol_mappings = get_symbol_mappings(strategy_id)
    return templates.TemplateResponse("chartink/view_strategy.html", {
        "request": request, "strategy": strategy, "symbol_mappings": symbol_mappings
    })


@chartink_router.post("/{strategy_id}/delete")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def delete_strategy_route(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Delete a strategy."""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "error": "Session expired"}, status_code=401)

    strategy = get_strategy(strategy_id)
    if not strategy:
        return JSONResponse({"status": "error", "error": "Strategy not found"}, status_code=404)

    if strategy.user_id != user_id:
        return JSONResponse({"status": "error", "error": "Unauthorized"}, status_code=403)

    try:
        job_id = f"squareoff_{strategy_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        if delete_strategy(strategy_id):
            return JSONResponse({"status": "success"})
        else:
            return JSONResponse({"status": "error", "error": "Failed to delete strategy"}, status_code=500)
    except Exception as e:
        logger.error(f"Error deleting strategy {strategy_id}: {str(e)}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@chartink_router.post("/{strategy_id}/toggle")
async def toggle_strategy_route(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Toggle strategy active status."""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    strategy = get_strategy(strategy_id)
    if not strategy or strategy.user_id != user_id:
        return JSONResponse({"error": "Strategy not found"}, status_code=404)

    try:
        strategy = toggle_strategy(strategy_id)
        return RedirectResponse(url=f"/chartink/{strategy_id}", status_code=302)
    except Exception as e:
        logger.error(f"Error toggling strategy: {str(e)}")
        return RedirectResponse(url=f"/chartink/{strategy_id}", status_code=302)


@chartink_router.get("/search")
async def search_symbols(request: Request, q: str = Query(""), exchange: Optional[str] = Query(None), session: dict = Depends(check_session_validity)):
    """Search symbols endpoint."""
    query = q.strip()
    if not query:
        return JSONResponse({"results": []})

    results = enhanced_search_symbols(query, exchange)
    return JSONResponse({
        "results": [{"symbol": result.symbol, "name": result.name, "exchange": result.exchange} for result in results]
    })


# JSON API Endpoints for React Frontend

@chartink_router.get("/api/strategies")
async def api_get_strategies(request: Request, session: dict = Depends(check_session_validity)):
    """API: Get all strategies for current user as JSON."""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    strategies = get_user_strategies(user_id)
    return JSONResponse({
        "strategies": [
            {
                "id": s.id, "name": s.name, "webhook_id": s.webhook_id, "is_active": s.is_active,
                "is_intraday": s.is_intraday, "start_time": s.start_time, "end_time": s.end_time,
                "squareoff_time": s.squareoff_time,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in strategies
        ]
    })


@chartink_router.get("/api/strategy/{strategy_id}")
async def api_get_strategy(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """API: Get single strategy with mappings as JSON."""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    strategy = get_strategy(strategy_id)
    if not strategy:
        return JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)

    if strategy.user_id != user_id:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    mappings = get_symbol_mappings(strategy_id)

    return JSONResponse({
        "strategy": {
            "id": strategy.id, "name": strategy.name, "webhook_id": strategy.webhook_id,
            "is_active": strategy.is_active, "is_intraday": strategy.is_intraday,
            "start_time": strategy.start_time, "end_time": strategy.end_time,
            "squareoff_time": strategy.squareoff_time,
            "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
            "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
        },
        "mappings": [
            {
                "id": m.id, "chartink_symbol": m.chartink_symbol, "exchange": m.exchange,
                "quantity": m.quantity, "product_type": m.product_type,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ],
    })


@chartink_router.post("/api/strategy")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def api_create_strategy(request: Request, session: dict = Depends(check_session_validity)):
    """API: Create new strategy (JSON)."""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    try:
        data = await request.json()
        if not data:
            return JSONResponse({"status": "error", "message": "No data provided"}, status_code=400)

        name = data.get("name", "").strip()
        strategy_type = data.get("strategy_type", "intraday")
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        squareoff_time = data.get("squareoff_time")

        is_valid_name, name_result = validate_strategy_name(name)
        if not is_valid_name:
            return JSONResponse({"status": "error", "message": name_result}, status_code=400)
        name = name_result

        is_intraday = strategy_type == "intraday"

        if is_intraday:
            if not all([start_time, end_time, squareoff_time]):
                return JSONResponse({"status": "error", "message": "All time fields are required for intraday strategy"}, status_code=400)

            is_valid, error_msg = validate_strategy_times(start_time, end_time, squareoff_time)
            if not is_valid:
                return JSONResponse({"status": "error", "message": error_msg}, status_code=400)
        else:
            start_time = end_time = squareoff_time = None

        webhook_id = str(uuid.uuid4())

        strategy = create_strategy(
            name=name, webhook_id=webhook_id, user_id=user_id, is_intraday=is_intraday,
            start_time=start_time, end_time=end_time, squareoff_time=squareoff_time,
        )

        if strategy:
            if is_intraday and squareoff_time:
                schedule_squareoff(strategy.id)
            return JSONResponse({"status": "success", "data": {"strategy_id": strategy.id}})
        else:
            return JSONResponse({"status": "error", "message": "Failed to create strategy"}, status_code=500)

    except Exception as e:
        logger.error(f"Error creating strategy via API: {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@chartink_router.post("/api/strategy/{strategy_id}/toggle")
async def api_toggle_strategy(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """API: Toggle strategy active status (JSON)."""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    strategy = get_strategy(strategy_id)
    if not strategy:
        return JSONResponse({"status": "error", "message": "Strategy not found"}, status_code=404)

    if strategy.user_id != user_id:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    try:
        updated_strategy = toggle_strategy(strategy_id)
        if updated_strategy:
            return JSONResponse({"status": "success", "data": {"is_active": updated_strategy.is_active}})
        else:
            return JSONResponse({"status": "error", "message": "Failed to toggle strategy"}, status_code=500)
    except Exception as e:
        logger.error(f"Error toggling strategy via API: {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@chartink_router.post("/webhook/{webhook_id}")
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def webhook(webhook_id: str, request: Request):
    """Handle webhook from Chartink."""
    try:
        strategy = get_strategy_by_webhook_id(webhook_id)
        if not strategy:
            logger.error(f"Strategy not found for webhook ID: {webhook_id}")
            return JSONResponse({"status": "error", "error": "Invalid webhook ID"}, status_code=404)

        if not strategy.is_active:
            logger.info(f"Strategy {strategy.id} is inactive, ignoring webhook")
            return JSONResponse({"status": "success", "message": "Strategy is inactive"})

        data = await request.json()
        if not data:
            logger.error(f"No data received in webhook for strategy {strategy.id}")
            return JSONResponse({"status": "error", "error": "No data received"}, status_code=400)

        logger.info(f"Received webhook data: {data}")

        scan_name = data.get("scan_name", "").upper()
        if "BUY" in scan_name:
            action = "BUY"
            use_smart_order = False
            is_entry_order = True
        elif "SELL" in scan_name:
            action = "SELL"
            use_smart_order = True
            is_entry_order = False
        elif "SHORT" in scan_name:
            action = "SELL"
            use_smart_order = False
            is_entry_order = True
        elif "COVER" in scan_name:
            action = "BUY"
            use_smart_order = True
            is_entry_order = False
        else:
            error_msg = "No valid action keyword (BUY/SELL/SHORT/COVER) found in scan name"
            logger.error(error_msg)
            return JSONResponse({"status": "error", "error": error_msg}, status_code=400)

        if strategy.is_intraday:
            current_time = datetime.now(pytz.timezone("Asia/Kolkata")).time()
            start_time = datetime.strptime(strategy.start_time, "%H:%M").time()
            end_time = datetime.strptime(strategy.end_time, "%H:%M").time()
            squareoff_time = datetime.strptime(strategy.squareoff_time, "%H:%M").time()

            if current_time < start_time:
                return JSONResponse({"status": "error", "error": "Cannot place orders before start time"}, status_code=400)

            if current_time >= squareoff_time:
                return JSONResponse({"status": "error", "error": "Cannot place orders after squareoff time"}, status_code=400)

            if is_entry_order and current_time >= end_time:
                return JSONResponse({"status": "error", "error": "Cannot place entry orders after end time"}, status_code=400)

        symbols = data.get("stocks", "").split(",")
        if not symbols:
            logger.error("No symbols received in webhook")
            return JSONResponse({"status": "error", "error": "No symbols received"}, status_code=400)

        mappings = get_symbol_mappings(strategy.id)
        if not mappings:
            logger.error(f"No symbol mappings found for strategy {strategy.id}")
            return JSONResponse({"status": "error", "error": "No symbol mappings configured"}, status_code=400)

        mapping_dict = {m.chartink_symbol: m for m in mappings}

        api_key = get_api_key_for_tradingview(strategy.user_id)
        if not api_key:
            logger.error(f"No API key found for user {strategy.user_id}")
            return JSONResponse({"status": "error", "error": "No API key found"}, status_code=401)

        processed_symbols = []
        for symbol in symbols:
            symbol = symbol.strip()
            if not symbol:
                continue

            mapping = mapping_dict.get(symbol)
            if not mapping:
                logger.warning(f"No mapping found for symbol {symbol} in strategy {strategy.id}")
                continue

            payload = {
                "apikey": api_key,
                "strategy": strategy.name,
                "symbol": mapping.chartink_symbol,
                "exchange": mapping.exchange,
                "action": action,
                "product": mapping.product_type,
                "pricetype": "MARKET",
            }

            if use_smart_order:
                payload.update({
                    "quantity": "0", "position_size": "0", "price": "0",
                    "trigger_price": "0", "disclosed_quantity": "0",
                })
                endpoint = "placesmartorder"
            else:
                payload.update({"quantity": str(mapping.quantity)})
                endpoint = "placeorder"

            logger.info(f"Queueing {endpoint} with payload: {payload}")
            queue_order(endpoint, payload)
            processed_symbols.append(symbol)

        if processed_symbols:
            return JSONResponse({"status": "success", "message": f"Orders queued for symbols: {', '.join(processed_symbols)}"})
        else:
            return JSONResponse({"status": "warning", "message": "No orders were queued"})

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
