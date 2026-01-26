# routers/latency.py
"""
FastAPI Latency Router for RealAlgo
Handles latency monitoring dashboard and API endpoints.
Requirements: 4.7
"""

import csv
import io
from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np
import pytz
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from database.latency_db import OrderLatency, latency_session
from dependencies_fastapi import check_session_validity
from limiter_fastapi import limiter
from utils.logging import get_logger

logger = get_logger(__name__)

latency_router = APIRouter(prefix="/latency", tags=["latency"])
templates = Jinja2Templates(directory="templates")


def convert_to_ist(timestamp):
    """Convert UTC timestamp to IST"""
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    utc = pytz.timezone("UTC")
    ist = pytz.timezone("Asia/Kolkata")
    if timestamp.tzinfo is None:
        timestamp = utc.localize(timestamp)
    return timestamp.astimezone(ist)


def format_ist_time(timestamp):
    """Format timestamp in IST with 12-hour format"""
    ist_time = convert_to_ist(timestamp)
    return ist_time.strftime("%d-%m-%Y %I:%M:%S %p")


def get_histogram_data(broker=None):
    """Get histogram data for RTT distribution"""
    try:
        query = OrderLatency.query
        if broker:
            query = query.filter_by(broker=broker)

        rtts = [r[0] for r in query.with_entities(OrderLatency.rtt_ms).all()]

        if not rtts:
            return {"bins": [], "counts": [], "avg_rtt": 0, "min_rtt": 0, "max_rtt": 0}

        avg_rtt = sum(rtts) / len(rtts)
        min_rtt = min(rtts)
        max_rtt = max(rtts)

        bin_count = 30
        bin_width = (max_rtt - min_rtt) / bin_count if max_rtt > min_rtt else 1

        counts, bins = np.histogram(rtts, bins=bin_count, range=(min_rtt, max_rtt))
        counts = counts.tolist()
        bins = bins.tolist()
        bin_labels = [f"{bins[i]:.1f}" for i in range(len(bins) - 1)]

        return {
            "bins": bin_labels,
            "counts": counts,
            "avg_rtt": float(avg_rtt),
            "min_rtt": float(min_rtt),
            "max_rtt": float(max_rtt),
        }

    except Exception as e:
        logger.error(f"Error getting histogram data: {e}")
        return {"bins": [], "counts": [], "avg_rtt": 0, "min_rtt": 0, "max_rtt": 0}


def generate_csv(logs):
    """Generate CSV file from latency logs with trader-friendly column names"""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date & Time (IST)", "Broker", "Order ID", "Symbol", "Order Type",
        "Broker Confirmation (ms)", "Platform Overhead (ms)", "Total Latency (ms)",
        "Status", "Error (if any)",
    ])

    for log in logs:
        writer.writerow([
            format_ist_time(log.timestamp),
            log.broker or "N/A",
            log.order_id,
            log.symbol or "N/A",
            log.order_type,
            round(log.rtt_ms, 2),
            round(log.overhead_ms, 2),
            round(log.total_latency_ms, 2),
            log.status,
            log.error or "",
        ])

    return output.getvalue()


@latency_router.get("/")
@limiter.limit("60/minute")
async def latency_dashboard(request: Request, session: dict = Depends(check_session_validity)):
    """Display latency monitoring dashboard"""
    stats = OrderLatency.get_latency_stats()
    recent_logs = OrderLatency.get_recent_logs(limit=100)

    broker_histograms = {}
    brokers = [b[0] for b in OrderLatency.query.with_entities(OrderLatency.broker).distinct().all()]
    for broker in brokers:
        if broker:
            broker_histograms[broker] = get_histogram_data(broker)

    logs_json = []
    for log in recent_logs:
        log.formatted_timestamp = format_ist_time(log.timestamp)
        logs_json.append({
            "id": log.id,
            "order_id": log.order_id,
            "broker": log.broker,
            "symbol": log.symbol,
            "order_type": log.order_type,
            "rtt_ms": log.rtt_ms,
            "validation_latency_ms": log.validation_latency_ms,
            "response_latency_ms": log.response_latency_ms,
            "overhead_ms": log.overhead_ms,
            "total_latency_ms": log.total_latency_ms,
            "status": log.status,
            "error": log.error,
            "timestamp": convert_to_ist(log.timestamp).isoformat(),
        })

    return templates.TemplateResponse("latency/dashboard.html", {
        "request": request,
        "stats": stats,
        "logs": recent_logs,
        "logs_json": logs_json,
        "broker_histograms": broker_histograms,
    })


@latency_router.get("/api/logs")
@limiter.limit("60/minute")
async def get_logs(request: Request, limit: int = Query(100, le=1000), session: dict = Depends(check_session_validity)):
    """API endpoint to get latency logs"""
    try:
        logs = OrderLatency.get_recent_logs(limit=limit)
        return JSONResponse([
            {
                "timestamp": convert_to_ist(log.timestamp).isoformat(),
                "id": log.id,
                "order_id": log.order_id,
                "broker": log.broker,
                "symbol": log.symbol,
                "order_type": log.order_type,
                "rtt_ms": log.rtt_ms,
                "validation_latency_ms": log.validation_latency_ms,
                "response_latency_ms": log.response_latency_ms,
                "overhead_ms": log.overhead_ms,
                "total_latency_ms": log.total_latency_ms,
                "status": log.status,
                "error": log.error,
            }
            for log in logs
        ])
    except Exception as e:
        logger.error(f"Error fetching latency logs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@latency_router.get("/api/stats")
@limiter.limit("60/minute")
async def get_stats(request: Request, session: dict = Depends(check_session_validity)):
    """API endpoint to get latency statistics"""
    try:
        stats = OrderLatency.get_latency_stats()

        broker_histograms = {}
        for broker in stats.get("broker_stats", {}):
            broker_histograms[broker] = get_histogram_data(broker)

        stats["broker_histograms"] = broker_histograms
        return JSONResponse(stats)
    except Exception as e:
        logger.error(f"Error fetching latency stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@latency_router.get("/api/broker/{broker}/stats")
@limiter.limit("60/minute")
async def get_broker_stats(broker: str, request: Request, session: dict = Depends(check_session_validity)):
    """API endpoint to get broker-specific latency statistics"""
    try:
        stats = OrderLatency.get_latency_stats()
        broker_stats = stats.get("broker_stats", {}).get(broker, {})
        if not broker_stats:
            return JSONResponse({"error": "Broker not found"}, status_code=404)

        broker_stats["histogram"] = get_histogram_data(broker)
        return JSONResponse(broker_stats)
    except Exception as e:
        logger.error(f"Error fetching broker stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@latency_router.get("/export")
@limiter.limit("10/minute")
async def export_logs(request: Request, session: dict = Depends(check_session_validity)):
    """Export latency logs to CSV"""
    try:
        logs = OrderLatency.get_recent_logs(limit=None)
        csv_data = generate_csv(logs)

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=latency_logs.csv"},
        )

    except Exception as e:
        logger.error(f"Error exporting latency logs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
