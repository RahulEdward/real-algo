#!/usr/bin/env python3
"""
Unit Tests for FastAPI CSRF Middleware

This module tests the CSRFMiddleware class for FastAPI to ensure:
- CSRF validation works correctly for state-changing requests
- API paths (/api/v1/) are exempt from CSRF validation
- Safe methods (GET, HEAD, OPTIONS, TRACE) are exempt
- Token validation uses constant-time comparison

Requirements: 3.3, 7.4
"""

import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from csrf_fastapi import CSRFMiddleware, generate_csrf_token, get_csrf_config


# Test fixtures
@pytest.fixture
def app_with_csrf():
    """Create a FastAPI app with CSRF middleware enabled."""
    app = FastAPI()
    
    # Note: Middleware is added in reverse order of execution
    # CSRFMiddleware needs session, so SessionMiddleware must run first (added last)
    app.add_middleware(
        CSRFMiddleware,
        secret_key="test-secret-key-for-testing",
        exempt_paths=["/api/v1/"],
        enabled=True,
    )
    
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key-for-testing",
        session_cookie="test_session",
    )
    
    # Test routes
    @app.get("/")
    async def root():
        return {"message": "Hello World"}
    
    @app.post("/form-submit")
    async def form_submit():
        return {"status": "success"}
    
    @app.post("/api/v1/orders")
    async def api_orders():
        return {"status": "success", "message": "API endpoint"}
    
    @app.get("/csrf-token")
    async def get_csrf_token_endpoint(request: Request):
        token = generate_csrf_token()
        request.session["csrf_token"] = token
        return {"csrf_token": token}
    
    return app


@pytest.fixture
def app_without_csrf():
    """Create a FastAPI app with CSRF middleware disabled."""
    app = FastAPI()
    
    app.add_middleware(
        CSRFMiddleware,
        secret_key="test-secret-key-for-testing",
        exempt_paths=["/api/v1/"],
        enabled=False,
    )
    
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key-for-testing",
        session_cookie="test_session",
    )
    
    @app.post("/form-submit")
    async def form_submit():
        return {"status": "success"}
    
    return app


@pytest.fixture
def client(app_with_csrf):
    """Create a test client for the CSRF-enabled app."""
    return TestClient(app_with_csrf, raise_server_exceptions=False)


@pytest.fixture
def client_no_csrf(app_without_csrf):
    """Create a test client for the CSRF-disabled app."""
    return TestClient(app_without_csrf, raise_server_exceptions=False)


