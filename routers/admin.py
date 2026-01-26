# routers/admin.py
"""
FastAPI Admin Router for RealAlgo
Handles admin dashboard and system management.
Requirements: 4.7
"""

import os
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from database.market_calendar_db import (
    DEFAULT_MARKET_TIMINGS,
    SUPPORTED_EXCHANGES,
    Holiday,
    HolidayExchange,
    MarketTiming,
    clear_market_calendar_cache,
    get_all_market_timings,
    get_holidays_by_year,
    get_market_timings_for_date,
    update_market_timing,
)
from database.market_calendar_db import db_session as calendar_db_session
from database.qty_freeze_db import (
    QtyFreeze,
    get_all_freeze_qty,
    load_freeze_qty_cache,
    load_freeze_qty_from_csv,
)
from database.qty_freeze_db import db_session as freeze_db_session
from dependencies_fastapi import check_session_validity
from limiter_fastapi import limiter
from utils.logging import get_logger

logger = get_logger(__name__)

API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "50/second")

admin_router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# JSON API Endpoints for React Frontend
# ============================================================================


@admin_router.get("/api/stats")
@limiter.limit(API_RATE_LIMIT)
async def api_stats(request: Request, session: dict = Depends(check_session_validity)):
    """Get admin dashboard stats"""
    try:
        freeze_count = QtyFreeze.query.count()
        holiday_count = Holiday.query.count()
        return JSONResponse(
            {"status": "success", "freeze_count": freeze_count, "holiday_count": holiday_count}
        )
    except Exception as e:
        logger.error(f"Error fetching admin stats: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================================
# Freeze Quantity API Endpoints
# ============================================================================


@admin_router.get("/api/freeze")
@limiter.limit(API_RATE_LIMIT)
async def api_freeze_list(request: Request, session: dict = Depends(check_session_validity)):
    """Get all freeze quantities"""
    try:
        freeze_data = QtyFreeze.query.order_by(QtyFreeze.symbol).all()
        return JSONResponse({
            "status": "success",
            "data": [
                {"id": f.id, "exchange": f.exchange, "symbol": f.symbol, "freeze_qty": f.freeze_qty}
                for f in freeze_data
            ],
        })
    except Exception as e:
        logger.error(f"Error fetching freeze data: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.post("/api/freeze")
@limiter.limit(API_RATE_LIMIT)
async def api_freeze_add(request: Request, session: dict = Depends(check_session_validity)):
    """Add a new freeze quantity entry"""
    try:
        data = await request.json()
        exchange = data.get("exchange", "NFO").strip().upper()
        symbol = data.get("symbol", "").strip().upper()
        freeze_qty = data.get("freeze_qty")

        if not symbol or freeze_qty is None:
            return JSONResponse(
                {"status": "error", "message": "Symbol and freeze_qty are required"}, status_code=400
            )

        existing = QtyFreeze.query.filter_by(exchange=exchange, symbol=symbol).first()
        if existing:
            return JSONResponse(
                {"status": "error", "message": f"{symbol} already exists for {exchange}"}, status_code=400
            )

        entry = QtyFreeze(exchange=exchange, symbol=symbol, freeze_qty=int(freeze_qty))
        freeze_db_session.add(entry)
        freeze_db_session.commit()
        load_freeze_qty_cache()

        return JSONResponse({
            "status": "success",
            "message": f"Added freeze qty for {symbol}: {freeze_qty}",
            "data": {"id": entry.id, "exchange": entry.exchange, "symbol": entry.symbol, "freeze_qty": entry.freeze_qty},
        })
    except Exception as e:
        freeze_db_session.rollback()
        logger.error(f"Error adding freeze qty: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.put("/api/freeze/{id}")
@limiter.limit(API_RATE_LIMIT)
async def api_freeze_edit(id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Edit a freeze quantity entry"""
    try:
        entry = QtyFreeze.query.get(id)
        if not entry:
            return JSONResponse({"status": "error", "message": "Entry not found"}, status_code=404)

        data = await request.json()
        freeze_qty = data.get("freeze_qty")

        if freeze_qty is not None:
            entry.freeze_qty = int(freeze_qty)
            freeze_db_session.commit()
            load_freeze_qty_cache()

            return JSONResponse({
                "status": "success",
                "message": f"Updated freeze qty for {entry.symbol}: {freeze_qty}",
                "data": {"id": entry.id, "exchange": entry.exchange, "symbol": entry.symbol, "freeze_qty": entry.freeze_qty},
            })

        return JSONResponse({"status": "error", "message": "No freeze_qty provided"}, status_code=400)
    except Exception as e:
        freeze_db_session.rollback()
        logger.error(f"Error editing freeze qty: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.delete("/api/freeze/{id}")
@limiter.limit(API_RATE_LIMIT)
async def api_freeze_delete(id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Delete a freeze quantity entry"""
    try:
        entry = QtyFreeze.query.get(id)
        if not entry:
            return JSONResponse({"status": "error", "message": "Entry not found"}, status_code=404)

        symbol = entry.symbol
        freeze_db_session.delete(entry)
        freeze_db_session.commit()
        load_freeze_qty_cache()

        return JSONResponse({"status": "success", "message": f"Deleted freeze qty for {symbol}"})
    except Exception as e:
        freeze_db_session.rollback()
        logger.error(f"Error deleting freeze qty: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.post("/api/freeze/upload")
@limiter.limit("10/minute")
async def api_freeze_upload(
    request: Request,
    csv_file: UploadFile = File(...),
    exchange: str = Form(default="NFO"),
    session: dict = Depends(check_session_validity),
):
    """Upload CSV file to update freeze quantities"""
    try:
        if not csv_file.filename.endswith(".csv"):
            return JSONResponse({"status": "error", "message": "Please upload a CSV file"}, status_code=400)

        temp_path = "/tmp/qtyfreeze_upload.csv"
        content = await csv_file.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        exchange = exchange.strip().upper()
        result = load_freeze_qty_from_csv(temp_path, exchange)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        if result:
            count = QtyFreeze.query.filter_by(exchange=exchange).count()
            return JSONResponse({
                "status": "success",
                "message": f"Successfully loaded {count} freeze quantities for {exchange}",
                "count": count,
            })
        else:
            return JSONResponse({"status": "error", "message": "Error loading CSV file"}, status_code=500)

    except Exception as e:
        logger.error(f"Error uploading freeze qty CSV: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================================
# Holiday API Endpoints
# ============================================================================


@admin_router.get("/api/holidays")
@limiter.limit(API_RATE_LIMIT)
async def api_holidays_list(
    request: Request,
    year: int = Query(default=None),
    session: dict = Depends(check_session_validity),
):
    """Get holidays for a specific year"""
    try:
        current_year = datetime.now().year
        if year is None:
            year = current_year

        holidays_list = Holiday.query.filter(Holiday.year == year).order_by(Holiday.holiday_date).all()

        holidays_data = []
        for holiday in holidays_list:
            exchanges = HolidayExchange.query.filter(HolidayExchange.holiday_id == holiday.id).all()
            closed_exchanges = [ex.exchange_code for ex in exchanges if not ex.is_open]

            holidays_data.append({
                "id": holiday.id,
                "date": holiday.holiday_date.strftime("%Y-%m-%d"),
                "day_name": holiday.holiday_date.strftime("%A"),
                "description": holiday.description,
                "holiday_type": holiday.holiday_type,
                "closed_exchanges": closed_exchanges,
            })

        from sqlalchemy import func
        available_years = calendar_db_session.query(func.distinct(Holiday.year)).order_by(Holiday.year).all()
        years = [y[0] for y in available_years] if available_years else [current_year]

        if current_year not in years:
            years.append(current_year)
        if current_year + 1 not in years:
            years.append(current_year + 1)
        years = sorted(years)

        return JSONResponse({
            "status": "success",
            "data": holidays_data,
            "current_year": year,
            "years": years,
            "exchanges": SUPPORTED_EXCHANGES,
        })
    except Exception as e:
        logger.error(f"Error fetching holidays: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.post("/api/holidays")
@limiter.limit(API_RATE_LIMIT)
async def api_holiday_add(request: Request, session: dict = Depends(check_session_validity)):
    """Add a new holiday"""
    try:
        data = await request.json()
        date_str = data.get("date", "").strip()
        description = data.get("description", "").strip()
        holiday_type = data.get("holiday_type", "TRADING_HOLIDAY").strip()
        closed_exchanges = data.get("closed_exchanges", [])

        if not date_str or not description:
            return JSONResponse(
                {"status": "error", "message": "Date and description are required"}, status_code=400
            )

        holiday_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        year = holiday_date.year

        holiday = Holiday(
            holiday_date=holiday_date, description=description, holiday_type=holiday_type, year=year
        )
        calendar_db_session.add(holiday)
        calendar_db_session.flush()

        for exchange in closed_exchanges:
            exchange_entry = HolidayExchange(holiday_id=holiday.id, exchange_code=exchange, is_open=False)
            calendar_db_session.add(exchange_entry)

        calendar_db_session.commit()
        clear_market_calendar_cache()

        return JSONResponse({
            "status": "success",
            "message": f"Added holiday: {description} on {date_str}",
            "data": {
                "id": holiday.id,
                "date": date_str,
                "description": description,
                "holiday_type": holiday_type,
                "closed_exchanges": closed_exchanges,
            },
        })
    except Exception as e:
        calendar_db_session.rollback()
        logger.error(f"Error adding holiday: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.delete("/api/holidays/{id}")
@limiter.limit(API_RATE_LIMIT)
async def api_holiday_delete(id: int, request: Request, session: dict = Depends(check_session_validity)):
    """Delete a holiday"""
    try:
        holiday = Holiday.query.get(id)
        if not holiday:
            return JSONResponse({"status": "error", "message": "Holiday not found"}, status_code=404)

        description = holiday.description
        HolidayExchange.query.filter_by(holiday_id=id).delete()
        calendar_db_session.delete(holiday)
        calendar_db_session.commit()
        clear_market_calendar_cache()

        return JSONResponse({"status": "success", "message": f"Deleted holiday: {description}"})
    except Exception as e:
        calendar_db_session.rollback()
        logger.error(f"Error deleting holiday: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================================
# Market Timings API Endpoints
# ============================================================================


@admin_router.get("/api/timings")
@limiter.limit(API_RATE_LIMIT)
async def api_timings_list(request: Request, session: dict = Depends(check_session_validity)):
    """Get all market timings"""
    try:
        timings_data = get_all_market_timings()

        today = date.today()
        today_timings = get_market_timings_for_date(today)

        today_timings_formatted = []
        for t in today_timings:
            start_dt = datetime.fromtimestamp(t["start_time"] / 1000)
            end_dt = datetime.fromtimestamp(t["end_time"] / 1000)
            today_timings_formatted.append({
                "exchange": t["exchange"],
                "start_time": start_dt.strftime("%H:%M"),
                "end_time": end_dt.strftime("%H:%M"),
            })

        return JSONResponse({
            "status": "success",
            "data": timings_data,
            "today_timings": today_timings_formatted,
            "today": today.strftime("%Y-%m-%d"),
            "exchanges": SUPPORTED_EXCHANGES,
        })
    except Exception as e:
        logger.error(f"Error fetching timings: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.put("/api/timings/{exchange}")
@limiter.limit(API_RATE_LIMIT)
async def api_timings_edit(exchange: str, request: Request, session: dict = Depends(check_session_validity)):
    """Edit market timing for an exchange"""
    try:
        data = await request.json()
        start_time = data.get("start_time", "").strip()
        end_time = data.get("end_time", "").strip()

        if not start_time or not end_time:
            return JSONResponse(
                {"status": "error", "message": "Start time and end time are required"}, status_code=400
            )

        try:
            datetime.strptime(start_time, "%H:%M")
            datetime.strptime(end_time, "%H:%M")
        except ValueError:
            return JSONResponse(
                {"status": "error", "message": "Invalid time format. Use HH:MM"}, status_code=400
            )

        if update_market_timing(exchange, start_time, end_time):
            return JSONResponse({
                "status": "success",
                "message": f"Updated timing for {exchange}: {start_time} - {end_time}",
            })
        else:
            return JSONResponse(
                {"status": "error", "message": f"Error updating timing for {exchange}"}, status_code=500
            )

    except Exception as e:
        logger.error(f"Error editing timing: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@admin_router.post("/api/timings/check")
@limiter.limit(API_RATE_LIMIT)
async def api_timings_check(request: Request, session: dict = Depends(check_session_validity)):
    """Check market timings for a specific date"""
    try:
        data = await request.json()
        date_str = data.get("date", "").strip()

        if not date_str:
            return JSONResponse({"status": "error", "message": "Date is required"}, status_code=400)

        check_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        check_timings = get_market_timings_for_date(check_date)

        result_timings = []
        for t in check_timings:
            start_dt = datetime.fromtimestamp(t["start_time"] / 1000)
            end_dt = datetime.fromtimestamp(t["end_time"] / 1000)
            result_timings.append({
                "exchange": t["exchange"],
                "start_time": start_dt.strftime("%H:%M"),
                "end_time": end_dt.strftime("%H:%M"),
            })

        return JSONResponse({"status": "success", "date": date_str, "timings": result_timings})
    except Exception as e:
        logger.error(f"Error checking timings: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
