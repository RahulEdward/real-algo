# csrf_fastapi.py
"""
CSRF (Cross-Site Request Forgery) Protection Middleware for FastAPI

This module provides CSRF protection equivalent to Flask-WTF CSRFProtect.
It validates CSRF tokens for state-changing requests (POST, PUT, DELETE, PATCH)
while exempting API endpoints that use API key authentication.

Requirements: 3.3, 7.4
"""

import os
import secrets
from typing import List, Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware for FastAPI.
    
    This middleware:
    - Skips CSRF validation for exempt paths (e.g., /api/v1/ which uses API key auth)
    - Skips CSRF validation for safe HTTP methods (GET, HEAD, OPTIONS, TRACE)
    - Validates CSRF token from X-CSRF-Token header or form data csrf_token field
    - Compares tokens using secrets.compare_digest to prevent timing attacks
    
    Attributes:
        secret_key: Application secret key for token generation
        exempt_paths: List of URL path prefixes to exempt from CSRF validation
        safe_methods: HTTP methods that don't require CSRF validation
    """
    
    # Safe HTTP methods that don't modify state
    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
    
    def __init__(
        self,
        app,
        secret_key: str,
        exempt_paths: Optional[List[str]] = None,
        enabled: bool = True,
    ):
        """
        Initialize CSRF middleware.
        
        Args:
            app: The ASGI application
            secret_key: Application secret key
            exempt_paths: List of URL path prefixes to exempt from CSRF validation.
                         Defaults to ["/api/v1/"] since API endpoints use API key auth.
            enabled: Whether CSRF protection is enabled. Defaults to True.
        """
        super().__init__(app)
        self.secret_key = secret_key
        self.exempt_paths = exempt_paths or ["/api/v1/"]
        self.enabled = enabled
        
        logger.debug(
            f"CSRF middleware initialized: enabled={enabled}, "
            f"exempt_paths={self.exempt_paths}"
        )
    
    def _is_exempt_path(self, path: str) -> bool:
        """
        Check if the request path is exempt from CSRF validation.
        
        Args:
            path: The request URL path
            
        Returns:
            True if the path is exempt, False otherwise
        """
        return any(path.startswith(exempt) for exempt in self.exempt_paths)
    
    def _is_safe_method(self, method: str) -> bool:
        """
        Check if the HTTP method is safe (doesn't modify state).
        
        Args:
            method: The HTTP method
            
        Returns:
            True if the method is safe, False otherwise
        """
        return method.upper() in self.SAFE_METHODS
    
    async def _get_csrf_token_from_request(self, request: Request) -> Optional[str]:
        """
        Extract CSRF token from request headers or form data.
        
        The token is checked in the following order:
        1. X-CSRF-Token header (preferred for AJAX requests)
        2. csrf_token field in form data (for traditional form submissions)
        
        Args:
            request: The incoming request
            
        Returns:
            The CSRF token if found, None otherwise
        """
        # First, check the X-CSRF-Token header (preferred for AJAX/React)
        token = request.headers.get("X-CSRF-Token")
        if token:
            return token
        
        # Fall back to form data for traditional form submissions
        # Only try to parse form data for appropriate content types
        content_type = request.headers.get("content-type", "")
        
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                # Note: This consumes the request body, but Starlette caches it
                form = await request.form()
                token = form.get("csrf_token")
                if token:
                    return token
            except Exception as e:
                logger.debug(f"Could not parse form data for CSRF token: {e}")
        
        return None
    
    def _get_session_csrf_token(self, request: Request) -> Optional[str]:
        """
        Get the CSRF token stored in the session.
        
        Args:
            request: The incoming request
            
        Returns:
            The session CSRF token if found, None otherwise
        """
        try:
            return request.session.get("csrf_token")
        except Exception as e:
            logger.debug(f"Could not get session CSRF token: {e}")
            return None
    
    def _validate_csrf_token(self, request_token: str, session_token: str) -> bool:
        """
        Validate the CSRF token using constant-time comparison.
        
        Uses secrets.compare_digest to prevent timing attacks.
        
        Args:
            request_token: Token from the request
            session_token: Token from the session
            
        Returns:
            True if tokens match, False otherwise
        """
        if not request_token or not session_token:
            return False
        
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(request_token, session_token)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request and validate CSRF token if required.
        
        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain
            
        Returns:
            The response from the next handler
            
        Raises:
            HTTPException: 400 error if CSRF validation fails
        """
        # Skip if CSRF protection is disabled
        if not self.enabled:
            return await call_next(request)
        
        # Skip CSRF for exempt paths (API endpoints use API key auth)
        if self._is_exempt_path(request.url.path):
            return await call_next(request)
        
        # Skip CSRF for safe methods (GET, HEAD, OPTIONS, TRACE)
        if self._is_safe_method(request.method):
            return await call_next(request)
        
        # Validate CSRF token for state-changing requests
        request_token = await self._get_csrf_token_from_request(request)
        session_token = self._get_session_csrf_token(request)
        
        if not self._validate_csrf_token(request_token, session_token):
            logger.warning(
                f"CSRF validation failed for {request.method} {request.url.path} "
                f"from {request.client.host if request.client else 'unknown'}"
            )
            # Return a JSON response directly instead of raising HTTPException
            # This ensures proper handling in middleware context
            return JSONResponse(
                status_code=400,
                content={"detail": "CSRF validation failed"}
            )
        
        return await call_next(request)


def generate_csrf_token() -> str:
    """
    Generate a new CSRF token.
    
    Uses secrets.token_urlsafe to generate a cryptographically secure token.
    The token is 32 bytes (256 bits) of randomness, URL-safe base64 encoded.
    
    Returns:
        A new CSRF token string
    """
    return secrets.token_urlsafe(32)


def get_csrf_config() -> dict:
    """
    Get CSRF configuration from environment variables.
    
    Returns:
        Dictionary with CSRF configuration:
        - enabled: Whether CSRF protection is enabled
        - exempt_paths: List of paths exempt from CSRF validation
    """
    enabled = os.getenv("CSRF_ENABLED", "TRUE").upper() == "TRUE"
    
    # Default exempt paths - API endpoints use API key authentication
    # /setup is exempt because it's the initial setup before any session exists
    # /auth/login is exempt because the session doesn't exist yet for CSRF validation
    exempt_paths = ["/api/v1/", "/setup", "/auth/login"]
    
    # Add webhook paths if configured (webhooks use their own auth)
    webhook_paths = os.getenv("CSRF_EXEMPT_WEBHOOK_PATHS", "")
    if webhook_paths:
        exempt_paths.extend(webhook_paths.split(","))
    
    return {
        "enabled": enabled,
        "exempt_paths": exempt_paths,
    }
