# routers/settings.py
"""
FastAPI Settings Router for RealAlgo
Handles analyze mode settings.
Requirements: 4.7
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from database.settings_db import get_analyze_mode, set_analyze_mode
from dependencies_fastapi import check_session_validity
from sandbox.execution_thread import start_execution_engine, stop_execution_engine
from utils.logging import get_logger

logger = get_logger(__name__)

settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get("/analyze-mode")
async def get_mode(request: Request, session: dict = Depends(check_session_validity)):
    """Get current analyze mode setting."""
    try:
        return JSONResponse({"analyze_mode": get_analyze_mode()})
    except Exception as e:
        logger.error(f"Error getting analyze mode: {str(e)}")
        return JSONResponse({"error": "Failed to get analyze mode"}, status_code=500)


@settings_router.post("/analyze-mode/{mode}")
async def set_mode(mode: int, request: Request, session: dict = Depends(check_session_validity)):
    """Set analyze mode setting and manage execution engine thread."""
    try:
        set_analyze_mode(bool(mode))
        mode_name = "Analyze" if mode else "Live"

        if mode:
            success, message = start_execution_engine()
            if success:
                logger.info("Execution engine started for Analyze mode")
            else:
                logger.warning(f"Failed to start execution engine: {message}")
        else:
            success, message = stop_execution_engine()
            if success:
                logger.info("Execution engine stopped for Live mode")
            else:
                logger.warning(f"Failed to stop execution engine: {message}")

        return JSONResponse({
            "success": True,
            "analyze_mode": bool(mode),
            "message": f"Switched to {mode_name} Mode",
        })
    except Exception as e:
        logger.error(f"Error setting analyze mode: {str(e)}")
        return JSONResponse({"error": "Failed to set analyze mode"}, status_code=500)
