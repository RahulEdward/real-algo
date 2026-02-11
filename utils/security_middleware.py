"""
Legacy Security Middleware (Flask).

This module is kept for backward compatibility.
The active FastAPI security middleware is in security_middleware_fastapi.py.
"""

import logging
from functools import wraps

from database.traffic_db import Error404Tracker, IPBan, logs_session
from utils.ip_helper import get_real_ip, get_real_ip_from_environ

logger = logging.getLogger(__name__)


class SecurityMiddleware:
    """WSGI Middleware to check for banned IPs - legacy Flask version."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        client_ip = get_real_ip_from_environ(environ)

        if IPBan.is_ip_banned(client_ip):
            status = "403 Forbidden"
            headers = [("Content-Type", "text/plain")]
            start_response(status, headers)
            logger.warning(f"Blocked banned IP: {client_ip}")
            return [b"Access Denied: Your IP has been banned"]

        return self.app(environ, start_response)


def check_ip_ban(f):
    """Decorator to check if IP is banned - legacy Flask version."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = get_real_ip()

        if IPBan.is_ip_banned(client_ip):
            logger.warning(f"Blocked banned IP in decorator: {client_ip}")
            # Return a generic error instead of Flask abort
            raise PermissionError("Access Denied: Your IP has been banned")

        return f(*args, **kwargs)

    return decorated_function


def init_security_middleware(app):
    """Initialize security middleware - legacy Flask version."""
    app.wsgi_app = SecurityMiddleware(app.wsgi_app)
    logger.debug("Security middleware initialized")
