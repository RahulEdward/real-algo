# routers/master_contract_status.py
"""
FastAPI Master Contract Status Router for RealAlgo
Handles master contract download status and cache management.
Requirements: 4.7
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from database.master_contract_status_db import check_if_ready, get_status
from dependencies_fastapi import check_session_validity, get_session
from utils.logging import get_logger

logger = get_logger(__name__)

master_contract_status_router = APIRouter(prefix="/api", tags=["master_contract_status"])


@master_contract_status_router.get("/master-contract/status")
async def get_master_contract_status(request: Request, session: dict = Depends(check_session_validity)):
    """Get the current master contract download status"""
    try:
        broker = session.get("broker")
        if not broker:
            return JSONResponse({"status": "error", "message": "No broker session found"}, status_code=401)

        status_data = get_status(broker)
        return JSONResponse(status_data, status_code=200)

    except Exception as e:
        logger.error(f"Error getting master contract status: {str(e)}")
        return JSONResponse({"status": "error", "message": "Failed to get master contract status"}, status_code=500)


@master_contract_status_router.get("/master-contract/ready")
async def check_master_contract_ready(request: Request, session: dict = Depends(check_session_validity)):
    """Check if master contracts are ready for trading"""
    try:
        broker = session.get("broker")
        if not broker:
            return JSONResponse({"ready": False, "message": "No broker session found"}, status_code=401)

        is_ready = check_if_ready(broker)
        return JSONResponse({
            "ready": is_ready,
            "message": "Master contracts are ready" if is_ready else "Master contracts not ready",
        }, status_code=200)

    except Exception as e:
        logger.error(f"Error checking master contract readiness: {str(e)}")
        return JSONResponse({"ready": False, "message": "Failed to check master contract readiness"}, status_code=500)


@master_contract_status_router.get("/cache/status")
async def get_cache_status(request: Request, session: dict = Depends(check_session_validity)):
    """Get the current symbol cache status and statistics"""
    try:
        from database.token_db_enhanced import get_cache_stats

        cache_info = get_cache_stats()
        return JSONResponse(cache_info, status_code=200)

    except ImportError:
        return JSONResponse({"status": "not_available", "message": "Enhanced cache module not available"}, status_code=200)
    except Exception as e:
        logger.error(f"Error getting cache status: {str(e)}")
        return JSONResponse({"status": "error", "message": f"Failed to get cache status: {str(e)}"}, status_code=500)


@master_contract_status_router.get("/cache/health")
async def get_cache_health(request: Request, session: dict = Depends(check_session_validity)):
    """Get cache health metrics and recommendations"""
    try:
        from database.master_contract_cache_hook import get_cache_health

        health_info = get_cache_health()
        return JSONResponse(health_info, status_code=200)

    except ImportError:
        return JSONResponse({
            "health_score": 0,
            "status": "not_available",
            "message": "Cache health monitoring not available",
        }, status_code=200)
    except Exception as e:
        logger.error(f"Error getting cache health: {str(e)}")
        return JSONResponse({
            "health_score": 0,
            "status": "error",
            "message": f"Failed to get cache health: {str(e)}",
        }, status_code=500)


@master_contract_status_router.post("/cache/reload")
async def reload_cache(request: Request, session: dict = Depends(check_session_validity)):
    """Manually trigger cache reload"""
    try:
        broker = session.get("broker")
        if not broker:
            return JSONResponse({"status": "error", "message": "No broker session found"}, status_code=401)

        from database.master_contract_cache_hook import load_symbols_to_cache

        success = load_symbols_to_cache(broker)

        if success:
            return JSONResponse({
                "status": "success",
                "message": f"Cache reloaded successfully for broker: {broker}",
            }, status_code=200)
        else:
            return JSONResponse({"status": "error", "message": "Failed to reload cache"}, status_code=500)

    except ImportError:
        return JSONResponse({"status": "error", "message": "Cache reload functionality not available"}, status_code=501)
    except Exception as e:
        logger.error(f"Error reloading cache: {str(e)}")
        return JSONResponse({"status": "error", "message": f"Failed to reload cache: {str(e)}"}, status_code=500)


@master_contract_status_router.post("/cache/clear")
async def clear_cache(request: Request, session: dict = Depends(check_session_validity)):
    """Manually clear the cache"""
    try:
        from database.token_db_enhanced import clear_cache as clear_symbol_cache

        clear_symbol_cache()

        return JSONResponse({"status": "success", "message": "Cache cleared successfully"}, status_code=200)

    except ImportError:
        return JSONResponse({"status": "error", "message": "Cache clear functionality not available"}, status_code=501)
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return JSONResponse({"status": "error", "message": f"Failed to clear cache: {str(e)}"}, status_code=500)
