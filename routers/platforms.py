# routers/platforms.py
"""
FastAPI Platforms Router for RealAlgo
Handles trading platforms display route.
Requirements: 4.7
"""

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from dependencies_fastapi import check_session_validity
from utils.logging import get_logger

logger = get_logger(__name__)

platforms_router = APIRouter(prefix="/platforms", tags=["platforms"])
templates = Jinja2Templates(directory="templates")


@platforms_router.get("/")
async def index(request: Request, session: dict = Depends(check_session_validity)):
    """Display all trading platforms."""
    logger.info("Accessing platforms page")
    return templates.TemplateResponse("platforms.html", {"request": request})
