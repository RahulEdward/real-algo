# routers/strategy.py
"""
FastAPI Strategy Router for RealAlgo
Handles strategy management and webhooks for trading platforms.
Requirements: 4.7
"""

import os
import queue
import re
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
from database.strategy_db import (
    Strategy,
    StrategySymbolMapping,
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
from utils.session import is_session_valid

logger = get_logger(__name__)

# Rate limiting configuration
WEBHOOK_RATE_LIMIT = os.getenv("WEBHOOK_RATE_LIMIT", "100/minute")
STRATEGY_RATE_LIMIT = os.getenv("STRATEGY_RATE_LIMIT", "200/minute")

strategy_router = APIRouter(prefix="/strategy", tags=["strategy"])
templates = Jinja2Templates(directory="templates")

# Initialize scheduler for time-based controls
scheduler = BackgroundScheduler(
    timezone=pytz.timezone("Asia/Kolkata"),
    job_defaults={"coalesce": True, "misfire_grace_time": 300, "max_instances": 1},
)
scheduler.start()

# Get base URL from environment or default to localhost
BASE_URL = os.getenv("HOST_SERVER", "http://127.0.0.1:5000")

# Valid exchanges
VALID_EXCHANGES = ["NSE", "BSE", "NFO", "CDS", "BFO", "BCD", "MCX", "NCDEX"]

# Product types per exchange
EXCHANGE_PRODUCTS = {
    "NSE": ["MIS", "CNC"], "BSE": ["MIS", "CNC"],
    "NFO": ["MIS", "NRML"], "CDS": ["MIS", "NRML"],
    "BFO": ["MIS", "NRML"], "BCD": ["MIS", "NRML"],
    "MCX": ["MIS", "NRML"], "NCDEX": ["MIS", "NRML"],
}

DEFAULT_EXCHANGE = "NSE"
DEFAULT_PRODUCT = "MIS"

# Separate queues for different order types
regular_order_queue = queue.Queue()
smart_order_queue = queue.Queue()

# Order processor state
order_processor_running = False
order_processor_lock = threading.Lock()
last_regular_orders = deque(maxlen=10)


def process_orders():
    """Background task to process orders from both queues with rate limiting"""
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
                        logger.info(f"Smart order placed for {smart_order['payload']['symbol']} in strategy {smart_order['payload']['strategy']}")
                    else:
                        logger.error(f"Error placing smart order for {smart_order['payload']['symbol']}: {response.text}")
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
                            logger.info(f"Regular order placed for {regular_order['payload']['symbol']} in strategy {regular_order['payload']['strategy']}")
                            last_regular_orders.append(now)
                        else:
                            logger.error(f"Error placing regular order for {regular_order['payload']['symbol']}: {response.text}")
                    except Exception as e:
                        logger.error(f"Error placing regular order: {str(e)}")

                except queue.Empty:
                    pass

            time_module.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in order processor: {str(e)}")
            time_module.sleep(1)


def ensure_order_processor():
    """Ensure the order processor is running"""
    global order_processor_running
    with order_processor_lock:
        if not order_processor_running:
            threading.Thread(target=process_orders, daemon=True).start()
            order_processor_running = True


def queue_order(endpoint, payload):
    """Add order to appropriate queue"""
    ensure_order_processor()
    if endpoint == "placesmartorder":
        smart_order_queue.put({"payload": payload})
    else:
        regular_order_queue.put({"payload": payload})


def validate_strategy_times(start_time, end_time, squareoff_time):
    """Validate strategy time settings"""
    try:
        if not all([start_time, end_time, squareoff_time]):
            return False, "All time fields are required"

        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        squareoff = datetime.strptime(squareoff_time, "%H:%M").time()

        market_open = datetime.strptime("09:15", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()

        if start < market_open:
            return False, "Start time cannot be before market open (9:15)"
        if end > market_close:
            return False, "End time cannot be after market close (15:30)"
        if squareoff > market_close:
            return False, "Square off time cannot be after market close (15:30)"
        if start >= end:
            return False, "Start time must be before end time"
        if squareoff < start:
            return False, "Square off time must be after start time"
        if squareoff < end:
            return False, "Square off time must be after end time"

        return True, None

    except ValueError:
        return False, "Invalid time format. Use HH:MM format"


def validate_strategy_name(name):
    """Validate strategy name format"""
    if not name:
        return False, "Strategy name is required"

    if len(name) < 3 or len(name) > 50:
        return False, "Strategy name must be between 3 and 50 characters"

    if not re.match(r"^[A-Za-z0-9\s\-_]+$", name):
        return False, "Strategy name can only contain letters, numbers, spaces, hyphens and underscores"

    return True, None


def schedule_squareoff(strategy_id):
    """Schedule squareoff for intraday strategy"""
    strategy = get_strategy(strategy_id)
    if not strategy or not strategy.is_intraday or not strategy.squareoff_time:
        return

    try:
        hours, minutes = map(int, strategy.squareoff_time.split(":"))
        job_id = f"squareoff_{strategy_id}"

        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        scheduler.add_job(
            squareoff_positions, "cron", hour=hours, minute=minutes,
            args=[strategy_id], id=job_id, timezone=pytz.timezone("Asia/Kolkata"),
        )
        logger.info(f"Scheduled squareoff for strategy {strategy_id} at {hours}:{minutes}")
    except Exception as e:
        logger.error(f"Error scheduling squareoff for strategy {strategy_id}: {str(e)}")


def squareoff_positions(strategy_id):
    """Square off all positions for intraday strategy"""
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
                "apikey": api_key, "symbol": mapping.symbol, "exchange": mapping.exchange,
                "product": mapping.product_type, "strategy": strategy.name, "action": "SELL",
                "pricetype": "MARKET", "quantity": "0", "position_size": "0",
                "price": "0", "trigger_price": "0", "disclosed_quantity": "0",
            }
            queue_order("placesmartorder", payload)

    except Exception as e:
        logger.error(f"Error in squareoff_positions for strategy {strategy_id}: {str(e)}")


@strategy_router.get("/")
async def index(request: Request, session: dict = Depends(get_session)):
    """List all strategies"""
    if not is_session_valid():
        return RedirectResponse(url="/auth/login", status_code=302)

    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        strategies = get_user_strategies(user_id)
        return templates.TemplateResponse("strategy/index.html", {"request": request, "strategies": strategies})
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        return RedirectResponse(url="/dashboard", status_code=302)


@strategy_router.get("/new")
async def new_strategy_get(request: Request, session: dict = Depends(check_session_validity)):
    """Create new strategy - GET"""
    return templates.TemplateResponse("strategy/new_strategy.html", {"request": request})


@strategy_router.post("/new")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def new_strategy_post(request: Request, session: dict = Depends(check_session_validity)):
    """Create new strategy - POST"""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        form = await request.form()
        platform = form.get("platform", "").strip()
        name = form.get("name", "").strip()

        if not platform:
            return templates.TemplateResponse("strategy/new_strategy.html", {
                "request": request, "flash_message": "Please select a platform", "flash_category": "error"
            })

        name = f"{platform}_{name}"

        strategy_type = form.get("type")
        trading_mode = form.get("trading_mode", "LONG")
        start_time = form.get("start_time")
        end_time = form.get("end_time")
        squareoff_time = form.get("squareoff_time")

        is_valid, error_msg = validate_strategy_name(name)
        if not is_valid:
            return templates.TemplateResponse("strategy/new_strategy.html", {
                "request": request, "flash_message": error_msg, "flash_category": "error"
            })

        is_intraday = strategy_type == "intraday"
        if is_intraday:
            is_valid, error_msg = validate_strategy_times(start_time, end_time, squareoff_time)
            if not is_valid:
                return templates.TemplateResponse("strategy/new_strategy.html", {
                    "request": request, "flash_message": error_msg, "flash_category": "error"
                })
        else:
            start_time = end_time = squareoff_time = None

        webhook_id = str(uuid.uuid4())

        strategy = create_strategy(
            name=name, webhook_id=webhook_id, user_id=user_id, is_intraday=is_intraday,
            trading_mode=trading_mode, start_time=start_time, end_time=end_time,
            squareoff_time=squareoff_time, platform=platform,
        )

        if strategy:
            if strategy.is_intraday:
                schedule_squareoff(strategy.id)
            return RedirectResponse(url=f"/strategy/{strategy.id}/configure", status_code=302)
        else:
            return templates.TemplateResponse("strategy/new_strategy.html", {
                "request": request, "flash_message": "Error creating strategy", "flash_category": "error"
            })

    except Exception as e:
        logger.error(f"Error creating strategy: {str(e)}")
        return templates.TemplateResponse("strategy/new_strategy.html", {
            "request": request, "flash_message": "Error creating strategy", "flash_category": "error"
        })


@strategy_router.get("/{strategy_id}")
async def view_strategy(strategy_id: int, request: Request, session: dict = Depends(get_session)):
    """View strategy details"""
    if not is_session_valid():
        return RedirectResponse(url="/auth/login", status_code=302)

    strategy = get_strategy(strategy_id)
    if not strategy:
        return RedirectResponse(url="/strategy", status_code=302)

    if strategy.user_id != session.get("user"):
        return RedirectResponse(url="/strategy", status_code=302)

    symbol_mappings = get_symbol_mappings(strategy_id)

    return templates.TemplateResponse("strategy/view_strategy.html", {
        "request": request, "strategy": strategy, "symbol_mappings": symbol_mappings
    })


@strategy_router.post("/toggle/{strategy_id}")
async def toggle_strategy_route(strategy_id: int, request: Request, session: dict = Depends(get_session)):
    """Toggle strategy active status"""
    if not is_session_valid():
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        strategy = toggle_strategy(strategy_id)
        if strategy:
            if strategy.is_active:
                schedule_squareoff(strategy_id)
            else:
                try:
                    scheduler.remove_job(f"squareoff_{strategy_id}")
                except Exception:
                    pass

            return RedirectResponse(url=f"/strategy/{strategy_id}", status_code=302)
        else:
            return RedirectResponse(url="/strategy", status_code=302)
    except Exception as e:
        return RedirectResponse(url="/strategy", status_code=302)


@strategy_router.post("/{strategy_id}/delete")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def delete_strategy_route(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Delete strategy"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "error": "Session expired"}, status_code=401)

    strategy = get_strategy(strategy_id)
    if not strategy:
        return JSONResponse({"status": "error", "error": "Strategy not found"}, status_code=404)

    if strategy.user_id != user_id:
        return JSONResponse({"status": "error", "error": "Unauthorized"}, status_code=403)

    try:
        try:
            scheduler.remove_job(f"squareoff_{strategy_id}")
        except Exception:
            pass

        if delete_strategy(strategy_id):
            return JSONResponse({"status": "success"})
        else:
            return JSONResponse({"status": "error", "error": "Failed to delete strategy"}, status_code=500)
    except Exception as e:
        logger.error(f"Error deleting strategy {strategy_id}: {str(e)}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@strategy_router.get("/{strategy_id}/configure")
async def configure_symbols_get(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Configure symbols for strategy - GET"""
    user_id = session.get("user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=302)

    strategy = get_strategy(strategy_id)
    if not strategy:
        return JSONResponse({"error": "Strategy not found"}, status_code=404)

    if strategy.user_id != user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    symbol_mappings = get_symbol_mappings(strategy_id)
    return templates.TemplateResponse("strategy/configure_symbols.html", {
        "request": request, "strategy": strategy, "symbol_mappings": symbol_mappings, "exchanges": VALID_EXCHANGES
    })


@strategy_router.post("/{strategy_id}/configure")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def configure_symbols_post(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Configure symbols for strategy - POST"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "error": "Session expired"}, status_code=401)

    strategy = get_strategy(strategy_id)
    if not strategy:
        return JSONResponse({"status": "error", "error": "Strategy not found"}, status_code=404)

    if strategy.user_id != user_id:
        return JSONResponse({"status": "error", "error": "Unauthorized"}, status_code=403)

    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        if "symbols" in data:
            symbols_text = data.get("symbols")
            mappings = []

            for line in symbols_text.strip().split("\n"):
                if not line.strip():
                    continue

                parts = line.strip().split(",")
                if len(parts) != 4:
                    raise ValueError(f"Invalid format in line: {line}")

                symbol, exchange, quantity, product = parts
                if exchange not in VALID_EXCHANGES:
                    raise ValueError(f"Invalid exchange: {exchange}")

                mappings.append({
                    "symbol": symbol.strip(), "exchange": exchange.strip(),
                    "quantity": int(quantity), "product_type": product.strip(),
                })

            if mappings:
                bulk_add_symbol_mappings(strategy_id, mappings)
                return JSONResponse({"status": "success"})

        else:
            symbol = data.get("symbol")
            exchange = data.get("exchange")
            quantity = data.get("quantity")
            product_type = data.get("product_type")

            if not all([symbol, exchange, quantity, product_type]):
                missing = []
                if not symbol: missing.append("symbol")
                if not exchange: missing.append("exchange")
                if not quantity: missing.append("quantity")
                if not product_type: missing.append("product_type")
                raise ValueError(f"Missing required fields: {', '.join(missing)}")

            if exchange not in VALID_EXCHANGES:
                raise ValueError(f"Invalid exchange: {exchange}")

            try:
                quantity = int(quantity)
            except ValueError:
                raise ValueError("Quantity must be a valid number")

            if quantity <= 0:
                raise ValueError("Quantity must be greater than 0")

            mapping = add_symbol_mapping(
                strategy_id=strategy_id, symbol=symbol, exchange=exchange,
                quantity=quantity, product_type=product_type,
            )

            if mapping:
                return JSONResponse({"status": "success"})
            else:
                raise ValueError("Failed to add symbol mapping")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error configuring symbols: {error_msg}")
        return JSONResponse({"status": "error", "error": error_msg}, status_code=400)


@strategy_router.post("/{strategy_id}/symbol/{mapping_id}/delete")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def delete_symbol(strategy_id: int, mapping_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Delete symbol mapping"""
    username = session.get("user")
    if not username:
        return JSONResponse({"status": "error", "error": "Session expired"}, status_code=401)

    strategy = get_strategy(strategy_id)
    if not strategy or strategy.user_id != username:
        return JSONResponse({"status": "error", "error": "Strategy not found"}, status_code=404)

    try:
        if delete_symbol_mapping(mapping_id):
            return JSONResponse({"status": "success"})
        else:
            return JSONResponse({"status": "error", "error": "Symbol mapping not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error deleting symbol mapping: {str(e)}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=400)


@strategy_router.get("/search")
async def search_symbols(request: Request, q: str = Query(""), exchange: Optional[str] = Query(None), session: dict = Depends(check_session_validity)):
    """Search symbols endpoint"""
    query = q.strip()
    if not query:
        return JSONResponse({"results": []})

    results = enhanced_search_symbols(query, exchange)
    return JSONResponse({
        "results": [{"symbol": result.symbol, "name": result.name, "exchange": result.exchange} for result in results]
    })


# =============================================================================
# JSON API Endpoints for React Frontend
# =============================================================================

@strategy_router.get("/api/strategies")
async def api_get_strategies(request: Request, session: dict = Depends(check_session_validity)):
    """API: Get all strategies for current user as JSON"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    strategies = get_user_strategies(user_id)
    return JSONResponse({
        "strategies": [
            {
                "id": s.id, "name": s.name, "webhook_id": s.webhook_id, "is_active": s.is_active,
                "is_intraday": s.is_intraday, "trading_mode": s.trading_mode, "platform": s.platform,
                "start_time": s.start_time, "end_time": s.end_time, "squareoff_time": s.squareoff_time,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in strategies
        ]
    })


@strategy_router.get("/api/strategy/{strategy_id}")
async def api_get_strategy(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """API: Get single strategy with mappings as JSON"""
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
            "trading_mode": strategy.trading_mode, "platform": strategy.platform,
            "start_time": strategy.start_time, "end_time": strategy.end_time,
            "squareoff_time": strategy.squareoff_time,
            "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
            "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
        },
        "mappings": [
            {
                "id": m.id, "symbol": m.symbol, "exchange": m.exchange,
                "quantity": m.quantity, "product_type": m.product_type,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ],
    })


@strategy_router.post("/api/strategy")
@limiter.limit(STRATEGY_RATE_LIMIT)
async def api_create_strategy(request: Request, session: dict = Depends(check_session_validity)):
    """API: Create new strategy (JSON)"""
    user_id = session.get("user")
    if not user_id:
        return JSONResponse({"status": "error", "message": "Session expired"}, status_code=401)

    try:
        data = await request.json()
        if not data:
            return JSONResponse({"status": "error", "message": "No data provided"}, status_code=400)

        platform = data.get("platform", "").strip()
        name = data.get("name", "").strip()
        strategy_type = data.get("strategy_type", "intraday")
        trading_mode = data.get("trading_mode", "LONG")
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        squareoff_time = data.get("squareoff_time")

        if not platform:
            return JSONResponse({"status": "error", "message": "Platform is required"}, status_code=400)

        full_name = f"{platform}_{name}"

        is_valid, error_msg = validate_strategy_name(full_name)
        if not is_valid:
            return JSONResponse({"status": "error", "message": error_msg}, status_code=400)

        is_intraday = strategy_type == "intraday"

        if is_intraday:
            is_valid, error_msg = validate_strategy_times(start_time, end_time, squareoff_time)
            if not is_valid:
                return JSONResponse({"status": "error", "message": error_msg}, status_code=400)
        else:
            start_time = end_time = squareoff_time = None

        webhook_id = str(uuid.uuid4())

        strategy = create_strategy(
            name=full_name, webhook_id=webhook_id, user_id=user_id, is_intraday=is_intraday,
            trading_mode=trading_mode, start_time=start_time, end_time=end_time,
            squareoff_time=squareoff_time, platform=platform,
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


@strategy_router.post("/api/strategy/{strategy_id}/toggle")
async def api_toggle_strategy(strategy_id: int, request: Request, session: dict = Depends(check_session_validity)):
    """API: Toggle strategy active status (JSON)"""
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


@strategy_router.post("/webhook/{webhook_id}")
@limiter.limit(WEBHOOK_RATE_LIMIT)
async def webhook(webhook_id: str, request: Request):
    """Handle webhook from trading platform"""
    try:
        strategy = get_strategy_by_webhook_id(webhook_id)
        if not strategy:
            return JSONResponse({"error": "Invalid webhook ID"}, status_code=404)

        if not strategy.is_active:
            return JSONResponse({"error": "Strategy is inactive"}, status_code=400)

        data = await request.json()
        if not data:
            return JSONResponse({"error": "No data received"}, status_code=400)

        # Check trading hours for intraday strategies
        if strategy.is_intraday:
            now = datetime.now(pytz.timezone("Asia/Kolkata"))
            current_time = now.strftime("%H:%M")

            action = data["action"].upper()
            position_size = int(data.get("position_size", 0))

            is_exit_order = False
            if strategy.trading_mode == "LONG":
                is_exit_order = action == "SELL"
            elif strategy.trading_mode == "SHORT":
                is_exit_order = action == "BUY"
            else:  # BOTH mode
                is_exit_order = position_size == 0

            if not is_exit_order:
                if strategy.start_time and current_time < strategy.start_time:
                    return JSONResponse({"error": "Entry orders not allowed before start time"}, status_code=400)
                if strategy.end_time and current_time > strategy.end_time:
                    return JSONResponse({"error": "Entry orders not allowed after end time"}, status_code=400)
            else:
                if strategy.start_time and current_time < strategy.start_time:
                    return JSONResponse({"error": "Exit orders not allowed before start time"}, status_code=400)
                if strategy.squareoff_time and current_time > strategy.squareoff_time:
                    return JSONResponse({"error": "Exit orders not allowed after square off time"}, status_code=400)

        # Validate required fields
        required_fields = ["symbol", "action"]
        if strategy.trading_mode == "BOTH":
            required_fields.append("position_size")

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return JSONResponse({"error": f"Missing required fields: {', '.join(missing_fields)}"}, status_code=400)

        action = data["action"].upper()
        position_size = int(data.get("position_size", 0))

        if strategy.trading_mode == "LONG":
            if action not in ["BUY", "SELL"]:
                return JSONResponse({"error": "Invalid action for LONG mode. Use BUY to enter, SELL to exit"}, status_code=400)
            use_smart_order = action == "SELL"
        elif strategy.trading_mode == "SHORT":
            if action not in ["BUY", "SELL"]:
                return JSONResponse({"error": "Invalid action for SHORT mode. Use SELL to enter, BUY to exit"}, status_code=400)
            use_smart_order = action == "BUY"
        else:  # BOTH mode
            if action not in ["BUY", "SELL"]:
                return JSONResponse({"error": "Invalid action. Use BUY or SELL"}, status_code=400)

            if action == "BUY" and position_size < 0:
                return JSONResponse({"error": "For BUY orders in BOTH mode, position_size must be >= 0"}, status_code=400)
            if action == "SELL" and position_size > 0:
                return JSONResponse({"error": "For SELL orders in BOTH mode, position_size must be <= 0"}, status_code=400)

            use_smart_order = position_size == 0

        # Get symbol mapping
        mapping = next((m for m in get_symbol_mappings(strategy.id) if m.symbol == data["symbol"]), None)
        if not mapping:
            return JSONResponse({"error": f"No mapping found for symbol {data['symbol']}"}, status_code=400)

        api_key = get_api_key_for_tradingview(strategy.user_id)
        if not api_key:
            logger.error(f"No API key found for user {strategy.user_id}")
            return JSONResponse({"error": "No API key found"}, status_code=401)

        payload = {
            "apikey": api_key, "symbol": mapping.symbol, "exchange": mapping.exchange,
            "product": mapping.product_type, "strategy": strategy.name, "action": action, "pricetype": "MARKET",
        }

        if strategy.trading_mode == "BOTH":
            quantity = "0" if position_size == 0 else str(mapping.quantity)
            payload.update({
                "quantity": quantity, "position_size": str(position_size),
                "price": "0", "trigger_price": "0", "disclosed_quantity": "0",
            })
            endpoint = "placesmartorder"
        else:
            if use_smart_order:
                payload.update({
                    "quantity": "0", "position_size": "0",
                    "price": "0", "trigger_price": "0", "disclosed_quantity": "0",
                })
                endpoint = "placesmartorder"
            else:
                quantity = abs(position_size) if position_size != 0 else mapping.quantity
                payload.update({"quantity": str(quantity)})
                endpoint = "placeorder"

        queue_order(endpoint, payload)
        return JSONResponse({"message": f"Order queued successfully for {data['symbol']}"}, status_code=200)

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return JSONResponse({"error": "Internal server error"}, status_code=500)
