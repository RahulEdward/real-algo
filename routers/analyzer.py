# routers/analyzer.py
"""
FastAPI Analyzer Router for RealAlgo
Handles API analyzer dashboard and data.
Requirements: 4.7
"""

import csv
import io
import json
import traceback
from datetime import datetime, timedelta
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func

from database.analyzer_db import AnalyzerLog, db_session
from dependencies_fastapi import check_session_validity
from utils.api_analyzer import get_analyzer_stats
from utils.logging import get_logger

logger = get_logger(__name__)

analyzer_router = APIRouter(prefix="/analyzer", tags=["analyzer"])
templates = Jinja2Templates(directory="templates")


def format_request(req, ist):
    """Format a single request entry."""
    try:
        request_data = json.loads(req.request_data) if isinstance(req.request_data, str) else req.request_data
        response_data = json.loads(req.response_data) if isinstance(req.response_data, str) else req.response_data

        formatted_request = {
            "timestamp": req.created_at.astimezone(ist).strftime("%Y-%m-%d %H:%M:%S"),
            "api_type": req.api_type,
            "source": request_data.get("strategy", "Unknown"),
            "request_data": request_data,
            "response_data": response_data,
            "analysis": {
                "issues": response_data.get("status") == "error",
                "error": response_data.get("message"),
                "error_type": "error" if response_data.get("status") == "error" else "success",
                "warnings": response_data.get("warnings", []),
            },
        }

        if req.api_type in ["placeorder", "placesmartorder"]:
            formatted_request.update({
                "symbol": request_data.get("symbol", "Unknown"),
                "exchange": request_data.get("exchange", "Unknown"),
                "action": request_data.get("action", "Unknown"),
                "quantity": request_data.get("quantity", 0),
                "price_type": request_data.get("pricetype", "Unknown"),
                "product_type": request_data.get("product", "Unknown"),
            })
            if req.api_type == "placesmartorder":
                formatted_request["position_size"] = request_data.get("position_size", 0)
        elif req.api_type == "cancelorder":
            formatted_request.update({"orderid": request_data.get("orderid", "Unknown")})

        return formatted_request
    except Exception as e:
        logger.error(f"Error formatting request {req.id}: {str(e)}")
        return None


def get_recent_requests():
    """Get recent analyzer requests."""
    try:
        ist = pytz.timezone("Asia/Kolkata")
        recent = AnalyzerLog.query.order_by(AnalyzerLog.created_at.desc()).limit(100).all()
        requests = []

        for req in recent:
            formatted = format_request(req, ist)
            if formatted:
                requests.append(formatted)

        return requests
    except Exception as e:
        logger.error(f"Error getting recent requests: {str(e)}")
        return []


def get_filtered_requests(start_date=None, end_date=None):
    """Get analyzer requests with date filtering."""
    try:
        ist = pytz.timezone("Asia/Kolkata")
        query = AnalyzerLog.query

        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(func.date(AnalyzerLog.created_at) >= start_date)
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(func.date(AnalyzerLog.created_at) <= end_date)

        if not start_date and not end_date:
            today_ist = datetime.now(ist).date()
            query = query.filter(func.date(AnalyzerLog.created_at) == today_ist)

        results = query.order_by(AnalyzerLog.created_at.desc()).all()
        requests = []

        for req in results:
            formatted = format_request(req, ist)
            if formatted:
                requests.append(formatted)

        return requests
    except Exception as e:
        logger.error(f"Error getting filtered requests: {str(e)}\n{traceback.format_exc()}")
        return []


def generate_csv(requests):
    """Generate CSV from analyzer requests."""
    try:
        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Timestamp", "API Type", "Source", "Symbol", "Exchange", "Action",
            "Quantity", "Price Type", "Product Type", "Status", "Error Message",
        ]
        writer.writerow(headers)

        for req in requests:
            row = [
                req["timestamp"], req["api_type"], req["source"],
                req.get("symbol", ""), req.get("exchange", ""), req.get("action", ""),
                req.get("quantity", ""), req.get("price_type", ""), req.get("product_type", ""),
                "Error" if req["analysis"]["issues"] else "Success",
                req["analysis"].get("error", ""),
            ]
            writer.writerow(row)

        return output.getvalue()
    except Exception as e:
        logger.error(f"Error generating CSV: {str(e)}\n{traceback.format_exc()}")
        return ""


