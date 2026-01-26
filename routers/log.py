# routers/log.py
"""
FastAPI Log Router for RealAlgo
Handles API log viewing and export routes.
Requirements: 4.7
"""

import csv
import io
import json
import traceback
from datetime import datetime
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from database.apilog_db import OrderLog
from dependencies_fastapi import check_session_validity
from utils.logging import get_logger

logger = get_logger(__name__)

log_router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="templates")


def sanitize_request_data(data):
    """Remove sensitive information from request data."""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            sanitized = data.copy()
            sanitized.pop("apikey", None)
            return sanitized
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON: {data}")
        return {}
    except Exception as e:
        logger.error(f"Error sanitizing data: {str(e)}")
        return {}
    return data


def format_log_entry(log, ist):
    """Format a single log entry."""
    try:
        request_data = sanitize_request_data(log.request_data)
        try:
            response_data = json.loads(log.response_data) if log.response_data else {}
        except json.JSONDecodeError:
            logger.error(f"Error decoding response JSON for log {log.id}")
            response_data = {}
        except Exception as e:
            logger.error(f"Error processing response data for log {log.id}: {str(e)}")
            response_data = {}

        strategy = request_data.get("strategy", "Unknown") if isinstance(request_data, dict) else "Unknown"

        return {
            "id": log.id,
            "api_type": log.api_type,
            "request_data": request_data,
            "response_data": response_data,
            "strategy": strategy,
            "created_at": log.created_at.astimezone(ist).strftime("%Y-%m-%d %I:%M:%S %p"),
        }
    except Exception as e:
        logger.error(f"Error formatting log {log.id}: {str(e)}\n{traceback.format_exc()}")
        return {
            "id": log.id,
            "api_type": log.api_type,
            "request_data": {},
            "response_data": {},
            "strategy": "Unknown",
            "created_at": log.created_at.astimezone(ist).strftime("%Y-%m-%d %I:%M:%S %p"),
        }


def get_filtered_logs(start_date=None, end_date=None, search_query=None, page=None, per_page=None):
    """Get filtered logs with pagination."""
    ist = pytz.timezone("Asia/Kolkata")
    query = OrderLog.query

    try:
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(func.date(OrderLog.created_at) >= start_date)
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(func.date(OrderLog.created_at) <= end_date)

        if not start_date and not end_date:
            today_ist = datetime.now(ist).date()
            query = query.filter(func.date(OrderLog.created_at) == today_ist)

        if search_query:
            search = f"%{search_query}%"
            query = query.filter(
                (OrderLog.api_type.ilike(search))
                | (OrderLog.request_data.ilike(search))
                | (OrderLog.response_data.ilike(search))
            )

        total_logs = query.count()

        if page is not None and per_page is not None:
            total_pages = (total_logs + per_page - 1) // per_page
            query = query.order_by(OrderLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        else:
            total_pages = 1
            query = query.order_by(OrderLog.created_at.desc())

        logs = [format_log_entry(log, ist) for log in query.all()]
        logger.info(f"Retrieved {len(logs)} logs")

        return logs, total_pages, total_logs

    except Exception as e:
        logger.error(f"Error in get_filtered_logs: {str(e)}\n{traceback.format_exc()}")
        return [], 1, 0


def generate_csv(logs):
    """Generate CSV file from logs."""
    try:
        si = io.StringIO()
        writer = csv.writer(si)

        headers = [
            "ID", "Timestamp", "API Type", "Strategy", "Exchange", "Symbol", "Action",
            "Product", "Price Type", "Quantity", "Position Size", "Price", "Trigger Price",
            "Disclosed Quantity", "Order ID", "Response",
        ]
        writer.writerow(headers)

        for log in logs:
            try:
                request_data = log["request_data"]
                if not isinstance(request_data, dict):
                    request_data = {}

                response_data = log["response_data"]
                response_str = json.dumps(response_data) if isinstance(response_data, dict) else str(response_data)

                row = [
                    log["id"], log["created_at"], log["api_type"], log["strategy"],
                    request_data.get("exchange", ""), request_data.get("symbol", ""),
                    request_data.get("action", ""), request_data.get("product", ""),
                    request_data.get("pricetype", ""), request_data.get("quantity", ""),
                    request_data.get("position_size", ""), request_data.get("price", ""),
                    request_data.get("trigger_price", ""), request_data.get("disclosed_quantity", ""),
                    request_data.get("orderid", ""), response_str,
                ]
                writer.writerow(row)
            except Exception as e:
                logger.error(f"Error writing row for log {log.get('id')}: {str(e)}")
                continue

        return si.getvalue()

    except Exception as e:
        logger.error(f"Error generating CSV: {str(e)}\n{traceback.format_exc()}")
        raise


@log_router.get("/")
async def view_logs(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: str = Query(""),
    page: int = Query(1),
    session: dict = Depends(check_session_validity)
):
    """View logs page."""
    try:
        search_query = search.strip()
        per_page = 20

        logs, total_pages, _ = get_filtered_logs(
            start_date=start_date,
            end_date=end_date,
            search_query=search_query,
            page=page,
            per_page=per_page,
        )

        # If AJAX request, return JSON
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"logs": logs, "total_pages": total_pages, "current_page": page})

        logger.info(f"Found {len(logs)} log entries")
        return templates.TemplateResponse("logs.html", {
            "request": request,
            "logs": logs,
            "total_pages": total_pages,
            "current_page": page,
            "search_query": search_query,
            "start_date": start_date,
            "end_date": end_date,
        })

    except Exception as e:
        logger.error(f"Error in view_logs: {str(e)}\n{traceback.format_exc()}")
        return templates.TemplateResponse("logs.html", {
            "request": request,
            "logs": [],
            "total_pages": 1,
            "current_page": 1,
            "search_query": "",
            "start_date": None,
            "end_date": None,
        })


@log_router.get("/export")
async def export_logs(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: str = Query(""),
    session: dict = Depends(check_session_validity)
):
    """Export logs as CSV."""
    try:
        logger.info("Starting log export")
        search_query = search.strip()

        logger.info(f"Export parameters - start_date: {start_date}, end_date: {end_date}, search: {search_query}")

        logs, _, total = get_filtered_logs(
            start_date=start_date,
            end_date=end_date,
            search_query=search_query,
            page=None,
            per_page=None,
        )

        logger.info(f"Retrieved {total} logs for export")

        csv_output = generate_csv(logs)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"realalgo_logs_{timestamp}.csv"

        logger.info(f"Generated CSV file: {filename}")

        return Response(
            content=csv_output,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv",
            },
        )

    except Exception as e:
        error_msg = f"Error exporting logs: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return JSONResponse({"error": error_msg}, status_code=500)