class TestCSRFMiddleware:
    """Test suite for CSRF middleware functionality."""
    
    def test_get_request_allowed_without_csrf(self, client):
        """GET requests should be allowed without CSRF token."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello World"}
    
    def test_post_request_blocked_without_csrf(self, client):
        """POST requests should be blocked without CSRF token."""
        response = client.post("/form-submit")
        assert response.status_code == 400
        assert "CSRF validation failed" in response.json()["detail"]
    
    def test_api_endpoint_exempt_from_csrf(self, client):
        """API endpoints (/api/v1/) should be exempt from CSRF validation."""
        response = client.post("/api/v1/orders")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_csrf_disabled_allows_all_requests(self, client_no_csrf):
        """When CSRF is disabled, all requests should be allowed."""
        response = client_no_csrf.post("/form-submit")
        assert response.status_code == 200
        assert response.json()["status"] == "success"


class TestCSRFTokenGeneration:
    """Test suite for CSRF token generation."""
    
    def test_generate_csrf_token_returns_string(self):
        """generate_csrf_token should return a string."""
        token = generate_csrf_token()
        assert isinstance(token, str)
    
    def test_generate_csrf_token_length(self):
        """generate_csrf_token should return a token of appropriate length."""
        token = generate_csrf_token()
        # URL-safe base64 encoding of 32 bytes = 43 characters
        assert len(token) == 43
    
    def test_generate_csrf_token_unique(self):
        """Each call to generate_csrf_token should return a unique token."""
        tokens = [generate_csrf_token() for _ in range(100)]
        assert len(set(tokens)) == 100  # All tokens should be unique


class TestCSRFConfig:
    """Test suite for CSRF configuration."""
    
    def test_get_csrf_config_default_enabled(self, monkeypatch):
        """CSRF should be enabled by default."""
        monkeypatch.delenv("CSRF_ENABLED", raising=False)
        config = get_csrf_config()
        assert config["enabled"] is True
    
    def test_get_csrf_config_disabled(self, monkeypatch):
        """CSRF can be disabled via environment variable."""
        monkeypatch.setenv("CSRF_ENABLED", "FALSE")
        config = get_csrf_config()
        assert config["enabled"] is False
    
    def test_get_csrf_config_exempt_paths(self, monkeypatch):
        """Default exempt paths should include /api/v1/."""
        monkeypatch.delenv("CSRF_EXEMPT_WEBHOOK_PATHS", raising=False)
        config = get_csrf_config()
        assert "/api/v1/" in config["exempt_paths"]
    
    def test_get_csrf_config_custom_webhook_paths(self, monkeypatch):
        """Custom webhook paths can be added via environment variable."""
        monkeypatch.setenv("CSRF_EXEMPT_WEBHOOK_PATHS", "/webhook/,/hooks/")
        config = get_csrf_config()
        assert "/webhook/" in config["exempt_paths"]
        assert "/hooks/" in config["exempt_paths"]


class TestCSRFValidation:
    """Test suite for CSRF token validation with session."""
    
    def test_valid_csrf_token_in_header(self):
        """Valid CSRF token in X-CSRF-Token header should be accepted."""
        app = FastAPI()
        
        # Note: Middleware is added in reverse order of execution
        # SessionMiddleware must be added AFTER CSRFMiddleware so it runs BEFORE
        app.add_middleware(
            CSRFMiddleware,
            secret_key="test-secret-key",
            exempt_paths=["/api/v1/"],
            enabled=True,
        )
        
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret-key",
            session_cookie="test_session",
        )
        
        @app.get("/get-token")
        async def get_token(request: Request):
            token = generate_csrf_token()
            request.session["csrf_token"] = token
            return {"csrf_token": token}
        
        @app.post("/protected")
        async def protected():
            return {"status": "success"}
        
        client = TestClient(app, raise_server_exceptions=False)
        
        # First, get a CSRF token (this sets it in the session)
        token_response = client.get("/get-token")
        assert token_response.status_code == 200
        token = token_response.json()["csrf_token"]
        
        # Now make a POST request with the token in header
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": token}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_invalid_csrf_token_rejected(self):
        """Invalid CSRF token should be rejected."""
        app = FastAPI()
        
        # Note: Middleware is added in reverse order of execution
        app.add_middleware(
            CSRFMiddleware,
            secret_key="test-secret-key",
            exempt_paths=["/api/v1/"],
            enabled=True,
        )
        
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret-key",
            session_cookie="test_session",
        )
        
        @app.get("/get-token")
        async def get_token(request: Request):
            token = generate_csrf_token()
            request.session["csrf_token"] = token
            return {"csrf_token": token}
        
        @app.post("/protected")
        async def protected():
            return {"status": "success"}
        
        client = TestClient(app, raise_server_exceptions=False)
        
        # First, get a CSRF token to establish session
        client.get("/get-token")
        
        # Now make a POST request with an invalid token
        response = client.post(
            "/protected",
            headers={"X-CSRF-Token": "invalid-token"}
        )
        assert response.status_code == 400
        assert "CSRF validation failed" in response.json()["detail"]


class TestSafeMethodsExemption:
    """Test that safe HTTP methods are exempt from CSRF validation."""
    
    def test_head_request_exempt(self):
        """HEAD requests should be exempt from CSRF validation."""
        app = FastAPI()
        
        app.add_middleware(
            CSRFMiddleware,
            secret_key="test-secret-key",
            enabled=True,
        )
        
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret-key",
            session_cookie="test_session",
        )
        
        @app.head("/test")
        async def test_head():
            return {}
        
        client = TestClient(app, raise_server_exceptions=False)
        response = client.head("/test")
        assert response.status_code == 200
    
    def test_options_request_exempt(self):
        """OPTIONS requests should be exempt from CSRF validation."""
        app = FastAPI()
        
        app.add_middleware(
            CSRFMiddleware,
            secret_key="test-secret-key",
            enabled=True,
        )
        
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret-key",
            session_cookie="test_session",
        )
        
        @app.options("/test")
        async def test_options():
            return {}
        
        client = TestClient(app, raise_server_exceptions=False)
        response = client.options("/test")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
