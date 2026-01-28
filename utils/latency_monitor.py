"""
Latency Monitoring for FastAPI

This module provides latency tracking for API endpoints.
It tracks request timing, broker API calls, and response processing.
"""

import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

from fastapi import Request

from database.auth_db import get_broker_name
from database.latency_db import OrderLatency, init_latency_db, latency_session, purge_old_data_logs
from utils.logging import get_logger

logger = get_logger(__name__)


class LatencyTracker:
    """Helper class to track latencies across different stages of order execution"""

    def __init__(self):
        self.start_time = time.time()
        self.stage_times = {}
        self.current_stage = None
        self.stage_start = None
        self.request_start = None
        self.request_end = None
        self.broker_api_time = None

    def start_stage(self, stage_name: str):
        """Start timing a new stage"""
        self.current_stage = stage_name
        self.stage_start = time.time()
        if stage_name == "broker_request":
            self.request_start = self.stage_start

    def end_stage(self):
        """End timing the current stage"""
        if self.current_stage and self.stage_start:
            current_time = time.time()
            duration = (current_time - self.stage_start) * 1000  # Convert to milliseconds
            self.stage_times[self.current_stage] = duration
            if self.current_stage == "broker_request":
                self.request_end = current_time
            self.current_stage = None
            self.stage_start = None

    def get_total_time(self) -> float:
        """Get total time since tracker was created"""
        return (time.time() - self.start_time) * 1000  # Convert to milliseconds

    def get_rtt(self) -> float:
        """Get round-trip time (comparable to Postman/Bruno)"""
        if self.request_start and self.request_end:
            return (self.request_end - self.request_start) * 1000
        return 0

    def get_overhead(self) -> float:
        """Get total overhead from our processing"""
        return self.stage_times.get("validation", 0) + self.stage_times.get("broker_response", 0)


def track_latency(api_type: str):
    """
    Decorator to track latency for FastAPI API endpoints.
    
    Args:
        api_type: Type of API endpoint (e.g., "PLACE", "QUOTES", etc.)
    """

    def decorator(f: Callable):
        @wraps(f)
        async def wrapped(request: Request, *args, **kwargs):
            # Initialize latency tracker
            tracker = LatencyTracker()
            
            # Store tracker in request state for access by other components
            request.state.latency_tracker = tracker
            endpoint_start_time = time.time()
            request.state.endpoint_start_time = endpoint_start_time

            try:
                # Start validation stage
                tracker.start_stage("validation")

                # Get request data for logging
                request_data = {}
                try:
                    if request.headers.get("content-type") == "application/json":
                        request_data = await request.json()
                except Exception:
                    pass

                # End validation stage after getting request data
                tracker.end_stage()

                # Start broker request stage
                tracker.start_stage("broker_request")

                # Execute the actual endpoint
                response = await f(request, *args, **kwargs)

                # End broker request stage
                tracker.end_stage()

                # Start response processing stage
                tracker.start_stage("broker_response")

                # Get response data
                response_data = {}
                status_code = 200
                
                if hasattr(response, "body"):
                    try:
                        import json
                        response_data = json.loads(response.body)
                    except Exception:
                        pass
                    status_code = response.status_code

                # End response processing stage
                tracker.end_stage()

                # Calculate latencies
                broker_api_time = getattr(request.state, "broker_api_time", None)

                if broker_api_time is not None:
                    current_time = time.time()
                    total_time = (current_time - endpoint_start_time) * 1000
                    rtt = broker_api_time
                    overhead = total_time - broker_api_time
                    total = total_time
                else:
                    rtt = tracker.get_rtt()
                    overhead = tracker.get_overhead()
                    total = rtt + overhead

                # Log the latency data
                order_id = response_data.get("orderid")
                if order_id is None:
                    order_id = response_data.get("request_id", "unknown")

                # Get broker name from auth_db using API key
                broker_name = None
                if "apikey" in request_data:
                    broker_name = get_broker_name(request_data["apikey"])

                # Get user_id from session if available
                user_id = None
                try:
                    user_id = request.session.get("user")
                except Exception:
                    pass

                OrderLatency.log_latency(
                    order_id=order_id,
                    user_id=user_id,
                    broker=broker_name,
                    symbol=request_data.get("symbol"),
                    order_type=api_type,
                    latencies={
                        "rtt": rtt,
                        "validation": tracker.stage_times.get("validation", 0),
                        "broker_response": tracker.stage_times.get("broker_response", 0),
                        "overhead": overhead,
                        "total": total,
                    },
                    request_body=None,
                    response_body=None,
                    status="SUCCESS" if status_code < 400 else "FAILED",
                    error=response_data.get("message") if status_code >= 400 else None,
                )

                return response

            except Exception as e:
                # Log error latency
                broker_api_time = getattr(request.state, "broker_api_time", None)

                if broker_api_time is not None:
                    current_time = time.time()
                    total_time = (current_time - endpoint_start_time) * 1000
                    rtt = broker_api_time
                    overhead = total_time - broker_api_time
                else:
                    total_time = tracker.get_total_time()
                    rtt = tracker.get_rtt()
                    overhead = tracker.get_overhead()

                broker_name = None
                if "request_data" in locals() and "apikey" in request_data:
                    broker_name = get_broker_name(request_data["apikey"])

                user_id = None
                try:
                    user_id = request.session.get("user")
                except Exception:
                    pass

                OrderLatency.log_latency(
                    order_id="error",
                    user_id=user_id,
                    broker=broker_name,
                    symbol=request_data.get("symbol") if "request_data" in locals() else None,
                    order_type=api_type,
                    latencies={
                        "rtt": rtt,
                        "validation": tracker.stage_times.get("validation", 0),
                        "broker_response": 0,
                        "overhead": overhead,
                        "total": total_time,
                    },
                    request_body=None,
                    response_body=None,
                    status="FAILED",
                    error=str(e),
                )
                raise

            finally:
                latency_session.remove()

        return wrapped

    return decorator


def init_latency_monitoring():
    """Initialize latency monitoring for FastAPI"""
    # Initialize the latency database
    init_latency_db()

    # Auto-purge old data endpoint logs (keep order logs forever, purge data logs after 7 days)
    purge_old_data_logs(days=7)
    
    logger.info("Latency monitoring initialized")
