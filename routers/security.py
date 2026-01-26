# routers/security.py
"""
FastAPI Security Router for RealAlgo
Handles security dashboard with IP banning, 404 tracking, API abuse tracking.
Requirements: 4.7
"""

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from database.settings_db import get_security_settings, set_security_settings
from database.traffic_db import Error404Tracker, InvalidAPIKeyTracker, IPBan, logs_session
from dependencies_fastapi import check_session_validity
from limiter_fastapi import limiter

logger = logging.getLogger(__name__)

security_router = APIRouter(prefix="/security", tags=["security"])
templates = Jinja2Templates(directory="templates")


@security_router.get("/")
@limiter.limit("60/minute")
async def security_dashboard(request: Request, session: dict = Depends(check_session_validity)):
    """Display security dashboard with banned IPs and 404 tracking"""
    try:
        security_settings = get_security_settings()
        banned_ips = IPBan.get_all_bans()
        suspicious_ips = Error404Tracker.get_suspicious_ips(min_errors=1)
        suspicious_api_users = InvalidAPIKeyTracker.get_suspicious_api_users(min_attempts=1)

        banned_data = [
            {
                "ip_address": ban.ip_address,
                "ban_reason": ban.ban_reason,
                "banned_at": ban.banned_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if ban.banned_at
                else "Unknown",
                "expires_at": ban.expires_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if ban.expires_at
                else "Permanent",
                "is_permanent": ban.is_permanent,
                "ban_count": ban.ban_count,
                "created_by": ban.created_by,
            }
            for ban in banned_ips
        ]

        suspicious_data = [
            {
                "ip_address": tracker.ip_address,
                "error_count": tracker.error_count,
                "first_error_at": tracker.first_error_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.first_error_at
                else "Unknown",
                "last_error_at": tracker.last_error_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.last_error_at
                else "Unknown",
                "paths_attempted": tracker.paths_attempted,
            }
            for tracker in suspicious_ips
        ]

        api_abuse_data = [
            {
                "ip_address": tracker.ip_address,
                "attempt_count": tracker.attempt_count,
                "first_attempt_at": tracker.first_attempt_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.first_attempt_at
                else "Unknown",
                "last_attempt_at": tracker.last_attempt_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.last_attempt_at
                else "Unknown",
                "api_keys_tried": tracker.api_keys_tried,
            }
            for tracker in suspicious_api_users
        ]

        return templates.TemplateResponse(
            "security/dashboard.html",
            {
                "request": request,
                "banned_ips": banned_data,
                "suspicious_ips": suspicious_data,
                "api_abuse_ips": api_abuse_data,
                "security_settings": security_settings,
            },
        )
    except Exception as e:
        logger.error(f"Error loading security dashboard: {e}")
        return templates.TemplateResponse(
            "security/dashboard.html",
            {
                "request": request,
                "banned_ips": [],
                "suspicious_ips": [],
                "api_abuse_ips": [],
                "security_settings": get_security_settings(),
            },
        )


