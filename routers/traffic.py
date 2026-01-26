# routers/traffic.py
"""
FastAPI Traffic Router for RealAlgo
Handles traffic monitoring dashboard and API.
Requirements: 4.7
"""

import csv
import io
from datetime import datetime

import pytz
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from database.traffic_db import TrafficLog, logs_session
from dependencies_fastapi import check_session_validity
from limiter_fastapi import limiter
from utils.logging import get_logger

logger = get_logger(__name__)

traffic_router = APIRouter(prefix="/traffic", tags=["traffic"])
templates = Jinja2Templates(directory="templates")


def convert_to_ist(timestamp):
    """Convert UTC timestamp to IST."""
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    utc = pytz.timezone("UTC")
    ist = pytz.timezone("Asia/Kolkata")
    if timestamp.tzinfo is None:
        timestamp = utc.localize(timestamp)
    return timestamp.astimezone(ist)


def format_ist_time(timestamp):
    """Format timestamp in IST with 12-hour format."""
    ist_time = convert_to_ist(timestamp)
    return ist_time.strftime("%d-%m-%Y %I:%M:%S %p")


def generate_csv(logs):
    """Generate CSV file from traffic logs."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Timestamp", "Client IP", "Method", "Path", "Status Code",
        "Duration (ms)", "Host", "Error",
    ])

    for log in logs:
        writer.writerow([
            format_ist_time(log.timestamp),
            log.client_ip,
            log.method,
            log.path,
            log.status_code,
            round(log.duration_ms, 2),
            log.host,
            log.error,
        ])

    return output.getvalue()


@traffic_router.get("/")
@limiter.limit("60/minute")
async def traffic_dashboard(request: Request, session: dict = Depends(check_session_validity)):
    """Display traffic monitoring dashboard."""
    stats = TrafficLog.get_stats()
    recent_logs = TrafficLog.get_recent_logs(limit=100)

    logs_data = [
        {
            "timestamp": format_ist_time(log.timestamp),
            "client_ip": log.client_ip,
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "duration_ms": round(log.duration_ms, 2),
            "host": log.host,
            "error": log.error,
        }
        for log in recent_logs
    ]
    return templates.TemplateResponse("traffic/dashboard.html", {
        "request": request, "stats": stats, "logs": logs_data
    })


@traffic_router.get("/api/logs")
@limiter.limit("60/minute")
async def get_logs(
    request: Request,
    limit: int = Query(100, le=1000),
    session: dict = Depends(check_session_validity)
):
    """API endpoint to get traffic logs."""
    try:
        logs = TrafficLog.get_recent_logs(limit=limit)
        return JSONResponse([
            {
                "timestamp": format_ist_time(log.timestamp),
                "client_ip": log.client_ip,
                "method": log.method,
                "path": log.path,
                "status_code": log.status_code,
                "duration_ms": round(log.duration_ms, 2),
                "host": log.host,
                "error": log.error,
            }
            for log in logs
        ])
    except Exception as e:
        logger.error(f"Error fetching traffic logs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@traffic_router.get("/api/stats")
@limiter.limit("60/minute")
async def get_stats(request: Request, session: dict = Depends(check_session_validity)):
    """API endpoint to get traffic statistics."""
    try:
        all_logs = TrafficLog.query
        overall_stats = {
            "total_requests": all_logs.count(),
            "error_requests": all_logs.filter(TrafficLog.status_code >= 400).count(),
            "avg_duration": round(
                float(all_logs.with_entities(func.avg(TrafficLog.duration_ms)).scalar() or 0), 2
            ),
        }

        api_logs = TrafficLog.query.filter(TrafficLog.path.like("/api/v1/%"))
        api_stats = {
            "total_requests": api_logs.count(),
            "error_requests": api_logs.filter(TrafficLog.status_code >= 400).count(),
            "avg_duration": round(
                float(api_logs.with_entities(func.avg(TrafficLog.duration_ms)).scalar() or 0), 2
            ),
        }

        endpoint_stats = {}
        for endpoint in [
            "placeorder", "placesmartorder", "modifyorder", "cancelorder", "quotes",
            "history", "depth", "intervals", "funds", "orderbook", "tradebook",
            "positionbook", "holdings", "basketorder", "splitorder", "orderstatus", "openposition",
        ]:
            path = f"/api/v1/{endpoint}"
            endpoint_logs = TrafficLog.query.filter(TrafficLog.path.like(f"{path}%"))
            endpoint_stats[endpoint] = {
                "total": endpoint_logs.count(),
                "errors": endpoint_logs.filter(TrafficLog.status_code >= 400).count(),
                "avg_duration": round(
                    float(endpoint_logs.with_entities(func.avg(TrafficLog.duration_ms)).scalar() or 0), 2
                ),
            }

        return JSONResponse({"overall": overall_stats, "api": api_stats, "endpoints": endpoint_stats})
    except Exception as e:
        logger.error(f"Error fetching traffic stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@traffic_router.get("/export")
@limiter.limit("10/minute")
async def export_logs(request: Request, session: dict = Depends(check_session_validity)):
    """Export traffic logs to CSV."""
    try:
        logs = TrafficLog.get_recent_logs(limit=None)
        csv_data = generate_csv(logs)

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=traffic_logs.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting traffic logs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)