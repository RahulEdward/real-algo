# routers/logging.py
"""
FastAPI Logging Router for RealAlgo
Handles consolidated logging dashboard.
Requirements: 4.7
"""

import os

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from dependencies_fastapi import check_session_validity
from limiter_fastapi import limiter

logging_router = APIRouter(prefix="/logging", tags=["logging"])
templates = Jinja2Templates(directory="templates")

API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "50/second")


@logging_router.get("/")
@limiter.limit("60/minute")
async def logging_dashboard(request: Request, session: dict = Depends(check_session_validity)):
    """
    Consolidated logging dashboard page.
    Provides access to all logging and monitoring sections:
    - Live Logs
    - Analyzer Logs
    - Traffic Monitor
    - Latency Monitor
    - Security Logs
    """
    return templates.TemplateResponse("logging.html", {"request": request})
