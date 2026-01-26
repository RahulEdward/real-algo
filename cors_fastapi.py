# cors_fastapi.py
"""
FastAPI CORS Configuration for RealAlgo

This module provides CORS configuration for FastAPI CORSMiddleware,
matching the Flask-CORS behavior exactly.

Environment Variables:
- CORS_ENABLED: Enable/disable CORS (TRUE/FALSE)
- CORS_ALLOWED_ORIGINS: Comma-separated list of allowed origins
- CORS_ALLOWED_METHODS: Comma-separated list of allowed HTTP methods
- CORS_ALLOWED_HEADERS: Comma-separated list of allowed headers
- CORS_EXPOSED_HEADERS: Comma-separated list of exposed headers
- CORS_ALLOW_CREDENTIALS: Allow credentials (TRUE/FALSE)
- CORS_MAX_AGE: Max age for preflight requests in seconds

Requirements: 7.1
"""

import os
from typing import Any, Dict, List, Optional


def get_fastapi_cors_config() -> Dict[str, Any]:
    """
    Get CORS configuration for FastAPI CORSMiddleware.
    
    Returns a dictionary with CORS configuration options that can be
    passed directly to CORSMiddleware via **kwargs.
    
    If CORS is disabled, returns an empty dict (middleware should not be added).
    
    Returns:
        Dict with CORS configuration for FastAPI CORSMiddleware:
        - allow_origins: List of allowed origins
        - allow_methods: List of allowed HTTP methods
        - allow_headers: List of allowed headers
        - expose_headers: List of exposed headers
        - allow_credentials: Whether to allow credentials
        - max_age: Max age for preflight requests in seconds
    """
    # Check if CORS is enabled
    cors_enabled = os.getenv("CORS_ENABLED", "FALSE").upper() == "TRUE"
    
    if not cors_enabled:
        # If CORS is disabled, return empty config
        # The middleware should not be added when CORS is disabled
        return {}
    
    cors_config: Dict[str, Any] = {}
    
    # Get allowed origins
    # Flask-CORS: "origins" -> FastAPI: "allow_origins"
    allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS")
    if allowed_origins:
        cors_config["allow_origins"] = [
            origin.strip() for origin in allowed_origins.split(",") if origin.strip()
        ]
    else:
        # Default to empty list (no origins allowed) if not specified
        # This matches Flask-CORS behavior when origins is not set
        cors_config["allow_origins"] = []
    
    # Get allowed methods
    # Flask-CORS: "methods" -> FastAPI: "allow_methods"
    allowed_methods = os.getenv("CORS_ALLOWED_METHODS")
    if allowed_methods:
        cors_config["allow_methods"] = [
            method.strip() for method in allowed_methods.split(",") if method.strip()
        ]
    else:
        # Default to common methods if not specified
        # FastAPI CORSMiddleware default is ["GET"]
        # Flask-CORS default is ["GET", "HEAD", "POST", "OPTIONS", "PUT", "PATCH", "DELETE"]
        cors_config["allow_methods"] = ["GET", "POST"]
    
    # Get allowed headers
    # Flask-CORS: "allow_headers" -> FastAPI: "allow_headers"
    allowed_headers = os.getenv("CORS_ALLOWED_HEADERS")
    if allowed_headers:
        cors_config["allow_headers"] = [
            header.strip() for header in allowed_headers.split(",") if header.strip()
        ]
    else:
        # Default to wildcard if not specified
        # This matches common Flask-CORS usage
        cors_config["allow_headers"] = ["*"]
    
    # Get exposed headers
    # Flask-CORS: "expose_headers" -> FastAPI: "expose_headers"
    exposed_headers = os.getenv("CORS_EXPOSED_HEADERS")
    if exposed_headers:
        cors_config["expose_headers"] = [
            header.strip() for header in exposed_headers.split(",") if header.strip()
        ]
    # If not specified, don't include in config (use FastAPI default: [])
    
    # Check if credentials are allowed
    # Flask-CORS: "supports_credentials" -> FastAPI: "allow_credentials"
    credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "FALSE").upper() == "TRUE"
    cors_config["allow_credentials"] = credentials
    
    # Max age for preflight requests
    # Flask-CORS: "max_age" -> FastAPI: "max_age"
    max_age = os.getenv("CORS_MAX_AGE")
    if max_age and max_age.isdigit():
        cors_config["max_age"] = int(max_age)
    else:
        # Default to 600 seconds (10 minutes) if not specified
        cors_config["max_age"] = 600
    
    return cors_config


def is_cors_enabled() -> bool:
    """
    Check if CORS is enabled via environment variable.
    
    Returns:
        True if CORS_ENABLED is set to "TRUE" (case-insensitive), False otherwise.
    """
    return os.getenv("CORS_ENABLED", "FALSE").upper() == "TRUE"