def get_default_stats():
    """Return default stats structure."""
    return {
        "total_requests": 0,
        "sources": {},
        "symbols": [],
        "issues": {
            "total": 0,
            "by_type": {
                "rate_limit": 0,
                "invalid_symbol": 0,
                "missing_quantity": 0,
                "invalid_exchange": 0,
                "other": 0,
            },
        },
    }


@analyzer_router.get("/")
async def analyzer(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session: dict = Depends(check_session_validity)
):
    """Render the analyzer dashboard."""
    try:
        stats = get_analyzer_stats()
        if not isinstance(stats, dict):
            stats = get_default_stats()

        requests_data = get_filtered_requests(start_date, end_date)

        return templates.TemplateResponse("analyzer.html", {
            "request": request,
            "requests": requests_data,
            "stats": stats,
            "start_date": start_date,
            "end_date": end_date,
        })
    except Exception as e:
        logger.error(f"Error rendering analyzer: {str(e)}\n{traceback.format_exc()}")
        return RedirectResponse(url="/", status_code=302)


@analyzer_router.get("/api/data")
async def api_get_data(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session: dict = Depends(check_session_validity)
):
    """API endpoint to get analyzer data as JSON for React frontend."""
    try:
        stats = get_analyzer_stats()
        if not isinstance(stats, dict):
            stats = get_default_stats()

        requests_data = get_filtered_requests(start_date, end_date)

        stats_transformed = {
            "total_requests": stats.get("total_requests", 0),
            "issues": stats.get("issues", {"total": 0}),
            "symbols": list(stats.get("symbols", [])) if isinstance(stats.get("symbols"), (list, set)) else [],
            "sources": list(stats.get("sources", {}).keys()) if isinstance(stats.get("sources"), dict) else [],
        }

        return JSONResponse({"status": "success", "data": {"stats": stats_transformed, "requests": requests_data}})
    except Exception as e:
        logger.error(f"Error getting analyzer data: {str(e)}\n{traceback.format_exc()}")
        return JSONResponse({"status": "error", "message": f"Error loading analyzer data: {str(e)}"}, status_code=500)


@analyzer_router.get("/stats")
async def get_stats(request: Request, session: dict = Depends(check_session_validity)):
    """Get analyzer stats endpoint."""
    try:
        stats = get_analyzer_stats()
        return JSONResponse(stats)
    except Exception as e:
        logger.error(f"Error getting analyzer stats: {str(e)}")
        return JSONResponse(get_default_stats(), status_code=500)


@analyzer_router.get("/requests")
async def get_requests(request: Request, session: dict = Depends(check_session_validity)):
    """Get analyzer requests endpoint."""
    try:
        requests_data = get_recent_requests()
        return JSONResponse({"requests": requests_data})
    except Exception as e:
        logger.error(f"Error getting analyzer requests: {str(e)}")
        return JSONResponse({"requests": []}, status_code=500)


@analyzer_router.get("/clear")
async def clear_logs(request: Request, session: dict = Depends(check_session_validity)):
    """Clear analyzer logs."""
    try:
        cutoff = datetime.now(pytz.UTC) - timedelta(hours=24)
        AnalyzerLog.query.filter(AnalyzerLog.created_at < cutoff).delete()
        db_session.commit()
        return RedirectResponse(url="/analyzer", status_code=302)
    except Exception as e:
        logger.error(f"Error clearing analyzer logs: {str(e)}")
        return RedirectResponse(url="/analyzer", status_code=302)


@analyzer_router.get("/export")
async def export_requests(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    session: dict = Depends(check_session_validity)
):
    """Export analyzer requests to CSV."""
    try:
        requests_data = get_filtered_requests(start_date, end_date)
        csv_data = generate_csv(requests_data)

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=analyzer_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting requests: {str(e)}\n{traceback.format_exc()}")
        return RedirectResponse(url="/analyzer", status_code=302)