@security_router.post("/ban")
@limiter.limit("30/minute")
async def ban_ip(request: Request, session: dict = Depends(check_session_validity)):
    """Manually ban an IP address"""
    try:
        data = await request.json()
        ip_address = data.get("ip_address", "").strip()
        reason = data.get("reason", "Manual ban").strip()
        duration_hours = int(data.get("duration_hours", 24))
        permanent = data.get("permanent", False)

        if not ip_address:
            return JSONResponse({"error": "IP address is required"}, status_code=400)

        if ip_address in ["127.0.0.1", "::1", "localhost"]:
            return JSONResponse({"error": "Cannot ban localhost"}, status_code=400)

        success = IPBan.ban_ip(
            ip_address=ip_address,
            reason=reason,
            duration_hours=duration_hours,
            permanent=permanent,
            created_by="manual",
        )

        if success:
            logger.info(f"Manual IP ban: {ip_address} - {reason}")
            return JSONResponse({"success": True, "message": f"IP {ip_address} has been banned"})
        else:
            return JSONResponse({"error": "Failed to ban IP"}, status_code=500)

    except Exception as e:
        logger.error(f"Error banning IP: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@security_router.post("/unban")
@limiter.limit("30/minute")
async def unban_ip(request: Request, session: dict = Depends(check_session_validity)):
    """Unban an IP address"""
    try:
        data = await request.json()
        ip_address = data.get("ip_address", "").strip()

        if not ip_address:
            return JSONResponse({"error": "IP address is required"}, status_code=400)

        success = IPBan.unban_ip(ip_address)

        if success:
            logger.info(f"IP unbanned: {ip_address}")
            return JSONResponse({"success": True, "message": f"IP {ip_address} has been unbanned"})
        else:
            return JSONResponse({"error": "IP not found in ban list"}, status_code=404)

    except Exception as e:
        logger.error(f"Error unbanning IP: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@security_router.post("/ban-host")
@limiter.limit("30/minute")
async def ban_host(request: Request, session: dict = Depends(check_session_validity)):
    """Ban by host/domain"""
    try:
        data = await request.json()
        host = data.get("host", "").strip()
        reason = data.get("reason", f"Host ban: {host}").strip()
        permanent = data.get("permanent", False)

        if not host:
            return JSONResponse({"error": "Host is required"}, status_code=400)

        ip_pattern = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")

        if ip_pattern.match(host):
            success = IPBan.ban_ip(
                ip_address=host,
                reason=f"Manual ban: {reason}",
                duration_hours=24 if not permanent else None,
                permanent=permanent,
                created_by="manual",
            )
            if success:
                return JSONResponse({"success": True, "message": f"Banned IP: {host}"})
            else:
                return JSONResponse({"error": f"Failed to ban IP: {host}"}, status_code=500)

        from database.traffic_db import TrafficLog

        matching_logs = (
            TrafficLog.query.filter(TrafficLog.host.like(f"%{host}%"))
            .distinct(TrafficLog.client_ip)
            .all()
        )

        if not matching_logs:
            logger.warning(f"Attempted to ban host {host} but no traffic found from it")
            return JSONResponse(
                {
                    "error": f"No traffic found from host: {host}. To ban specific IPs, use the IP ban form instead.",
                    "suggestion": "Use the Manual IP Ban form above to ban specific IP addresses directly.",
                },
                status_code=404,
            )

        banned_count = 0
        for log in matching_logs:
            if log.client_ip and log.client_ip not in ["127.0.0.1", "::1"]:
                success = IPBan.ban_ip(
                    ip_address=log.client_ip,
                    reason=f"Host ban: {host} - {reason}",
                    duration_hours=24 if not permanent else None,
                    permanent=permanent,
                    created_by="host_ban",
                )
                if success:
                    banned_count += 1

        logger.info(f"Host ban completed: {host} - {banned_count} IPs banned")
        return JSONResponse(
            {"success": True, "message": f"Banned {banned_count} IPs associated with host: {host}"}
        )

    except Exception as e:
        logger.error(f"Error banning host: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@security_router.post("/clear-404")
@limiter.limit("10/minute")
async def clear_404_tracker(request: Request, session: dict = Depends(check_session_validity)):
    """Clear 404 tracker for a specific IP"""
    try:
        data = await request.json()
        ip_address = data.get("ip_address", "").strip()

        if not ip_address:
            return JSONResponse({"error": "IP address is required"}, status_code=400)

        tracker = Error404Tracker.query.filter_by(ip_address=ip_address).first()
        if tracker:
            logs_session.delete(tracker)
            logs_session.commit()
            logger.info(f"Cleared 404 tracker for IP: {ip_address}")
            return JSONResponse(
                {"success": True, "message": f"404 tracker cleared for {ip_address}"}
            )
        else:
            return JSONResponse({"error": "No tracker found for this IP"}, status_code=404)

    except Exception as e:
        logger.error(f"Error clearing 404 tracker: {e}")
        logs_session.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@security_router.get("/api/data")
@limiter.limit("60/minute")
async def security_data(request: Request, session: dict = Depends(check_session_validity)):
    """API endpoint to get all security dashboard data as JSON"""
    try:
        security_settings = get_security_settings()
        banned_ips = IPBan.get_all_bans()
        suspicious_ips = Error404Tracker.get_suspicious_ips(min_errors=1)
        suspicious_api_users = InvalidAPIKeyTracker.get_suspicious_api_users(min_attempts=1)

        banned_data = [
            {
                "ip_address": ban.ip_address,
                "ban_reason": ban.ban_reason,
                "banned_at": ban.banned_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if ban.banned_at
                else "Unknown",
                "expires_at": ban.expires_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if ban.expires_at
                else "Permanent",
                "is_permanent": ban.is_permanent,
                "ban_count": ban.ban_count,
                "created_by": ban.created_by,
            }
            for ban in banned_ips
        ]

        suspicious_data = [
            {
                "ip_address": tracker.ip_address,
                "error_count": tracker.error_count,
                "first_error_at": tracker.first_error_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.first_error_at
                else "Unknown",
                "last_error_at": tracker.last_error_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.last_error_at
                else "Unknown",
                "paths_attempted": tracker.paths_attempted,
            }
            for tracker in suspicious_ips
        ]

        api_abuse_data = [
            {
                "ip_address": tracker.ip_address,
                "attempt_count": tracker.attempt_count,
                "first_attempt_at": tracker.first_attempt_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.first_attempt_at
                else "Unknown",
                "last_attempt_at": tracker.last_attempt_at.strftime("%d-%m-%Y %I:%M:%S %p")
                if tracker.last_attempt_at
                else "Unknown",
                "api_keys_tried": tracker.api_keys_tried,
            }
            for tracker in suspicious_api_users
        ]

        return JSONResponse({
            "banned_ips": banned_data,
            "suspicious_ips": suspicious_data,
            "api_abuse_ips": api_abuse_data,
            "security_settings": security_settings,
        })
    except Exception as e:
        logger.error(f"Error loading security data: {e}")
        return JSONResponse({
            "banned_ips": [],
            "suspicious_ips": [],
            "api_abuse_ips": [],
            "security_settings": get_security_settings(),
        })


@security_router.get("/stats")
@limiter.limit("60/minute")
async def security_stats(request: Request, session: dict = Depends(check_session_validity)):
    """Get security statistics"""
    try:
        total_bans = IPBan.query.count()
        permanent_bans = IPBan.query.filter_by(is_permanent=True).count()
        temp_bans = total_bans - permanent_bans

        suspicious_count = Error404Tracker.query.filter(Error404Tracker.error_count >= 5).count()

        near_threshold = Error404Tracker.query.filter(
            Error404Tracker.error_count >= 15, Error404Tracker.error_count < 20
        ).count()

        return JSONResponse({
            "total_bans": total_bans,
            "permanent_bans": permanent_bans,
            "temporary_bans": temp_bans,
            "suspicious_ips": suspicious_count,
            "near_threshold": near_threshold,
        })

    except Exception as e:
        logger.error(f"Error getting security stats: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@security_router.post("/settings")
@limiter.limit("10/minute")
async def update_security_settings(
    request: Request, session: dict = Depends(check_session_validity)
):
    """Update security threshold settings"""
    try:
        data = await request.json()

        threshold_404 = int(data.get("threshold_404", 20))
        ban_duration_404 = int(data.get("ban_duration_404", 24))
        threshold_api = int(data.get("threshold_api", 10))
        ban_duration_api = int(data.get("ban_duration_api", 48))
        repeat_offender_limit = int(data.get("repeat_offender_limit", 3))

        if threshold_404 < 1 or threshold_404 > 1000:
            return JSONResponse(
                {"error": "404 threshold must be between 1 and 1000"}, status_code=400
            )
        if ban_duration_404 < 1 or ban_duration_404 > 8760:
            return JSONResponse(
                {"error": "Ban duration must be between 1 hour and 1 year"}, status_code=400
            )
        if threshold_api < 1 or threshold_api > 100:
            return JSONResponse(
                {"error": "API threshold must be between 1 and 100"}, status_code=400
            )
        if ban_duration_api < 1 or ban_duration_api > 8760:
            return JSONResponse(
                {"error": "Ban duration must be between 1 hour and 1 year"}, status_code=400
            )
        if repeat_offender_limit < 1 or repeat_offender_limit > 10:
            return JSONResponse(
                {"error": "Repeat offender limit must be between 1 and 10"}, status_code=400
            )

        set_security_settings(
            threshold_404=threshold_404,
            ban_duration_404=ban_duration_404,
            threshold_api=threshold_api,
            ban_duration_api=ban_duration_api,
            repeat_offender_limit=repeat_offender_limit,
        )

        logger.info(
            f"Security settings updated: 404={threshold_404}/{ban_duration_404}h, "
            f"API={threshold_api}/{ban_duration_api}h, Repeat={repeat_offender_limit}"
        )

        return JSONResponse({
            "success": True,
            "message": "Security settings updated successfully",
            "settings": {
                "404_threshold": threshold_404,
                "404_ban_duration": ban_duration_404,
                "api_threshold": threshold_api,
                "api_ban_duration": ban_duration_api,
                "repeat_offender_limit": repeat_offender_limit,
            },
        })

    except ValueError as e:
        logger.error(f"Invalid value in security settings: {e}")
        return JSONResponse({"error": "Invalid numeric value provided"}, status_code=400)
    except Exception as e:
        logger.error(f"Error updating security settings: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
