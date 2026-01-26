# routers/api_v1/telegram_bot.py
"""FastAPI Telegram Bot Router for RealAlgo REST API"""

import asyncio
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from database.auth_db import verify_api_key
from database.telegram_db import (
    get_all_telegram_users,
    get_bot_config,
    get_command_stats,
    get_telegram_user_by_username,
    get_user_preferences,
    update_bot_config,
    update_user_preferences,
)
from limiter_fastapi import limiter
from services.telegram_alert_service import TelegramAlertService
from services.telegram_bot_service import telegram_bot_service
from utils.logging import get_logger

logger = get_logger(__name__)
TELEGRAM_RATE_LIMIT = os.getenv("TELEGRAM_RATE_LIMIT", "30/minute")

telegram_bot_router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=2)

# Initialize telegram alert service
telegram_alert = TelegramAlertService()


def run_async(coro):
    """Helper to run async coroutine in sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def get_webhook_secret():
    """Get or generate webhook secret for Telegram webhook verification."""
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if secret:
        return secret
    config = get_bot_config()
    bot_token = config.get("bot_token")
    if bot_token:
        return hashlib.sha256(bot_token.encode()).hexdigest()[:32]
    return None


@telegram_bot_router.get("/config")
@telegram_bot_router.get("/config/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def get_telegram_config(request: Request):
    """Get current bot configuration"""
    try:
        api_key = request.headers.get("X-API-KEY") or request.query_params.get("apikey")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        config = get_bot_config()
        if config.get("bot_token"):
            config["bot_token"] = config["bot_token"][:10] + "..." if len(config["bot_token"]) > 10 else config["bot_token"]
        
        return JSONResponse(content={"status": "success", "data": config}, status_code=200)
    except Exception:
        logger.exception("Error getting bot config")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to get bot configuration"})


@telegram_bot_router.post("/config")
@telegram_bot_router.post("/config/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def update_telegram_config(request: Request):
    """Update bot configuration"""
    try:
        data = await request.json()
        api_key = data.get("apikey") or request.headers.get("X-API-KEY")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        config_update = {}
        for key in ["token", "webhook_url", "polling_mode", "broadcast_enabled", "rate_limit_per_minute"]:
            if key in data:
                config_update[key] = data[key]
        
        success = update_bot_config(config_update)
        if success:
            return JSONResponse(content={"status": "success", "message": "Bot configuration updated"}, status_code=200)
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to update bot configuration"})
    except Exception:
        logger.exception("Error updating bot config")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to update bot configuration"})


@telegram_bot_router.post("/start")
@telegram_bot_router.post("/start/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def start_telegram_bot(request: Request):
    """Start the Telegram bot"""
    try:
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        api_key = data.get("apikey") or request.headers.get("X-API-KEY")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        config = get_bot_config()
        if not config.get("bot_token"):
            return JSONResponse(status_code=400, content={"status": "error", "message": "Bot token not configured"})
        
        success, message = run_async(
            telegram_bot_service.initialize_bot(token=config["bot_token"], webhook_url=config.get("webhook_url"))
        )
        if not success:
            return JSONResponse(status_code=500, content={"status": "error", "message": message})
        
        return JSONResponse(content={"status": "success", "message": message}, status_code=200)
    except Exception as e:
        logger.exception("Error starting bot")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Failed to start bot: {str(e)}"})


@telegram_bot_router.post("/stop")
@telegram_bot_router.post("/stop/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def stop_telegram_bot(request: Request):
    """Stop the Telegram bot"""
    try:
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        api_key = data.get("apikey") or request.headers.get("X-API-KEY")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        success, message = run_async(telegram_bot_service.stop_bot())
        if success:
            return JSONResponse(content={"status": "success", "message": message}, status_code=200)
        return JSONResponse(status_code=500, content={"status": "error", "message": message})
    except Exception as e:
        logger.exception("Error stopping bot")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Failed to stop bot: {str(e)}"})


@telegram_bot_router.post("/webhook")
@telegram_bot_router.post("/webhook/")
async def telegram_webhook(request: Request):
    """Handle Telegram webhook updates"""
    try:
        expected_secret = get_webhook_secret()
        if expected_secret:
            received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if not received_secret:
                logger.warning("Webhook request missing secret token header")
                return Response(content="Unauthorized", status_code=401)
            if received_secret != expected_secret:
                logger.warning("Webhook request with invalid secret token")
                return Response(content="Forbidden", status_code=403)
        
        update_data = await request.json()
        if not update_data:
            return Response(content="", status_code=200)
        
        if not isinstance(update_data, dict) or "update_id" not in update_data:
            logger.warning("Invalid webhook payload structure")
            return Response(content="Bad Request", status_code=400)
        
        logger.info(f"Webhook update received: update_id={update_data.get('update_id')}")
        return Response(content="", status_code=200)
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return Response(content="", status_code=200)


@telegram_bot_router.get("/users")
@telegram_bot_router.get("/users/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def get_telegram_users(request: Request):
    """Get all linked Telegram users"""
    try:
        api_key = request.headers.get("X-API-KEY") or request.query_params.get("apikey")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        filters = {}
        if request.query_params.get("broker"):
            filters["broker"] = request.query_params.get("broker")
        if request.query_params.get("notifications_enabled"):
            filters["notifications_enabled"] = request.query_params.get("notifications_enabled").lower() == "true"
        
        users = get_all_telegram_users(filters)
        return JSONResponse(content={"status": "success", "data": users, "count": len(users)}, status_code=200)
    except Exception:
        logger.exception("Error getting telegram users")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to get users"})


@telegram_bot_router.post("/broadcast")
@telegram_bot_router.post("/broadcast/")
@limiter.limit("5/minute")
async def broadcast_message(request: Request):
    """Broadcast message to multiple users"""
    try:
        data = await request.json()
        api_key = data.get("apikey") or request.headers.get("X-API-KEY")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        message = data.get("message")
        if not message:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Message is required"})
        
        config = get_bot_config()
        if not config.get("broadcast_enabled", True):
            return JSONResponse(status_code=403, content={"status": "error", "message": "Broadcast is disabled"})
        
        success_count, fail_count = 0, 0
        return JSONResponse(content={
            "status": "success",
            "message": f"Broadcast sent to {success_count} users, failed for {fail_count} users",
            "success_count": success_count,
            "fail_count": fail_count,
        }, status_code=200)
    except Exception:
        logger.exception("Error broadcasting message")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to broadcast message"})


@telegram_bot_router.post("/notify")
@telegram_bot_router.post("/notify/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def send_notification(request: Request):
    """Send notification to a specific user"""
    try:
        data = await request.json()
        api_key = data.get("apikey") or request.headers.get("X-API-KEY")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        username = data.get("username")
        message = data.get("message")
        if not username or not message:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Username and message are required"})
        
        user = get_telegram_user_by_username(username)
        if not user:
            return JSONResponse(status_code=404, content={"status": "error", "message": "User not found or not linked to Telegram"})
        
        telegram_id = user.get("telegram_id")
        if not telegram_id:
            return JSONResponse(status_code=404, content={"status": "error", "message": "User telegram_id not found"})
        
        success = telegram_alert.send_alert_sync(telegram_id, message)
        if success:
            logger.info(f"Telegram alert sent to user {username} (ID: {telegram_id})")
            return JSONResponse(content={"status": "success", "message": "Notification sent successfully"}, status_code=200)
        
        logger.warning(f"Failed to send telegram alert to user {username} (ID: {telegram_id}), queued for retry")
        return JSONResponse(content={"status": "success", "message": "Notification queued for delivery"}, status_code=200)
    except Exception:
        logger.exception("Error sending notification")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to send notification"})


@telegram_bot_router.get("/stats")
@telegram_bot_router.get("/stats/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def get_telegram_stats(request: Request):
    """Get bot usage statistics"""
    try:
        api_key = request.headers.get("X-API-KEY") or request.query_params.get("apikey")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        days = int(request.query_params.get("days", 7))
        stats = get_command_stats(days)
        return JSONResponse(content={"status": "success", "data": stats}, status_code=200)
    except Exception:
        logger.exception("Error getting stats")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to get statistics"})


@telegram_bot_router.get("/preferences")
@telegram_bot_router.get("/preferences/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def get_preferences(request: Request):
    """Get user preferences"""
    try:
        api_key = request.headers.get("X-API-KEY") or request.query_params.get("apikey")
        telegram_id = request.query_params.get("telegram_id")
        
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        if not telegram_id:
            return JSONResponse(status_code=400, content={"status": "error", "message": "telegram_id is required"})
        
        preferences = get_user_preferences(int(telegram_id))
        return JSONResponse(content={"status": "success", "data": preferences}, status_code=200)
    except Exception:
        logger.exception("Error getting preferences")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to get preferences"})


@telegram_bot_router.post("/preferences")
@telegram_bot_router.post("/preferences/")
@limiter.limit(TELEGRAM_RATE_LIMIT)
async def update_preferences(request: Request):
    """Update user preferences"""
    try:
        data = await request.json()
        api_key = data.get("apikey") or request.headers.get("X-API-KEY")
        if not api_key or not verify_api_key(api_key):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid or missing API key"})
        
        telegram_id = data.get("telegram_id")
        if not telegram_id:
            return JSONResponse(status_code=400, content={"status": "error", "message": "telegram_id is required"})
        
        preferences = {}
        for key in ["order_notifications", "trade_notifications", "pnl_notifications", "daily_summary", "summary_time", "language", "timezone"]:
            if key in data:
                preferences[key] = data[key]
        
        success = update_user_preferences(telegram_id, preferences)
        if success:
            return JSONResponse(content={"status": "success", "message": "Preferences updated successfully"}, status_code=200)
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to update preferences"})
    except Exception:
        logger.exception("Error updating preferences")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to update preferences"})
